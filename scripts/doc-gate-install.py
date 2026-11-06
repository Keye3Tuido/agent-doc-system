#!/usr/bin/env python3
"""Validate capabilities and stage disabled Codex mappings without self-trust."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import tomllib
import uuid

ROOT = Path(__file__).resolve().parent.parent
GATE_ID = 'agent-doc-system-context-update-gate'
EVENTS = ('UserPromptSubmit', 'SessionStart', 'PreToolUse', 'PostToolUse', 'Stop')
PINNED = ('doc-gate.py', 'doc-tree.py', 'doc-stale-check.py', 'doc-encoding-check.py',
          'doc-format-check.py', 'convert-to-utf8.sh', 'doc-gate-install.py')
DEFAULT_RUNTIME = Path(os.environ.get('AGENT_DOCS_GATE_RUNTIME', ROOT / 'runtime' / GATE_ID)).expanduser()
DEFAULT_CONFIG = Path.home() / '.codex'
CAPABILITIES = {'context_each_turn', 'context_after_resume', 'pre_write_deny',
                'post_write_observe', 'continue_pending_review', 'trusted_user_input'}


def atomic(path, text):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def package_hash(root=ROOT):
    root = Path(root)
    paths = [root / name for name in ('README.md', 'urls.conf')]
    for name in ('scripts', 'skills', 'manual', 'templates', 'installers'):
        paths.extend(p for p in (root / name).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
    values = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths if p.is_file()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def handler(root=ROOT, config_dir=DEFAULT_CONFIG, runtime=None):
    root = Path(root)
    config_dir = Path(config_dir).resolve()
    runtime = Path(runtime or root / 'runtime' / GATE_ID).resolve()
    pins = {str(root / 'scripts' / n): hashlib.sha256((root / 'scripts' / n).read_bytes()).hexdigest() for n in PINNED}
    loader = ("import hashlib,json,pathlib,sys\n"
              "event=json.load(sys.stdin)\n"
              f"pins={pins!r}\n"
              "try:\n"
              " for p,h in pins.items():\n"
              "  if hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()!=h: raise ValueError('package checksum mismatch; restage before enabling')\n"
              f" p=pathlib.Path({str(root / 'scripts/doc-gate.py')!r})\n"
              " import io\n"
              " sys.stdin=io.StringIO(json.dumps(event))\n"
              f" sys.argv=[str(p),'--runtime',{str(runtime)!r},'hook']\n"
              " exec(compile(p.read_bytes(),str(p),'exec'),{'__name__':'__main__','__file__':str(p)})\n"
              "except Exception as e:\n"
              f" m={GATE_ID!r}+': '+str(e)\n"
              " n=event.get('hook_event_name')\n"
              " repair=False\n"
              " try:\n"
              "  import shlex\n"
              "  text=event.get('tool_input',{}).get('command','')\n"
              "  tokens=shlex.split(text) if not any(c in text for c in '\\n\\r`$;|&><') else []\n"
              f"  repair=(event.get('tool_name')=='Bash' and len(tokens)>2 and (tokens[0]==sys.executable or pathlib.Path(tokens[0]).name in ('python','python3')) and pathlib.Path(tokens[1]).resolve()==pathlib.Path({str(root / 'scripts/doc-gate-install.py')!r}) and any(t in ('--stage-disabled','--require-ready','--register-adapter') for t in tokens[2:]))\n"
              " except Exception: pass\n"
              " regulated=True\n"
              " try:\n"
              "  import subprocess\n"
              "  cwd=pathlib.Path(event['cwd']).resolve(strict=True)\n"
              "  project=next((p for p in (cwd,*cwd.parents) if (p/'.agent-docs/_index.md').is_file()),None)\n"
              "  if project is None:\n"
              "   raw=subprocess.run(['git','-C',str(cwd),'rev-parse','--show-toplevel'],capture_output=True,text=True,timeout=10)\n"
              "   project=pathlib.Path(raw.stdout.strip()).resolve() if raw.returncode==0 else cwd\n"
              "  key=hashlib.sha256(json.dumps([str(project),event['session_id']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()\n"
              f"  state=pathlib.Path({str(runtime)!r})/(key+'.json')\n"
              "  regulated=(project/'.agent-docs/_index.md').is_file() or bool(json.loads(state.read_text()).get('pending') if state.is_file() else False)\n"
              " except Exception: pass\n"
              " if n=='PreToolUse' and regulated and not repair: r={'hookSpecificOutput':{'hookEventName':n,'permissionDecision':'deny','permissionDecisionReason':m}}\n"
              " elif n in ('UserPromptSubmit','SessionStart'): r={'hookSpecificOutput':{'hookEventName':n,'additionalContext':m}}\n"
              " else: r={'systemMessage':m}\n"
              " print(json.dumps(r))\n")
    digest = package_hash(root)
    return {'type': 'command', 'command': shlex.join([sys.executable, '-c', loader]),
            'statusMessage': GATE_ID, 'timeout': 240}, digest


def event_key(event):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event).lower()


def locations(config, path):
    return [str(path) + ':' + event_key(event) + f':{gi}:{hi}'
            for event, groups in config.get('hooks', {}).items()
            for gi, group in enumerate(groups) for hi, item in enumerate(group.get('hooks', []))
            if item.get('statusMessage') == GATE_ID]


def merged(config, config_dir=DEFAULT_CONFIG, runtime=DEFAULT_RUNTIME):
    result = json.loads(json.dumps(config))
    hooks = result.setdefault('hooks', {})
    entry, digest = handler(config_dir=config_dir, runtime=runtime)
    existing = {}
    for event, groups in hooks.items():
        for gi, group in enumerate(groups):
            for hi, item in enumerate(group.get('hooks', [])):
                if item.get('statusMessage') == GATE_ID:
                    if event not in EVENTS or event in existing or len(group['hooks']) != 1:
                        raise ValueError('ambiguous doc gate mappings; resolve before restaging')
                    existing[event] = (gi, hi)
    for event in EVENTS:
        group = {'hooks': [dict(entry)]}
        if event in ('PreToolUse', 'PostToolUse'):
            group['matcher'] = '.*'
        if event in ('UserPromptSubmit', 'SessionStart'):
            group['hooks'][0]['additionalContextLimit'] = 0
        if event in existing:
            hooks[event][existing[event][0]] = group
        else:
            hooks.setdefault(event, []).append(group)
    return result, digest


def host_identity():
    """Identify the running Codex ancestor, never guess from installed paths."""
    pid = os.getppid()
    for _ in range(16):
        output = subprocess.run(['ps', '-p', str(pid), '-o', 'ppid=', '-o', 'comm='],
                                capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        if not output:
            break
        parent, command = output.split(None, 1)
        proc = Path('/proc') / str(pid) / 'exe'
        binary = proc.resolve() if proc.exists() else Path(command)
        if binary.name in ('codex', 'CodexCLI') and binary.is_file():
            stat = binary.stat()
            return {'path': str(binary.resolve()), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                    'inode': stat.st_ino, 'device': stat.st_dev}
        pid = int(parent)
        if pid <= 1:
            break
    raise ValueError('cannot identify the running Codex host; a verified host adapter is required')


def codex_status(config_dir, runtime):
    """Codex adapter only: inspect its mappings without changing native state."""
    config_dir = Path(config_dir).resolve()
    try:
        path = config_dir / 'hooks.json'
        original = json.loads(path.read_text())
        updated, digest = merged(original, config_dir, runtime)
        if original != updated or len(locations(original, path)) != len(EVENTS):
            raise ValueError('missing or changed mapping; restage all five events')
        native = tomllib.loads((config_dir / 'config.toml').read_text())
        states = {}
        for identity in locations(original, path):
            value = native.get('hooks', {}).get('state', {}).get(identity, {})
            if value.get('enabled') is not True:
                raise ValueError('disabled hook: ' + identity)
            if not isinstance(value.get('trusted_hash'), str) or not value['trusted_hash']:
                raise ValueError('missing host trust: ' + identity)
            states[identity] = value
        report = json.loads((Path(runtime) / 'registration.json').read_text())
        if report.get('behavior_tests') != 'passed' or report.get('package_sha256') != digest:
            raise ValueError('package changed or behavior tests not passed; restage')
        raw = {'mappings': {e: updated['hooks'][e] for e in EVENTS}, 'states': states,
               'package_sha256': digest, 'config_dir': str(config_dir)}
        return {'adapter_id': 'codex', 'gate_id': GATE_ID, 'enabled': True, 'trusted': True,
                'host_fingerprint': host_identity(), 'capabilities': sorted(CAPABILITIES),
                'configuration_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()}
    except (OSError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError('missing or invalid host registration: ' + str(error)) from error


def validate_adapter(descriptor):
    if descriptor.get('schema_version') != 1 or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', descriptor.get('adapter_id', '')):
        raise ValueError('invalid adapter identity or schema')
    command, files = descriptor.get('check_command'), descriptor.get('files')
    if (not isinstance(command, list) or not command or not all(isinstance(v, str) for v in command)
            or not Path(command[0]).is_absolute() or not isinstance(files, dict) or not files):
        raise ValueError('adapter needs an absolute argv check_command and pinned files')
    entry = descriptor.get('entry_file')
    if command[0] not in files or not isinstance(entry, str) or entry not in command or entry not in files:
        raise ValueError('adapter executable and explicit entry_file must both be pinned')
    for path, expected in files.items():
        if not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('adapter file changed; review and register again: ' + path)
    return descriptor


def register_adapter(path, runtime, report):
    descriptor = validate_adapter(json.loads(Path(path).read_text()))
    runtime = Path(runtime)
    atomic(runtime / 'adapter.json', json.dumps(descriptor, ensure_ascii=False, indent=2) + '\n')
    report.update({'adapter_id': descriptor['adapter_id'], 'gate_id': GATE_ID,
                   'package_sha256': package_hash(), 'registration_id': uuid.uuid4().hex,
                   'native_execution_verified': False})
    atomic(runtime / 'registration.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def binding(runtime):
    """Host-neutral contract: every adapter supplies the same observed facts."""
    runtime = Path(runtime)
    try:
        descriptor = validate_adapter(json.loads((runtime / 'adapter.json').read_text()))
        report = json.loads((runtime / 'registration.json').read_text())
        if (report.get('adapter_id') != descriptor['adapter_id'] or report.get('behavior_tests') != 'passed'
                or report.get('package_sha256') != package_hash()):
            raise ValueError('package changed or adapter behavior tests not passed; register again')
        result = subprocess.run(descriptor['check_command'], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('adapter check failed: ' + result.stdout[-1500:])
        status = json.loads(result.stdout)
        if status.get('adapter_id') != descriptor['adapter_id'] or status.get('gate_id') != GATE_ID:
            raise ValueError('adapter check returned the wrong identity')
        if status.get('enabled') is not True or status.get('trusted') is not True:
            raise ValueError('adapter hooks disabled or missing host trust')
        if not CAPABILITIES.issubset(status.get('capabilities', [])):
            raise ValueError('adapter lacks required capabilities: ' + ', '.join(sorted(CAPABILITIES - set(status.get('capabilities', [])))))
        if not status.get('host_fingerprint') or not status.get('configuration_sha256'):
            raise ValueError('adapter must identify the actual host and configuration')
        raw = {'adapter': descriptor, 'status': status, 'registration_id': report.get('registration_id')}
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, AttributeError) as error:
        raise ValueError('adapter unavailable: ' + str(error)) from error


def verification(runtime):
    path = Path(runtime) / 'native-verification.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def probe_matches(record, runtime, project, session):
    if not project or record.get('session') != session:
        return False
    path = Path(project).resolve()
    probes = (Path(runtime) / 'probes').resolve()
    return (path == Path(record.get('project', '/missing')).resolve() and path.is_relative_to(probes)
            and (path / '.agent-docs/_index.md').is_file()
            and record.get('nonce', '') in (path / '.agent-docs/_index.md').read_text())


def require_ready(runtime=DEFAULT_RUNTIME, project=None, session=None):
    try:
        current = binding(runtime)
        record = verification(runtime)
        if record.get('binding') != current:
            raise ValueError('native verification missing or stale; run --start-verification after host review')
        effects = {'session_context', 'prompt_context', 'write', 'deny', 'stop', 'continued', 'approval'}
        if (set(record.get('effects', [])) >= effects and record.get('confirmed_prompt_sha256')
                == hashlib.sha256(('确认文档门限验证 ' + record['nonce']).encode()).hexdigest()):
            return {'ready': True, 'gate_id': GATE_ID, 'binding': current}
        if probe_matches(record, runtime, project, session):
            return {'ready': False, 'verification_only': True, 'gate_id': GATE_ID}
        raise ValueError('native verification incomplete; only the isolated verification project may proceed')
    except (ValueError, OSError, TypeError, KeyError) as error:
        raise ValueError('not ready: ' + str(error)) from error


def start_verification(runtime, session=None):
    import tempfile
    current = binding(runtime)
    probes = Path(runtime) / 'probes'
    probes.mkdir(parents=True, exist_ok=True, mode=0o700)
    project = Path(tempfile.mkdtemp(prefix='native-', dir=probes)).resolve()
    nonce = uuid.uuid4().hex
    docs = project / '.agent-docs'
    (docs / 'doc-library/modules').mkdir(parents=True)
    (docs / '_index.md').write_text('---\nschema_version: 7\nproject_config: {}\n---\n# Native verification\n' + nonce + '\n')
    (docs / 'doc-library/main-module.md').write_text('---\nschema_version: 7\n---\n# Probe\n\n## 定位\nNative verification fixture.\n')
    (project / 'probe.txt').write_text('before\n')
    for args in (('init', '-q'), ('add', '.'), ('-c', 'user.name=Doc gate probe',
                  '-c', 'user.email=probe@example.invalid', 'commit', '-qm', 'isolated native verification')):
        subprocess.run(['git', '-C', str(project), *args], check=True, capture_output=True, timeout=20)
    record = {'binding': current, 'project': str(project), 'session': session,
              'nonce': nonce, 'effects': [], 'observations': [], 'started_at': time.time()}
    atomic(Path(runtime) / 'native-verification.json', json.dumps(record, indent=2) + '\n')
    return record


def bind_verification(runtime, project, session, event):
    """A new probe chat supplies its real session through SessionStart."""
    record = verification(runtime)
    if record.get('session') is not None or event.get('hook_event_name') != 'SessionStart':
        return
    candidate = dict(record, session=session)
    if not probe_matches(candidate, runtime, project, session):
        return
    if record.get('binding') != binding(runtime):
        raise ValueError('native verification binding changed; restart verification')
    atomic(Path(runtime) / 'native-verification.json', json.dumps(candidate, indent=2) + '\n')


def observe_verification(runtime, project, session, event, result, state):
    record = verification(runtime)
    if not probe_matches(record, runtime, project, session):
        return
    if record.get('binding') != binding(runtime):
        raise ValueError('native verification binding changed; restart verification')
    name = event.get('hook_event_name')
    effects = set(record['effects'])
    output = result.get('hookSpecificOutput', {})
    if name in ('UserPromptSubmit', 'SessionStart') and record['nonce'] in output.get('additionalContext', ''):
        effects.add('prompt_context' if name == 'UserPromptSubmit' else 'session_context')
    if name == 'PostToolUse' and (state.get('pending') or {}).get('paths') and state.get('update_checks', 0) > 0:
        effects.add('write')
    if name == 'PreToolUse' and output.get('permissionDecision') == 'deny' and 'write' in effects:
        effects.add('deny')
    if name == 'PreToolUse' and 'stop' in effects:
        effects.add('continued')
    if name == 'Stop' and result.get('decision') == 'block':
        effects.add('stop')
    if (name == 'UserPromptSubmit' and re.fullmatch(r'\s*确认文档 [a-f0-9]{16} [a-f0-9]{12}\s*', event.get('prompt', ''))
            and state.get('last_review', {}).get('status') == 'applied' and not state.get('pending')):
        effects.add('approval')
    prompt = '确认文档门限验证 ' + record['nonce']
    if name == 'UserPromptSubmit' and event.get('prompt') == prompt:
        required = {'session_context', 'prompt_context', 'write', 'deny', 'stop', 'continued', 'approval'}
        if not effects >= required:
            raise ValueError('native verification incomplete: ' + ', '.join(sorted(required - effects)))
        record['confirmed_prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
        record['confirmed_turn_id'] = event.get('turn_id')
        record['verified_at'] = time.time()
    record['effects'] = sorted(effects)
    record['observations'].append({'event': name, 'turn_id': event.get('turn_id'),
                                   'tool_use_id': event.get('tool_use_id'), 'at': time.time()})
    atomic(Path(runtime) / 'native-verification.json', json.dumps(record, indent=2) + '\n')


def table_header(line):
    if not line.lstrip().startswith('['):
        return None
    try:
        return tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return None


def disabled_config(text, ids):
    expected = tomllib.loads(text)
    for identity in ids:
        expected.setdefault('hooks', {}).setdefault('state', {}).setdefault(identity, {})['enabled'] = False
    for identity in sorted(set(ids)):
        lines = text.splitlines(keepends=True)
        starts = [i for i, line in enumerate(lines)
                  if identity in (table_header(line) or {}).get('hooks', {}).get('state', {})]
        if not starts:
            text = text.rstrip('\n') + '\n\n[hooks.state.' + json.dumps(identity) + ']\nenabled = false\n'
            continue
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines)) if table_header(lines[i]) is not None), len(lines))
        indices = []
        for i in range(start + 1, end):
            try:
                if 'enabled' in tomllib.loads(lines[i]):
                    indices.append(i)
            except tomllib.TOMLDecodeError:
                continue
        if indices:
            lines[indices[0]] = 'enabled = false\n'
        else:
            lines.insert(start + 1, 'enabled = false\n')
        text = ''.join(lines)
    if tomllib.loads(text) != expected:
        raise ValueError('native disable edit changed unrelated policy or trust')
    return text


def preflight():
    failures = []
    for script in ('test_doc_gate.py', 'test_doc_gate_install.py'):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '-q'], capture_output=True, text=True, timeout=120)
        if result.returncode:
            failures.append(script + ': ' + result.stderr[-2000:])
    if failures:
        raise ValueError('capability tests failed: ' + '; '.join(failures))
    return {'behavior_tests': 'passed', 'package_sha256': package_hash(), 'tested_at': time.time(),
            'native_execution_verified': False, 'host_trust': 'pending_host_review'}


def stage(config_dir, report, runtime=DEFAULT_RUNTIME):
    hooks_path, native_path = config_dir / 'hooks.json', config_dir / 'config.toml'
    before = hooks_path.read_bytes() if hooks_path.exists() else b'{"hooks":{}}'
    native_before = native_path.read_bytes() if native_path.exists() else b''
    original = json.loads(before)
    updated, digest = merged(original, config_dir, runtime)
    ids = locations(original, hooks_path) + locations(updated, hooks_path)
    native_after = disabled_config(native_before.decode(), ids)
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path, data in ((hooks_path, before), (native_path, native_before)):
        backup = runtime / (path.name + '.before-' + hashlib.sha256(data).hexdigest()[:12])
        if not backup.exists():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
    if (hooks_path.read_bytes() if hooks_path.exists() else b'{"hooks":{}}') != before or (native_path.read_bytes() if native_path.exists() else b'') != native_before:
        raise ValueError('configuration changed during staging')
    atomic(native_path, native_after)
    atomic(hooks_path, json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
    report.update({'gate_id': GATE_ID, 'events': list(EVENTS), 'package_sha256': digest,
                   'lifecycle': 'disabled', 'production_enabled': False, 'native_identities': sorted(set(ids))})
    descriptor = {'schema_version': 1, 'adapter_id': 'codex',
                  'entry_file': str(Path(__file__).resolve()),
                  'check_command': [sys.executable, str(Path(__file__).resolve()), '--inspect-codex',
                                    '--config-dir', str(config_dir), '--runtime', str(runtime)],
                  'files': {str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            sys.executable: hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}}
    manifest = runtime / 'codex-adapter.json'
    atomic(manifest, json.dumps(descriptor, indent=2) + '\n')
    return register_adapter(manifest, runtime, report)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--stage-disabled', action='store_true')
    mode.add_argument('--require-ready', action='store_true')
    mode.add_argument('--start-verification', action='store_true')
    mode.add_argument('--register-adapter', type=Path)
    mode.add_argument('--inspect-codex', action='store_true', help='Codex adapter checker; not the common readiness gate')
    parser.add_argument('--session')
    parser.add_argument('--config-dir', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    try:
        if args.stage_disabled:
            result = stage(args.config_dir.resolve(), preflight(), args.runtime)
        elif args.register_adapter:
            result = register_adapter(args.register_adapter, args.runtime, preflight())
        elif args.inspect_codex:
            result = codex_status(args.config_dir.resolve(), args.runtime)
        elif args.start_verification:
            result = start_verification(args.runtime, args.session)
        else:
            result = require_ready(args.runtime)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        print(json.dumps({'ready': False, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == '__main__':
    main()

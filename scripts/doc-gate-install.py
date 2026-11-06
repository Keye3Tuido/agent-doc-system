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

ROOT = Path(__file__).resolve().parent.parent
GATE_ID = 'agent-doc-system-context-update-gate'
EVENTS = ('UserPromptSubmit', 'SessionStart', 'PreToolUse', 'PostToolUse', 'Stop')
PINNED = ('doc-gate.py', 'doc-tree.py', 'doc-stale-check.py', 'doc-encoding-check.py',
          'doc-format-check.py', 'convert-to-utf8.sh')


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


def handler(root=ROOT):
    root = Path(root)
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
              " sys.argv=[str(p),'hook']\n"
              " exec(compile(p.read_bytes(),str(p),'exec'),{'__name__':'__main__','__file__':str(p)})\n"
              "except Exception as e:\n"
              f" m={GATE_ID!r}+': '+str(e)\n"
              " n=event.get('hook_event_name')\n"
              " if n=='PreToolUse': r={'hookSpecificOutput':{'hookEventName':n,'permissionDecision':'deny','permissionDecisionReason':m}}\n"
              " elif n in ('UserPromptSubmit','SessionStart'): r={'hookSpecificOutput':{'hookEventName':n,'additionalContext':m}}\n"
              " else: r={'systemMessage':m}\n"
              " print(json.dumps(r))\n")
    digest = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    return {'type': 'command', 'command': shlex.join([sys.executable, '-c', loader]),
            'statusMessage': GATE_ID, 'timeout': 240}, digest


def event_key(event):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event).lower()


def locations(config, path):
    return [str(path) + ':' + event_key(event) + f':{gi}:{hi}'
            for event, groups in config.get('hooks', {}).items()
            for gi, group in enumerate(groups) for hi, item in enumerate(group.get('hooks', []))
            if item.get('statusMessage') == GATE_ID]


def merged(config):
    result = json.loads(json.dumps(config))
    hooks = result.setdefault('hooks', {})
    entry, digest = handler()
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
    return {'behavior_tests': 'passed', 'package_sha256': handler()[1], 'tested_at': time.time(),
            'native_execution_verified': False, 'host_trust': 'pending_host_review'}


def stage(config_dir, report):
    hooks_path, native_path = config_dir / 'hooks.json', config_dir / 'config.toml'
    before = hooks_path.read_bytes() if hooks_path.exists() else b'{"hooks":{}}'
    native_before = native_path.read_bytes() if native_path.exists() else b''
    original = json.loads(before)
    updated, digest = merged(original)
    ids = locations(original, hooks_path) + locations(updated, hooks_path)
    native_after = disabled_config(native_before.decode(), ids)
    runtime = ROOT / 'runtime' / GATE_ID
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
    atomic(runtime / 'registration.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage-disabled', action='store_true')
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.codex')
    args = parser.parse_args()
    if not args.stage_disabled:
        parser.error('only --stage-disabled is supported; native trust and enablement belong to the host')
    # Capability checks precede any hook registration or native state mutation.
    print(json.dumps(stage(args.config_dir.resolve(), preflight()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

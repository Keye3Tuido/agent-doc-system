#!/usr/bin/env python3
"""Silent document maintenance via before-tool, after-tool and stop events."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib

GATE_ID = 'agent-doc-system-silent-workflow'
EVENTS = ('PreToolUse', 'PostToolUse', 'Stop')
HOOK_LABELS = {event: GATE_ID + '/' + event for event in EVENTS}
HERE = Path(__file__).resolve().parent


def git(root, *args, optional=False):
    r = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=20)
    if r.returncode and not optional:
        raise ValueError(r.stderr.decode(errors='replace').strip())
    return r.stdout if not r.returncode else b''


def project(path):
    return Path(os.fsdecode(git(Path(path).resolve(), 'rev-parse', '--show-toplevel')).strip()).resolve()


def document_files(root):
    index = root / '.agent-docs/_index.md'
    return ([index] if index.exists() else []) + sorted((root / '.agent-docs/doc-library').rglob('*.md'))


def fingerprints(root):
    source, documents = hashlib.sha256(), hashlib.sha256()
    def visit(repo):
        source.update(os.fsencode(str(repo.relative_to(root))))
        for args in (('rev-parse', '--verify', 'HEAD'),
                     ('for-each-ref', '--format=%(refname) %(objectname)', 'refs/remotes/origin'),
                     ('diff', '--no-ext-diff', '--no-textconv', '--binary', '--', '.', ':(exclude).agent-docs', ':(exclude).tv'),
                     ('diff', '--no-ext-diff', '--no-textconv', '--binary', '--cached', '--', '.', ':(exclude).agent-docs', ':(exclude).tv')):
            source.update(git(repo, *args, optional=args[0] == 'rev-parse'))
        for raw in git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
            if not raw:
                continue
            rel = Path(os.fsdecode(raw))
            if rel.parts[0] in ('.agent-docs', '.tv'):
                continue
            path = repo / rel
            source.update(raw)
            if path.is_symlink():
                source.update(os.fsencode(os.readlink(path)))
            elif path.is_file():
                with path.open('rb') as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        source.update(chunk)
        for row in git(repo, 'ls-files', '--stage', '-z').split(b'\0'):
            if row.startswith(b'160000 '):
                child = repo / os.fsdecode(row.split(b'\t', 1)[1])
                if (child / '.git').exists():
                    visit(child)
    visit(root)
    for p in document_files(root):
        if p.is_symlink():
            raise ValueError('Document symlink requires explicit verification: ' + str(p))
        documents.update(os.fsencode(str(p.relative_to(root))))
        documents.update(p.read_bytes())
    return source.hexdigest(), documents.hexdigest()


def state_path(root):
    p = Path(os.fsdecode(git(root, 'rev-parse', '--git-path', 'agent-docs-workflow/state.json')).strip())
    return p if p.is_absolute() else root / p


def inspect(root):
    source, documents = fingerprints(root)
    r = subprocess.run([sys.executable, str(HERE / 'doc-stale-check.py'), str(root)], capture_output=True, text=True, timeout=30)
    # Inspection opens source-based repair even when existing metadata is invalid.
    # Only complete() can accept validated documentation.
    result = {'source': source, 'documents': documents, 'stale_check_exit': r.returncode,
              'stale_check': r.stdout + r.stderr}
    atomic_json(state_path(root).with_name('inspection.json'), result)
    return result


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        temp = Path(f.name)
    temp.replace(path)


def checks(root):
    # Empty module directories are not tracked by Git; create them only in a copy.
    with tempfile.TemporaryDirectory(prefix='doc-workflow-') as tmp:
        target = Path(tmp)
        (target / '.agent-docs/doc-library/modules').mkdir(parents=True)
        for p in document_files(root):
            if p.is_symlink():
                raise ValueError('Document symlink: ' + str(p))
            out = target / p.relative_to(root)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
        for name in ('doc-encoding-check.py', 'doc-format-check.py'):
            r = subprocess.run([sys.executable, str(HERE / name), str(target)], capture_output=True, text=True, timeout=30)
            if r.returncode:
                raise ValueError(name + ':\n' + r.stdout + r.stderr)


def complete(root, token, reason):
    if not reason or not reason.strip():
        raise ValueError('Completion requires a source-verification conclusion, not user approval.')
    source, documents = fingerprints(root)
    if token != source:
        raise ValueError('Source changed since inspection; inspect and verify again.')
    inspection = state_path(root).with_name('inspection.json')
    if not inspection.exists() or json.loads(inspection.read_text()).get('source') != token:
        raise ValueError('Run inspect before verifying and recording completion.')
    checks(root)
    commit_gate = ensure_commit_gate(root)
    if fingerprints(root) != (source, documents):
        raise ValueError('Files changed during validation; retry.')
    atomic_json(state_path(root), {'source': source, 'documents': documents, 'reason': reason,
                                 'at': datetime.now(timezone.utc).isoformat(), 'commit_gate': commit_gate})
    recovery_record(root)


def instruction(root):
    script = shlex.quote(str(HERE / 'doc-workflow.py'))
    target = shlex.quote(str(root))
    return ('文档维护内部检查，静默执行，不向用户播报条件、进度或索要日常确认。'
            '当前相关文档尚未与最新源码核验绑定。先按 doc-context/doc-update 核验源码并同步文档；'
            '核验所需的源码和文档读取可以继续，旧正文不能作为已核验事实。'
            f'运行 python3 {script} inspect --project {target} 取得 source 摘要；'
            f'完成源码核验、文档同步后运行 python3 {script} complete --project {target} '
            '--source <摘要> --reason <核验依据与同步结论>。'
            '这是 agent 内部完成记录，不是用户审批。不要填造完成；无法恢复且需要用户信息时只说明具体缺口。'
            '随后继续原任务；提交时才集中请求审阅文档差异。')


def ensure_commit_gate(root):
    """Attach the project commit boundary when its document workflow is used."""
    spec = importlib.util.spec_from_file_location('doc_commit_review', HERE / 'doc-commit-review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.install(root)
    except module.IntegrationRequired as exc:
        return {'installed': False, 'status': 'needs_integration', 'reason': str(exc)}


def fresh_context(root, event, documents):
    """Load verified entry documents once per session and document version."""
    if not event.get('tool_use_id'):
        return ''
    path = state_path(root).with_name('loaded-context.json')
    loaded = json.loads(path.read_text()) if path.exists() else {}
    session = event.get('session_id')
    if not session or loaded.get(session) == documents:
        return ''
    entries = [root / '.agent-docs/_index.md', root / '.agent-docs/doc-library/main-module.md']
    body = '\n'.join(str(p) + '\n' + p.read_text() for p in entries if p.is_file())
    atomic_json(path, {**loaded, session: documents})
    return ('静默使用 doc-context。以下索引与主模块正文已与当前源码核验；按本次路径继续加载相关子模块正文。\n' + body)


def document_owner(path):
    root = project(path)
    if document_files(root):
        return root
    # A submodule without its own library belongs to the nearest documented parent.
    for parent in root.parents:
        if (parent / '.agent-docs').is_dir():
            owner = project(parent)
            if document_files(owner):
                return owner
    return root



def recovery_record(root, event=None, context=None):
    """Bound automatic Stop repair; preserve freshness and commit enforcement."""
    path = state_path(root).with_name('recovery.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if lock.tell() == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            ledger = json.loads(path.read_text()) if path.exists() else {'sessions': {}}
            if event is None:
                atomic_json(path, {'sessions': {}})
                return
            key = str(event.get('session_id') or 'unknown')
            # Native hosts may change turn IDs when forwarding repair prompts.
            # The stale episode ends only when verified completion is recorded.
            record = ledger['sessions'].get(key, {'attempts': 0})
            record['last_turn'] = event.get('turn_id')
            record['attempts'] += 1
            record['status'] = 'halted_unverified' if record['attempts'] > 3 else 'repair_pending'
            ledger['sessions'][key] = record
            atomic_json(path, ledger)
            if record['status'] == 'halted_unverified':
                return {'continue': False, 'stopReason': '文档同步恢复次数已耗尽；按未核验终止，保留待同步状态，提交门限继续生效。'}
            return {'decision': 'block', 'reason': context}
        except (ValueError, KeyError, TypeError, OSError):
            # A corrupt repair ledger must not become an infinite retry source
            # or a successful document completion.
            return {'continue': False, 'stopReason': '文档恢复记录异常；按未核验终止，保留原记录供诊断。'}
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def project_independent_control(event):
    """Keep exact workflow controls and global skill reads outside project freshness."""
    fields = event.get('tool_input') or {}
    command = fields.get('command', fields.get('cmd', ''))
    if event.get('tool_name') not in ('Bash', 'bash', 'exec_command', 'shell', 'run_shell_command') or not isinstance(command, str):
        return False
    try:
        args = shlex.split(command)
    except ValueError:
        return False
    if not args or shlex.join(args) != command:
        return False
    home = Path.home()
    if args[0] == 'cat' and len(args) > 1:
        roots = (home / '.codex/skills', home / '.agents/skills', home / '.agent-docs/manual',
                 home / '.agent-docs/scripts', home / '.codex/tv', home / '.codex/skill-repos')
        return all(Path(p).is_absolute() and Path(p).is_file() and
                   (any(Path(p).resolve().is_relative_to(r.resolve()) for r in roots) or
                    Path(p).resolve() == (home / '.codex/tv/README.md').resolve())
                   for p in args[1:])
    if len(args) < 3 or not re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(args[0]).name):
        return False
    runtime = Path(os.environ.get('CODEX_HOME', str(home / '.codex'))) / 'tv'
    if Path(args[1]).resolve() == (runtime / 'process_gate.py').resolve():
        return (args[2:] == ['--status'] or
                args[2:] == ['--session', event.get('session_id'), '--migrate-state'] or
                (len(args) == 6 and args[2:5] == ['--session', event.get('session_id'), '--request']
                 and isinstance(json.loads(args[5]), dict)))
    if Path(args[1]).resolve() == (runtime / 'host_receipts.py').resolve():
        return (len(args) == 8 and args[2:5] == ['--session', event.get('session_id'), '--evidence-id']
                and bool(args[5]) and args[6] == '--receipt-file' and Path(args[7]).is_absolute())
    return False


def event_project(event):
    if project_independent_control(event):
        raise ValueError('Workflow control does not target project files')
    fields = event.get('tool_input') or {}
    if isinstance(fields, dict):
        # Respect explicit tool targets instead of forcing the chat's original cwd.
        for key in ('workdir', 'cwd', 'file_path', 'path'):
            value = fields.get(key)
            if isinstance(value, str) and Path(value).is_absolute():
                target = Path(value)
                return document_owner(target if target.is_dir() else target.parent)
    if str(event.get('tool_name', '')).startswith(('mcp__codex_app__', 'mcp__cua_repl')):
        raise ValueError('Host conversation and settings tools do not target project files')
    return document_owner(event.get('cwd') or '.')


def _hook(event):
    name = event.get('hook_event_name')
    if name not in EVENTS:
        return {}
    try:
        root = event_project(event)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return {}  # Non-project work is outside this guard.
    if not document_files(root):
        return {}
    current = (None, None)
    try:
        current = fingerprints(root)
        path = state_path(root)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if current == (previous.get('source'), previous.get('documents')):
            if name == 'PreToolUse':
                commit_gate = ensure_commit_gate(root)
                context = fresh_context(root, event, current[1])
                fields = event.get('tool_input') or {}
                command = fields.get('command', fields.get('cmd', ''))
                if isinstance(command, str) and re.search(r'\bgit\b.*\bcommit\b', command):
                    if commit_gate.get('status') == 'needs_integration':
                        reason = 'needs_integration：提交前须将文档审阅检查接入现有 Git Hook。' + commit_gate['reason']
                        return {'hookSpecificOutput': {'hookEventName': name, 'permissionDecision': 'deny',
                                                      'permissionDecisionReason': reason, 'additionalContext': reason}}
                    context += ('\n提交前静默使用 doc-update 核对实际暂存源码与文档，按本次范围同步并暂存；'
                                '运行 doc-commit-review.py prepare，展示文档差异，收到明确确认后 approve 并提交。')
                if context:
                    return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': context}}
            return {}
        context = instruction(root)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        context = '文档内部检查待恢复：' + type(exc).__name__ + '。先诊断并修复，不伪报已同步；日常状态不向用户播报。'
    if name == 'Stop':
        return recovery_record(root, event, context)
    if name == 'PreToolUse' and current[0] is not None:
        inspection = state_path(root).with_name('inspection.json')
        try:
            token = json.loads(inspection.read_text()).get('source') if inspection.exists() else None
        except (ValueError, OSError):
            token = None
        tool_input = json.dumps(event.get('tool_input', {}), ensure_ascii=False)
        maintenance = 'doc-workflow.py' in tool_input and bool(re.search(r'\b(inspect|complete)\b', tool_input))
        if (current[0] is None or token != current[0]) and not maintenance:
            return {'hookSpecificOutput': {'hookEventName': name, 'permissionDecision': 'deny',
                                          'permissionDecisionReason': context, 'additionalContext': context}}
    return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': context}}



def hook(event):
    result = _hook(event)
    name = event.get('hook_event_name')
    if name not in EVENTS:
        return result
    try:
        root = event_project(event)
        if not document_files(root):
            return result
        audit = state_path(root).with_name('observations.jsonl')
        if audit.is_symlink():
            raise ValueError('Policy journal must be a regular file.')
        audit.parent.mkdir(parents=True, exist_ok=True)
        decision = result.get('hookSpecificOutput', {}).get('permissionDecision')
        row = {'gate_id': GATE_ID, 'event': name, 'session_id': event.get('session_id'),
               'tool_use_id': event.get('tool_use_id'),
               'action_sha256': hashlib.sha256(json.dumps(
                   [event.get('tool_name'), event.get('tool_input')],
                   ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
               'decision': decision or result.get('decision') or 'continue',
               'at': datetime.now(timezone.utc).isoformat()}
        context = result.get('hookSpecificOutput', {}).get('additionalContext', '')
        if 'doc-context' in context and name == 'PreToolUse':
            row['triggered_skill'] = 'doc-context'
        if 'doc-update' in context and name in ('PreToolUse', 'PostToolUse'):
            row['triggered_update'] = 'doc-update'
        fd = os.open(audit, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Missing audit data never grants permission or invents a tool result.
        pass
    return result


def owned(entry):
    return entry.get('statusMessage') == GATE_ID or ('doc-workflow.py' in entry.get('command', '') and GATE_ID in entry.get('command', ''))


def registration(config):
    data = json.loads(json.dumps(config))
    command = shlex.join([sys.executable, str(HERE / 'doc-workflow.py'), 'hook', '--gate-id', GATE_ID])
    for event in EVENTS:
        groups = data.setdefault('hooks', {}).setdefault(event, [])
        entry = {'type': 'command', 'command': command, 'timeout': 60,
                 'statusMessage': HOOK_LABELS[event]}
        found = [(g, i) for g in groups for i, h in enumerate(g.get('hooks', [])) if owned(h)]
        if len(found) > 1:
            raise ValueError('Duplicate document hooks; preserve configuration for review.')
        if found:
            g, i = found[0]
            g['hooks'][i] = entry
        else:
            group = {'hooks': [entry]}
            if event != 'Stop':
                group['matcher'] = '.*'
            groups.append(group)
    labels = [h.get('statusMessage') for groups in data['hooks'].values()
              for group in groups for h in group.get('hooks', [])]
    for label in HOOK_LABELS.values():
        if labels.count(label) != 1:
            raise ValueError('Duplicate document hook name: ' + label)
    return data


def stage(config_dir):
    hooks_file, settings = config_dir / 'hooks.json', config_dir / 'config.toml'
    before = hooks_file.read_bytes() if hooks_file.exists() else None
    original = json.loads(before) if before is not None else {'hooks': {}}
    updated = registration(original)
    settings_before = settings.read_bytes() if settings.exists() else None
    text = settings_before.decode('utf-8') if settings_before is not None else ''
    expected = tomllib.loads(text)
    for event, groups in updated['hooks'].items():
        key = re.sub(r'(?<!^)(?=[A-Z])', '_', event).lower()
        for gi, group in enumerate(groups):
            for hi, entry in enumerate(group.get('hooks', [])):
                if not owned(entry):
                    continue
                identity = f'{hooks_file}:{key}:{gi}:{hi}'
                expected.setdefault('hooks', {}).setdefault('state', {}).setdefault(identity, {})['enabled'] = False
                lines = text.splitlines(keepends=True)
                starts = []
                for n, line in enumerate(lines):
                    if line.lstrip().startswith('['):
                        try:
                            if identity in tomllib.loads(line).get('hooks', {}).get('state', {}): starts.append(n)
                        except tomllib.TOMLDecodeError:
                            pass
                if not starts:
                    text = text.rstrip('\n') + '\n\n[hooks.state.' + json.dumps(identity) + ']\nenabled = false\n'
                else:
                    start = starts[0]
                    end = next((n for n in range(start + 1, len(lines)) if lines[n].lstrip().startswith('[')), len(lines))
                    enabled = []
                    for n in range(start + 1, end):
                        try:
                            if 'enabled' in tomllib.loads(lines[n]): enabled.append(n)
                        except tomllib.TOMLDecodeError:
                            pass
                    if enabled: lines[enabled[0]] = 'enabled = false\n'
                    else: lines.insert(start + 1, 'enabled = false\n')
                    text = ''.join(lines)
    if tomllib.loads(text) != expected:
        raise ValueError('Unrelated settings changed; registration refused.')
    backup = config_dir / 'skill-backups' / ('doc-silent-hooks-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, mode=0o700)
    for p in (hooks_file, settings):
        if p.exists():
            saved = backup / p.name
            saved.write_bytes(p.read_bytes())
            saved.chmod(0o600)
    if ((hooks_file.read_bytes() if hooks_file.exists() else None) != before or
            (settings.read_bytes() if settings.exists() else None) != settings_before):
        raise ValueError('Hook configuration changed during registration.')
    settings.write_text(text, encoding='utf-8')
    atomic_json(hooks_file, updated)
    return {'registered': len(EVENTS), 'enabled': False, 'host_verified': False,
            'gate_id': GATE_ID, 'backup': str(backup)}


def status(config_dir):
    path = config_dir / 'hooks.json'
    data = json.loads(path.read_text())
    states = tomllib.loads((config_dir / 'config.toml').read_text()).get('hooks', {}).get('state', {})
    entries = []
    for event, groups in data.get('hooks', {}).items():
        key = re.sub(r'(?<!^)(?=[A-Z])', '_', event).lower()
        for gi, group in enumerate(groups):
            for hi, item in enumerate(group.get('hooks', [])):
                if owned(item):
                    state = states.get(f'{path}:{key}:{gi}:{hi}', {})
                    entries.append({'event': event, 'name': item.get('statusMessage'), 'enabled': state.get('enabled'),
                                    'trust_record_present': bool(state.get('trusted_hash'))})
    return {'gate_id': GATE_ID, 'registered': len(entries), 'entries': entries,
            'note': 'Trust records alone do not prove the current command is trusted or native callbacks execute.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('hook', 'inspect', 'complete', 'register', 'status'))
    p.add_argument('--project', default='.')
    p.add_argument('--source')
    p.add_argument('--reason')
    p.add_argument('--gate-id', choices=(GATE_ID,), default=GATE_ID)
    p.add_argument('--config-dir', default=str(Path.home() / '.codex'))
    args = p.parse_args()
    if args.action == 'hook':
        print(json.dumps(hook(json.load(sys.stdin)), ensure_ascii=False))
    elif args.action == 'register':
        print(json.dumps(stage(Path(args.config_dir).expanduser().resolve()), ensure_ascii=False))
    elif args.action == 'status':
        print(json.dumps(status(Path(args.config_dir).expanduser().resolve()), ensure_ascii=False))
    else:
        root = project(args.project)
        if args.action == 'complete':
            complete(root, args.source, args.reason)
        else:
            print(json.dumps(inspect(root), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

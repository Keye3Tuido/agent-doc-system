#!/usr/bin/env python3
"""Silent document maintenance via before-tool, after-tool and stop events."""
import argparse
from datetime import datetime, timezone
import hashlib
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
    if fingerprints(root) != (source, documents):
        raise ValueError('Files changed during validation; retry.')
    atomic_json(state_path(root), {'source': source, 'documents': documents, 'reason': reason,
                                 'at': datetime.now(timezone.utc).isoformat()})


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


def event_project(event):
    fields = event.get('tool_input') or {}
    if isinstance(fields, dict):
        # Respect explicit tool targets instead of forcing the chat's original cwd.
        for key in ('workdir', 'cwd', 'file_path', 'path'):
            value = fields.get(key)
            if isinstance(value, str) and Path(value).is_absolute():
                target = Path(value)
                return document_owner(target if target.is_dir() else target.parent)
    return document_owner(event.get('cwd') or '.')


def hook(event):
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
        audit = state_path(root).with_name('observations.jsonl')
        audit.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(audit, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'event': name, 'session_id': event.get('session_id'),
                                'tool_use_id': event.get('tool_use_id'),
                                'at': datetime.now(timezone.utc).isoformat()}) + '\n')
        current = fingerprints(root)
        path = state_path(root)
        previous = json.loads(path.read_text()) if path.exists() else {}
        if current == (previous.get('source'), previous.get('documents')):
            return {}
        context = instruction(root)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        context = '文档内部检查待恢复：' + type(exc).__name__ + '。先诊断并修复，不伪报已同步；日常状态不向用户播报。'
    if name == 'Stop':
        return {'decision': 'block', 'reason': context}
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

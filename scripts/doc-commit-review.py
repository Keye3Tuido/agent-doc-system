#!/usr/bin/env python3
"""Optional reports and review records for staged documentation changes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def git(root, *args, optional=False, input_data=None):
    r = subprocess.run(['git', '-C', str(root), *args], capture_output=True, input=input_data)
    if r.returncode and not optional:
        raise ValueError(r.stderr.decode(errors='replace').strip())
    return r.stdout if r.returncode == 0 else b''


def docs(root, tree):
    if not tree:
        return []
    entries = []
    for row in git(root, 'ls-tree', '-rz', tree).split(b'\0'):
        if not row:
            continue
        info, raw = row.split(b'\t', 1)
        name = os.fsdecode(raw)
        if name == '.agent-docs/_index.md' or (name.startswith('.agent-docs/doc-library/') and name.endswith('.md')):
            mode, kind, oid = info.split()
            if mode == b'120000' or kind != b'blob':
                raise ValueError('Documentation must be regular files: ' + name)
            entries.append((name, oid.decode()))
    return entries


def snapshot(root):
    head = git(root, 'rev-parse', '--verify', 'HEAD', optional=True).decode().strip()
    tree = git(root, 'write-tree').decode().strip()
    digest = hashlib.sha256((str(root) + '\n' + head + '\n' + tree).encode()).hexdigest()
    return head, tree, digest


def validate(root, tree):
    # Validate index blobs, never the possibly different working-tree copy.
    entries = docs(root, tree)
    if not entries:
        return
    with tempfile.TemporaryDirectory(prefix='doc-commit-review-') as tmp:
        (Path(tmp) / '.agent-docs/doc-library/modules').mkdir(parents=True)
        for name, oid in entries:
            p = Path(tmp) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(git(root, 'cat-file', 'blob', oid))
        for name in ('doc-encoding-check.py', 'doc-format-check.py'):
            r = subprocess.run([sys.executable, str(HERE / name), tmp], capture_output=True, text=True)
            if r.returncode:
                raise ValueError(name + ':\n' + r.stdout + r.stderr)


def require_synced(root, tree):
    spec = importlib.util.spec_from_file_location('doc_workflow', HERE / 'doc-workflow.py')
    workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workflow)
    files = workflow.document_files(root)
    working = {str(p.relative_to(root)): p.read_bytes() for p in files if not p.is_symlink()}
    staged = {name: git(root, 'cat-file', 'blob', oid) for name, oid in docs(root, tree)}
    if working != staged:
        raise ValueError('文档同步结果尚未纳入本次暂存快照；按本次范围暂存文档后重试。')
    if not files:
        return
    path = workflow.state_path(root)
    state = json.loads(path.read_text()) if path.exists() else {}
    current = workflow.fingerprints(root)
    if current != (state.get('source'), state.get('documents')):
        raise ValueError('先静默核验并同步文档：运行 doc-workflow.py inspect，再核验源码并 complete；此步骤不请求用户批准。')


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        temp = Path(f.name)
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'approve', 'check'))
    p.add_argument('--project', default='.')
    p.add_argument('--digest')
    p.add_argument('--reason', help='Review conclusion, including why docs need no change when applicable')
    args = p.parse_args()
    root = Path(os.fsdecode(git(Path(args.project).resolve(), 'rev-parse', '--show-toplevel')).strip()).resolve()
    head, tree, digest = snapshot(root)
    managed = bool(docs(root, tree) or docs(root, head))
    if not managed and args.action == 'check':
        return
    require_synced(root, tree)
    location = os.fsdecode(git(root, 'rev-parse', '--git-path', 'agent-docs-commit-review')).strip()
    state_dir = Path(location)
    if not state_dir.is_absolute():
        state_dir = root / state_dir
    state = state_dir / 'review.json'
    report = state_dir / 'review.md'
    if args.action == 'prepare':
        validate(root, tree)
        base = head or git(root, 'hash-object', '-t', 'tree', '--stdin', input_data=b'').decode().strip()
        changes = git(root, 'diff', '--no-ext-diff', '--no-textconv', '--stat', base, tree).decode(errors='replace')
        doc_diff = git(root, 'diff', '--no-ext-diff', '--no-textconv', base, tree, '--', '.agent-docs/_index.md', '.agent-docs/doc-library').decode(errors='replace')
        source_diff = git(root, 'diff', '--no-ext-diff', '--no-textconv', base, tree, '--', '.', ':(exclude).agent-docs').decode(errors='replace')
        text = '# 提交文档审阅\n\n摘要：' + digest + '\n\n## 暂存变更\n\n```\n' + changes + '```\n\n## 文档差异\n\n```diff\n' + (doc_diff or '文档无变化；请核对源码并说明无需更新的依据。\n') + '```\n\n## 源码差异\n\n```diff\n' + source_diff + '```\n'
        if snapshot(root) != (head, tree, digest):
            raise ValueError('Index changed during review preparation; retry.')
        state_dir.mkdir(parents=True, exist_ok=True)
        report.write_text(text, encoding='utf-8')
        save(state, {'digest': digest, 'report_hash': hashlib.sha256(report.read_bytes()).hexdigest(), 'approved': False})
        print(json.dumps({'digest': digest, 'report': str(report)}, ensure_ascii=False))
        return
    if not state.exists():
        raise ValueError('提交前需审阅文档变化：先运行 doc-commit-review.py prepare --project ' + shlex.quote(str(root)))
    record = json.loads(state.read_text())
    if record.get('digest') != digest or not report.exists() or record.get('report_hash') != hashlib.sha256(report.read_bytes()).hexdigest():
        raise ValueError('暂存内容、HEAD 或审阅文件已变化，请重新 prepare 并审阅。')
    if args.action == 'approve':
        if args.digest != digest or not args.reason or not args.reason.strip():
            raise ValueError('需要当前完整摘要和审阅结论；收到用户对本次审阅的明确确认后才能记录。')
        validate(root, tree)
        record.update(approved=True, reason=args.reason.strip())
        save(state, record)
    else:
        if record.get('approved') is not True:
            raise ValueError('文档审阅尚未确认：' + str(report))
        validate(root, tree)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

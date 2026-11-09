#!/usr/bin/env python3
"""Optional source and documentation verification records; no event hooks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('inspect', 'complete', 'status'))
    p.add_argument('--project', default='.')
    p.add_argument('--source')
    p.add_argument('--reason')
    args = p.parse_args()
    if args.action == 'status':
        print(json.dumps({'mode': 'AGENTS.md', 'hooks_supported': False}))
        return
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

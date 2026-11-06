#!/usr/bin/env python3
"""Exercise the commit boundary with real Git repositories and staged objects."""
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('doc-commit-review.py')


class CommitReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.write('.agent-docs/_index.md', '---\nschema_version: 7\nproject_config:\n  initial_bootstrap_done: false\n---\n')
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n测试模块。\n')
        self.write('code.txt', 'one\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def run_cli(self, action, *args):
        return subprocess.run([sys.executable, str(SCRIPT), action, '--project', str(self.root), *args], capture_output=True, text=True)

    def prepare(self):
        self.sync(self.root)
        r = self.run_cli('prepare')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def sync(self, root):
        spec = importlib.util.spec_from_file_location('doc_workflow', SCRIPT.with_name('doc-workflow.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        if m.document_files(root):
            token = m.inspect(root)['source']
            m.complete(root, token, 'Isolated test: verified source and documentation')

    def approve(self, report):
        r = self.run_cli('approve', '--digest', report['digest'], '--reason', '已核对代码，本次不影响文档描述。')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_commit_requires_review_and_rejects_changed_index(self):
        self.write('code.txt', 'two\n')
        self.git('add', '.')
        self.assertNotEqual(self.run_cli('check').returncode, 0)
        report = self.prepare()
        self.assertIn('code.txt', Path(report['report']).read_text())
        self.approve(report)
        self.assertEqual(self.run_cli('check').returncode, 0)
        self.write('code.txt', 'three\n')
        self.git('add', '.')
        self.assertNotEqual(self.run_cli('check').returncode, 0)

    def test_staged_bad_document_is_not_hidden_by_worktree_fix(self):
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 1\n---\n')
        self.git('add', '.')
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n合法。\n')
        self.sync(self.root)
        result = self.run_cli('prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('暂存', result.stderr)

    def test_staged_schema_validation_rejects_invalid_blobs(self):
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 1\n---\n')
        self.git('add', '.agent-docs')
        spec = importlib.util.spec_from_file_location('commit_review', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.validate(self.root, self.git('write-tree'))

    def test_report_contains_doc_diff_and_approval_is_bound_to_head(self):
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n新描述。\n')
        self.git('add', '.')
        report = self.prepare()
        self.assertIn('+新描述。', Path(report['report']).read_text())
        self.approve(report)
        self.git('commit', '-qm', 'change')
        self.assertNotEqual(self.run_cli('check').returncode, 0)

    def test_real_hook_blocks_commit_and_preserves_existing_hook(self):
        old = self.root / '.git/hooks/pre-commit'
        old.write_text('#!/bin/sh\nprintf ran > .git/hook-ran\n')
        old.chmod(0o755)
        self.assertEqual(self.run_cli('install').returncode, 0)
        wrapper = old.read_bytes()
        self.assertEqual(self.run_cli('install').returncode, 0)
        self.assertEqual(old.read_bytes(), wrapper)
        self.write('code.txt', 'two\n')
        self.git('add', '.')
        r = subprocess.run(['git', '-C', str(self.root), 'commit', '-qm', 'blocked'], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.root / '.git/hook-ran').exists())
        self.approve(self.prepare())
        self.git('commit', '-qm', 'allowed')
        self.assertEqual((self.root / '.git/hook-ran').read_text(), 'ran')

    def test_custom_hooks_path_is_not_modified(self):
        self.git('config', 'core.hooksPath', 'custom-hooks')
        self.assertNotEqual(self.run_cli('install').returncode, 0)
        self.assertFalse((self.root / 'custom-hooks').exists())

    def test_existing_hook_cannot_restage_unreviewed_changes(self):
        old = self.root / '.git/hooks/pre-commit'
        old.write_text('#!/bin/sh\nprintf restaged > code.txt\ngit add code.txt\n')
        old.chmod(0o755)
        self.assertEqual(self.run_cli('install').returncode, 0)
        self.write('code.txt', 'two\n')
        self.git('add', '.')
        self.approve(self.prepare())
        r = subprocess.run(['git', '-C', str(self.root), 'commit', '-qm', 'blocked'], capture_output=True)
        self.assertNotEqual(r.returncode, 0)

    def test_changed_report_and_missing_reason_are_rejected(self):
        self.write('code.txt', 'two\n')
        self.git('add', '.')
        report = self.prepare()
        self.assertNotEqual(self.run_cli('approve', '--digest', report['digest']).returncode, 0)
        self.approve(report)
        Path(report['report']).write_text('tampered\n')
        self.assertNotEqual(self.run_cli('check').returncode, 0)

    def test_first_commit_is_reviewed(self):
        self.git('update-ref', '-d', 'HEAD')
        self.assertNotEqual(self.run_cli('check').returncode, 0)
        self.approve(self.prepare())
        self.assertEqual(self.run_cli('check').returncode, 0)

    def test_first_commit_prepare_does_not_read_terminal_stdin(self):
        self.git('update-ref', '-d', 'HEAD')
        self.sync(self.root)
        process = subprocess.Popen([sys.executable, str(SCRIPT), 'prepare', '--project', str(self.root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            self.fail('prepare waited for stdin instead of using an empty tree')
        stdout, stderr = process.communicate()
        self.assertEqual(process.returncode, 0, stderr)
        self.assertIn('digest', json.loads(stdout))

    def test_shared_hook_uses_current_worktree_not_install_directory(self):
        self.assertEqual(self.run_cli('install').returncode, 0)
        other = self.root / 'other-worktree'
        self.git('worktree', 'add', '-qb', 'other', str(other))
        (other / 'code.txt').write_text('changed in other\n')
        subprocess.run(['git', '-C', str(other), 'add', 'code.txt'], check=True)
        self.sync(other)
        r = subprocess.run([sys.executable, str(SCRIPT), 'prepare', '--project', str(other)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

        digest = json.loads(r.stdout)['digest']
        r = subprocess.run([sys.executable, str(SCRIPT), 'approve', '--project', str(other), '--digest', digest, '--reason', 'Verified other worktree'], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run(['git', '-C', str(other), 'commit', '-qm', 'other'], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_synchronized_document_changes_must_be_staged(self):
        self.write('code.txt', 'two\n')
        self.git('add', 'code.txt')
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n更新为 two。\n')
        self.sync(self.root)
        result = self.run_cli('prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('暂存', result.stderr)
        self.git('add', '.agent-docs')
        self.sync(self.root)
        self.assertEqual(self.run_cli('prepare').returncode, 0)

    def test_prepare_requires_completed_document_sync(self):
        self.write('code.txt', 'two\n')
        self.git('add', '.')
        result = self.run_cli('prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('inspect', result.stderr)
        self.sync(self.root)
        self.assertEqual(self.run_cli('prepare').returncode, 0)

    def test_missing_docs_does_not_block_unmanaged_repo(self):
        self.git('rm', '-r', '.agent-docs')
        self.assertNotEqual(self.run_cli('check').returncode, 0)
        self.approve(self.prepare())
        self.git('commit', '-qm', 'remove library')
        self.assertEqual(self.run_cli('check').returncode, 0)


if __name__ == '__main__':
    unittest.main()

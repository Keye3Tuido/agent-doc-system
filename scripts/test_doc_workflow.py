#!/usr/bin/env python3
"""Silent hook workflow tests; all writes stay in temporary repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

HERE = Path(__file__).resolve().parent


class Workflow(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('doc_workflow', HERE / 'doc-workflow.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.write('.agent-docs/_index.md', '---\nschema_version: 7\nproject_config:\n  initial_bootstrap_done: false\n---\n')
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n测试。\n')
        self.write('src.txt', 'one\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def event(self, name, **kw):
        return self.m.hook({'hook_event_name': name, 'cwd': str(self.root), 'session_id': 'isolated', **kw})

    def complete(self):
        token = self.m.inspect(self.root)['source']
        self.m.complete(self.root, token, '已核验相关源码与正文，更新已完成。')

    def test_initial_check_is_model_context_not_user_status(self):
        out = self.event('PreToolUse', tool_name='read_file', tool_input={'path': 'src.txt'})
        self.assertIn('additionalContext', out['hookSpecificOutput'])
        self.assertNotIn('systemMessage', out)
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
        self.m.inspect(self.root)
        repair = self.event('PreToolUse', tool_name='read_file', tool_input={'path': 'src.txt'})
        self.assertNotIn('permissionDecision', repair['hookSpecificOutput'])
        self.complete()
        self.assertEqual(self.event('PreToolUse'), {})

    def test_actual_write_queues_sync_and_blocks_stop_until_complete(self):
        self.complete()
        self.write('src.txt', 'two\n')
        out = self.event('PostToolUse', tool_response={'exit_code': 1})
        self.assertIn('additionalContext', out['hookSpecificOutput'])
        self.assertEqual(self.event('Stop')['decision'], 'block')
        self.complete()
        self.assertEqual(self.event('Stop'), {})

    def test_same_bytes_and_read_only_work_do_not_reopen_sync(self):
        self.complete()
        self.write('src.txt', 'one\n')
        self.assertEqual(self.event('PostToolUse'), {})
        self.assertEqual(self.event('Stop'), {})

    def test_new_files_staged_changes_and_document_changes_invalidate(self):
        self.complete()
        self.write('new.txt', 'new\n')
        self.assertEqual(self.event('Stop')['decision'], 'block')
        self.complete()
        self.git('add', 'new.txt')
        self.assertEqual(self.event('Stop')['decision'], 'block')
        self.complete()
        self.write('.agent-docs/doc-library/main-module.md', '---\nschema_version: 7\n---\n\n## 定位\n\n变更。\n')
        self.assertEqual(self.event('Stop')['decision'], 'block')

    def test_old_source_token_cannot_complete_new_source(self):
        token = self.m.fingerprints(self.root)[0]
        self.write('src.txt', 'two\n')
        with self.assertRaises(ValueError):
            self.m.complete(self.root, token, 'old review')

    def test_missing_library_does_not_block(self):
        self.git('rm', '-r', '.agent-docs')
        self.assertEqual(self.event('Stop'), {})

    def test_silent_registration_preserves_other_hook_positions(self):
        config = {'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'statusMessage': 'other', 'command': 'other'}]}]}}
        updated = self.m.registration(config)
        self.assertEqual(updated['hooks']['PreToolUse'][0], config['hooks']['PreToolUse'][0])
        self.assertEqual(updated, self.m.registration(updated))
        own = [h for gs in updated['hooks'].values() for g in gs for h in g['hooks'] if self.m.owned(h)]
        self.assertEqual(len(own), 3)
        self.assertTrue(all(not h.get('statusMessage') for h in own))

    def test_native_staging_preserves_other_policy_and_does_not_grant_trust(self):
        config = self.root / 'config'
        config.mkdir()
        path = config / 'hooks.json'
        original = {'hooks': {'PreToolUse': [{'hooks': [{'command': 'foreign', 'statusMessage': 'foreign'}]}]}}
        path.write_text(json.dumps(original))
        identity = f'{path}:pre_tool_use:0:0'
        settings = config / 'config.toml'
        settings.write_text('[hooks.state.' + json.dumps(identity) + ']\nenabled = true\ntrusted_hash = "keep"\n')
        result = self.m.stage(config)
        updated = json.loads(path.read_text())
        self.assertEqual(updated['hooks']['PreToolUse'][0], original['hooks']['PreToolUse'][0])
        states = tomllib.loads(settings.read_text())['hooks']['state']
        self.assertEqual(states[identity], {'enabled': True, 'trusted_hash': 'keep'})
        self.assertEqual(len(states), 4)
        for key, value in states.items():
            if key != identity:
                self.assertEqual(value, {'enabled': False})
        self.assertFalse(result['enabled'])
        self.assertEqual(self.m.status(config)['registered'], 3)

    def test_registration_bootstraps_missing_native_files(self):
        config = self.root / 'new-config'
        self.m.stage(config)
        self.assertEqual(self.m.status(config)['registered'], 3)
        self.assertTrue(all(e['enabled'] is False for e in self.m.status(config)['entries']))

    def test_corrupt_state_requests_internal_recovery(self):
        self.m.state_path(self.root).parent.mkdir(parents=True)
        self.m.state_path(self.root).write_text('bad json')
        self.assertEqual(self.event('Stop')['decision'], 'block')

    def test_document_error_allows_repair_but_prevents_completion(self):
        link = self.root / '.agent-docs/doc-library/link.md'
        link.symlink_to(self.root / 'src.txt')
        result = self.event('PreToolUse', tool_name='apply_patch', tool_input={'patch': 'delete link.md'})
        self.assertNotIn('permissionDecision', result['hookSpecificOutput'])
        self.assertEqual(self.event('Stop')['decision'], 'block')
        link.unlink()
        self.complete()
        self.assertEqual(self.event('Stop'), {})

    def test_submodule_absolute_target_uses_parent_document_library(self):
        child = self.root / 'child'
        subprocess.run(['git', 'init', '-q', str(child)], check=True)
        (child / 'source').write_text('one')
        result = self.event('PreToolUse', tool_input={'file_path': str(child / 'source')})
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.m.event_project({'cwd': str(child)}), self.root.resolve())

    def test_initialized_submodule_changes_are_observed(self):
        child = self.root / 'child'
        subprocess.run(['git', 'init', '-q', str(child)], check=True)
        for key, val in [('user.name', 'Test'), ('user.email', 'test@example.invalid')]:
            subprocess.run(['git', '-C', str(child), 'config', key, val], check=True)
        (child / 'source').write_text('one')
        subprocess.run(['git', '-C', str(child), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(child), 'commit', '-qm', 'base'], check=True)
        self.git('add', 'child')
        self.complete()
        (child / 'source').write_text('two')
        self.assertEqual(self.event('Stop')['decision'], 'block')


if __name__ == '__main__':
    unittest.main()

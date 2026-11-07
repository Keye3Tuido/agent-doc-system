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

    def test_verified_context_loads_once_and_commit_hook_is_automatic(self):
        self.complete()
        hook = self.root / '.git/hooks/pre-commit'
        self.assertTrue(hook.is_file())
        first = self.event('PreToolUse', tool_name='Bash', tool_input={'command':'cat src.txt'}, tool_use_id='first')
        self.assertIn('doc-context', first['hookSpecificOutput']['additionalContext'])
        self.assertIn('测试。', first['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.event('PreToolUse', tool_name='Bash', tool_input={'command':'cat src.txt'}, tool_use_id='again'), {})
        before = hook.read_bytes()
        self.m.ensure_commit_gate(self.root)
        self.assertEqual(hook.read_bytes(), before)
        self.write('src.txt', 'changed')
        self.git('add', 'src.txt')
        result = subprocess.run(['git','-C',str(self.root),'commit','-qm','unreviewed'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_commit_triggers_doc_update_and_host_tools_do_not_touch_project(self):
        self.complete()
        result = self.event('PreToolUse', tool_name='Bash', tool_input={'command':'git commit -m test'}, tool_use_id='commit')
        self.assertIn('doc-update', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.event('PreToolUse', tool_name='mcp__codex_app__read_thread', tool_input={}), {})

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

    def test_named_registration_preserves_other_hook_positions(self):
        config = {'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'statusMessage': 'other', 'command': 'other'}]}]}}
        updated = self.m.registration(config)
        self.assertEqual(updated['hooks']['PreToolUse'][0], config['hooks']['PreToolUse'][0])
        self.assertEqual(updated, self.m.registration(updated))
        own = [h for gs in updated['hooks'].values() for g in gs for h in g['hooks'] if self.m.owned(h)]
        self.assertEqual(len(own), 3)
        labels = {event: next(h['statusMessage'] for g in updated['hooks'][event]
                             for h in g['hooks'] if self.m.owned(h))
                  for event in ('PreToolUse', 'PostToolUse', 'Stop')}
        self.assertEqual(labels, {'PreToolUse': 'agent-doc-system-silent-workflow/PreToolUse',
                                  'PostToolUse': 'agent-doc-system-silent-workflow/PostToolUse',
                                  'Stop': 'agent-doc-system-silent-workflow/Stop'})

    def test_registration_refuses_foreign_name_collision_without_modifying_input(self):
        name = 'agent-doc-system-silent-workflow/PreToolUse'
        config = {'hooks': {'Stop': [{'hooks': [{'command': 'foreign', 'statusMessage': name}]}]}}
        before = json.dumps(config, sort_keys=True)
        with self.assertRaisesRegex(ValueError, 'Duplicate document hook name'):
            self.m.registration(config)
        self.assertEqual(json.dumps(config, sort_keys=True), before)

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


    def test_policy_journal_records_exact_denial_without_message_contents(self):
        fields={'path':'src.txt'}
        result=self.event('PreToolUse',tool_name='read_file',tool_input=fields,tool_use_id='blocked-read')
        rows=[json.loads(line) for line in self.m.state_path(self.root).with_name('observations.jsonl').read_text().splitlines()]
        receipt=rows[-1]
        self.assertEqual(receipt['gate_id'],self.m.GATE_ID)
        self.assertEqual(receipt['decision'],'deny')
        self.assertEqual(receipt['tool_use_id'],'blocked-read')
        import hashlib
        expected=hashlib.sha256(json.dumps(['read_file',fields],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        self.assertEqual(receipt['action_sha256'],expected)
        self.assertNotIn('tool_input',receipt)


    def test_global_skills_and_exact_tv_control_do_not_depend_on_project_docs(self):
        import shlex
        runtime = Path.home() / '.codex/tv/process_gate.py'
        command = shlex.join(['python3', str(runtime), '--session', 'isolated', '--request', '{"action":"inspect"}'])
        event = dict(tool_name='Bash', tool_input={'command': command})
        self.assertEqual(self.event('PreToolUse', **event), {})
        bad = command + '; cat src.txt'
        self.assertEqual(self.event('PreToolUse', tool_name='Bash', tool_input={'command':bad})['hookSpecificOutput']['permissionDecision'], 'deny')
        wrong = command.replace('--session isolated', '--session other')
        self.assertEqual(self.event('PreToolUse', tool_name='Bash', tool_input={'command':wrong})['hookSpecificOutput']['permissionDecision'], 'deny')
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill = home / '.agents/skills/test/SKILL.md'
            skill.parent.mkdir(parents=True); skill.write_text('test')
            from unittest.mock import patch
            with patch.object(self.m.Path, 'home', return_value=home):
                self.assertEqual(self.event('PreToolUse', tool_name='Bash', tool_input={'command':'cat ' + str(skill)}), {})
                self.assertEqual(self.event('PreToolUse', tool_name='Bash', tool_input={'command':'cat ' + str(skill) + ' src.txt'})['hookSpecificOutput']['permissionDecision'], 'deny')

if __name__ == '__main__':
    unittest.main()

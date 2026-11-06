#!/usr/bin/env python3
"""Behavioral tests use isolated Git projects and runtime state."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('doc-gate.py')


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.project = self.base / 'project'
        self.project.mkdir()
        self.runtime = self.base / 'runtime'
        self.config = self.base / 'config'
        self.config.mkdir(); self.runtime.mkdir()
        spec = importlib.util.spec_from_file_location('installer_fixture', SCRIPT.with_name('doc-gate-install.py'))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.host_identity = lambda: {'path': '/synthetic-test-host/codex'}
        mappings, digest = installer.merged({}, self.config, self.runtime)
        (self.config / 'hooks.json').write_text(json.dumps(mappings))
        (self.config / 'config.toml').write_text('\n'.join(
            '[hooks.state.' + json.dumps(i) + ']\nenabled = true\ntrusted_hash = "synthetic-test-only"'
            for i in installer.locations(mappings, self.config / 'hooks.json')))
        fixture_spec = importlib.util.spec_from_file_location('adapter_test_helpers', SCRIPT.with_name('test_doc_gate_install.py'))
        fixtures = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixtures)
        fixtures.fixture_adapter(installer, self.config, self.runtime)
        # Synthetic native validation is confined to this temporary test runtime.
        (self.runtime / 'native-verification.json').write_text(json.dumps({
            'binding': installer.binding(self.runtime), 'nonce': 'fixture',
            'effects': ['session_context', 'prompt_context', 'write', 'deny', 'stop', 'continued', 'approval'],
            'confirmed_prompt_sha256': hashlib.sha256('确认文档门限验证 fixture'.encode()).hexdigest()}))
        self.git('init', '-q')
        self.git('config', 'advice.addEmbeddedRepo', 'false')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.docs = self.project / '.agent-docs'
        (self.docs / 'doc-library/modules').mkdir(parents=True)
        (self.docs / '_index.md').write_text('---\nschema_version: 7\nproject_config: {}\n---\n# Index\n')
        (self.docs / 'doc-library/main-module.md').write_text('---\nschema_version: 7\n---\n# Main\n\n## 定位\nFixture application.\n')
        (self.project / 'main.py').write_text('value = 1\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.event('UserPromptSubmit', prompt='start')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.project), *args], text=True).strip()

    def cli(self, *args, event=None, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPT), '--runtime', str(self.runtime), *args],
                                input=json.dumps(event) if event else None, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout)

    def event(self, name, **kwargs):
        data = {'hook_event_name': name, 'session_id': 'conversation', 'turn_id': 'turn-1',
                'cwd': str(self.project), 'tool_use_id': 'call-1', 'tool_name': 'Bash',
                'tool_input': {'command': 'python change.py'}}
        data.update(kwargs)
        return self.cli('hook', event=data)

    def status(self):
        return self.cli('status', '--project', str(self.project), '--session', 'conversation')

    def write_source(self):
        self.event('PreToolUse')
        (self.project / 'main.py').write_text('value = 2\n')
        return self.event('PostToolUse', tool_response={'exit_code': 0})

    def test_user_prompt_and_compaction_receive_real_document_content(self):
        for name in ('UserPromptSubmit', 'SessionStart'):
            result = self.event(name, prompt='解释项目架构', source='compact')
            context = result['hookSpecificOutput']['additionalContext']
            self.assertIn('Fixture application.', context)
            self.assertIn('doc-context', context)

    def test_direct_cli_context_cannot_bypass_missing_native_gate(self):
        config = self.base / 'missing-host-config'
        result = subprocess.run([sys.executable, str(SCRIPT), '--runtime', str(config), 'context', '--project', str(self.project),
                                 '--session', 'conversation'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('not ready', result.stdout)

    def test_missing_readiness_blocks_write_but_allows_status_and_repair_diagnostics(self):
        (self.runtime / 'native-verification.json').unlink()
        output = self.event('PreToolUse', tool_input={'command': 'python change.py'})
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('not ready', output['hookSpecificOutput']['permissionDecisionReason'])
        self.assertIsNone(self.status()['pending'])
        for command in ('git --no-pager status',
                        str(sys.executable) + ' ' + str(SCRIPT.with_name('doc-gate-install.py')) + ' --require-ready',
                        str(sys.executable) + ' ' + str(SCRIPT.with_name('doc-gate-install.py')) + ' --stage-disabled',
                        str(sys.executable) + ' ' + str(SCRIPT.with_name('doc-sync-system.py')) + ' --dry-run'):
            output = self.event('PreToolUse', tool_input={'command': command})
            self.assertNotIn('permissionDecision', output.get('hookSpecificOutput', {}))

    def test_isolated_probe_collects_gate_effects_before_native_confirmation(self):
        spec = importlib.util.spec_from_file_location('probe_installer', SCRIPT.with_name('doc-gate-install.py'))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.host_identity = lambda: {'path': '/synthetic-test-host/codex'}
        probe = installer.start_verification(self.runtime, 'conversation')
        self.project = Path(probe['project'])
        self.docs = self.project / '.agent-docs'
        self.event('SessionStart')
        self.event('UserPromptSubmit', prompt='verify context')
        self.event('PreToolUse')
        (self.project / 'probe.txt').write_text('after\n')
        self.event('PostToolUse')
        output = self.event('PreToolUse')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual((self.project / 'probe.txt').read_text(), 'after\n')
        self.assertEqual(self.event('Stop')['decision'], 'block')
        self.event('PreToolUse', tool_input={'command': 'git --no-pager status'})
        pending = self.status()['pending']
        path = self.base / 'probe-review.json'
        relative = '.agent-docs/doc-library/main-module.md'
        path.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': relative, 'action': 'update', 'reason': 'Reflect the verified probe responsibility.',
             'new_content': (self.project / relative).read_text().replace('Native verification fixture.', 'Native verification fixture and approval test.')}] }))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        pending = self.status()['pending']
        for block in pending['proposal']['blocks']:
            self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + block['sha256'][:12])
        self.assertIsNone(self.status()['pending'])
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            installer.require_ready(self.runtime)
        self.event('UserPromptSubmit', prompt='确认文档门限验证 ' + probe['nonce'])
        self.assertTrue(installer.require_ready(self.runtime)['ready'])

    def test_new_probe_chat_binds_its_actual_session_from_session_start(self):
        spec = importlib.util.spec_from_file_location('unbound_probe_installer', SCRIPT.with_name('doc-gate-install.py'))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.host_identity = lambda: {'path': '/synthetic-test-host/codex'}
        probe = installer.start_verification(self.runtime, None)
        self.project = Path(probe['project'])
        output = self.event('SessionStart', session_id='new-real-session')
        self.assertIn(probe['nonce'], output['hookSpecificOutput']['additionalContext'])
        self.assertEqual(installer.verification(self.runtime)['session'], 'new-real-session')

    def test_delete_proposal_waits_for_exact_confirmation_and_does_not_recur(self):
        relative = '.agent-docs/doc-library/modules/orphan.md'
        path = self.project / relative
        path.write_text('---\nschema_version: 7\narchived: true\n---\n# Orphan\n')
        pending = self.cli('begin', '--project', str(self.project), '--session', 'conversation',
                           '--document', relative)['pending']
        review = self.base / 'delete-review.json'
        review.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': relative, 'action': 'delete', 'reason': 'User selected this orphaned archive for removal.'}]}))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(review))
        self.event('UserPromptSubmit', prompt='yes')
        self.assertTrue(path.exists())
        pending = self.status()['pending']
        for block in pending['proposal']['blocks']:
            self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + block['sha256'][:12])
        self.assertFalse(path.exists())
        self.assertIsNone(self.status()['pending'])
        self.event('PreToolUse', tool_input={'command': 'git --no-pager status'})
        self.event('PostToolUse')
        self.assertIsNone(self.status()['pending'])

    def test_rename_interrupted_after_delete_resumes_without_losing_new_document(self):
        old_relative = '.agent-docs/doc-library/modules/old.md'
        new_relative = '.agent-docs/doc-library/modules/new.md'
        old_path, new_path = self.project / old_relative, self.project / new_relative
        text = '---\nschema_version: 7\nrepo: https://github.com/example/module.git\nbranch: main\ncommit: ' + 'a' * 40 + '\n---\n# Module\n'
        old_path.write_text(text)
        pending = self.cli('begin', '--project', str(self.project), '--session', 'conversation',
                           '--document', old_relative, '--document', new_relative)['pending']
        review = self.base / 'rename-review.json'
        review.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': old_relative, 'action': 'delete', 'reason': 'Move this complete module to its verified canonical path.'},
            {'document': new_relative, 'action': 'update', 'reason': 'Preserve the module at its verified canonical path.', 'new_content': text}]}))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(review))
        spec = importlib.util.spec_from_file_location('rename_gate_fixture', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gate = module.Gate(self.runtime, self.project, 'conversation')
        state = gate.load()
        state['pending']['approved_sha256'] = state['pending']['proposal']['sha256']
        gate.save(state)
        real_mkstemp = module.tempfile.mkstemp
        def interrupt_new_file(*args, **kwargs):
            if kwargs.get('prefix') == '.doc-apply-':
                raise RuntimeError('interrupt after deletion')
            return real_mkstemp(*args, **kwargs)
        with mock.patch.object(module.tempfile, 'mkstemp', side_effect=interrupt_new_file):
            with self.assertRaises(RuntimeError):
                gate.apply(state)
        self.assertFalse(old_path.exists())
        self.assertFalse(new_path.exists())
        self.event('PostToolUse')
        self.assertEqual(self.status()['pending']['status'], 'applying')
        self.cli('apply', '--project', str(self.project), '--session', 'conversation')
        self.assertEqual(new_path.read_text(), text)
        self.assertFalse(old_path.exists())
        self.assertIsNone(self.status()['pending'])

    def test_initial_library_creation_uses_proposal_before_index_exists(self):
        import shutil
        contents = {str(p.relative_to(self.project)): p.read_text() for p in
                    (self.docs / '_index.md', self.docs / 'doc-library/main-module.md')}
        shutil.rmtree(self.docs)
        args = [item for relative in contents for item in ('--document', relative)]
        pending = self.cli('begin', '--project', str(self.project), '--session', 'conversation', *args)['pending']
        review = self.base / 'init-review.json'
        review.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': r, 'action': 'update', 'reason': 'Initialize approved project documentation.', 'new_content': text}
            for r, text in contents.items()]}))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(review))
        self.assertFalse((self.docs / '_index.md').exists())
        pending = self.status()['pending']
        for block in pending['proposal']['blocks']:
            self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + block['sha256'][:12])
        for relative, text in contents.items():
            self.assertEqual((self.project / relative).read_text(), text)

    def test_encoding_repair_can_propose_readable_diff_for_invalid_utf8(self):
        relative = '.agent-docs/doc-library/main-module.md'
        (self.project / relative).write_bytes(b'# broken \xff\n')
        pending = self.cli('begin', '--project', str(self.project), '--session', 'conversation', '--document', relative)['pending']
        review = self.base / 'encoding-review.json'
        review.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': relative, 'action': 'update', 'reason': 'Restore the verified text using UTF-8.',
             'new_content': '---\nschema_version: 7\n---\n# Main\n'}]}))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(review))
        self.assertIn('\\xff', (self.docs / '.tmp/pending-review.md').read_text())

    def test_unknown_module_scope_loads_all_active_docs_and_excludes_archives(self):
        modules = self.docs / 'doc-library/modules'
        for name, extra in [('active', ''), ('archive', 'archived: true\n')]:
            (modules / (name + '.md')).write_text('---\nschema_version: 7\n' + extra + '---\n# ' + name + '\n')
        context = self.event('UserPromptSubmit', prompt='分析调用关系')['hookSpecificOutput']['additionalContext']
        self.assertIn('# active', context)
        self.assertNotIn('# archive', context)

    def test_success_and_failed_tools_both_enqueue_actual_writes(self):
        self.event('PreToolUse')
        (self.project / 'main.py').write_text('partially changed\n')
        self.event('PostToolUse', tool_response={'exit_code': 1})
        state = self.status()
        self.assertEqual(state['pending']['paths'], ['main.py'])
        self.assertEqual(state['pending']['status'], 'needs_review')
        self.assertGreaterEqual(state['update_checks'], 1)
        self.assertIn('doc_update', state['pending'])

    def test_read_and_noop_write_do_not_create_review_debt(self):
        self.event('PreToolUse')
        (self.project / 'main.py').write_text('value = 1\n')
        self.event('PostToolUse')
        self.assertIsNone(self.status()['pending'])

    def test_pending_review_blocks_unknown_commands_and_commit_but_allows_reading(self):
        self.write_source()
        for command in ('git commit -am change', 'python arbitrary.py'):
            output = self.event('PreToolUse', tool_input={'command': command}, tool_use_id=command)
            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.event('PreToolUse', tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'}, tool_use_id='read'), {})

    def test_no_change_review_is_bound_to_actual_source_and_doc_hashes(self):
        self.write_source()
        pending = self.status()['pending']
        review = self.base / 'review.json'
        review.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': '.agent-docs/doc-library/main-module.md', 'action': 'unchanged',
             'reason': 'Only an internal value changed; documented interface and flow are unchanged.'}]}))
        self.cli('review', '--project', str(self.project), '--session', 'conversation', '--file', str(review))
        self.assertIsNone(self.status()['pending'])
        self.assertEqual(self.status()['last_review']['status'], 'reviewed_no_change')

    def test_stale_review_does_not_clear_new_writes(self):
        self.write_source()
        change = self.status()['pending']['id']
        (self.project / 'main.py').write_text('value = 3\n')
        review = self.base / 'review.json'
        review.write_text(json.dumps({'change_id': change, 'decisions': [
            {'document': '.agent-docs/doc-library/main-module.md', 'action': 'unchanged', 'reason': 'Internal detail.'}]}))
        self.cli('review', '--project', str(self.project), '--session', 'conversation', '--file', str(review), expected=2)
        self.assertIsNotNone(self.status()['pending'])

    def test_missing_library_warns_without_claiming_context_loaded(self):
        (self.docs / '_index.md').unlink()
        output = self.event('UserPromptSubmit', prompt='架构')
        context = output['hookSpecificOutput']['additionalContext']
        self.assertIn('/doc-init', context)
        self.assertNotIn('Fixture application.', context)

    def test_unknown_post_event_without_pre_snapshot_is_recorded_not_marked_clean(self):
        output = self.event('PostToolUse')
        self.assertIn('缺少执行前快照', output['systemMessage'])
        self.assertEqual(self.status()['observation_status'], 'unknown')

    def test_conversation_isolation_and_cwd_switch(self):
        self.write_source()
        other = self.event('PreToolUse', session_id='other', tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'})
        self.assertEqual(other, {})
        nested = self.project / 'nested'
        nested.mkdir()
        self.assertEqual(self.event('PreToolUse', cwd=str(nested), tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'}), {})

    def test_symlink_document_outside_project_is_rejected(self):
        external = self.base / 'outside.md'
        external.write_text('private external text')
        (self.docs / 'doc-library/modules/escape.md').symlink_to(external)
        output = self.event('UserPromptSubmit', prompt='架构')
        self.assertNotIn('private external text', json.dumps(output))
        self.assertIn('不可用', json.dumps(output, ensure_ascii=False))

    def proposal(self, text=None):
        pending = self.status()['pending']
        path = self.base / 'review.json'
        text = text or '---\nschema_version: 7\n---\n# Main\n\n## 定位\nApplication with value 2.\n'
        path.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': '.agent-docs/doc-library/main-module.md', 'action': 'update',
             'reason': 'The documented application behavior changed.', 'new_content': text}]}))
        return path

    def test_recovery_observes_write_without_post_callback(self):
        self.event('UserPromptSubmit', prompt='start')
        self.event('PreToolUse')
        (self.project / 'main.py').write_text('unreported write\n')
        self.event('SessionStart', source='compact')
        self.assertEqual(self.status()['pending']['paths'], ['main.py'])

    def test_repeated_pre_does_not_regenerate_change_id(self):
        self.event('UserPromptSubmit', prompt='start')
        (self.project / 'main.py').write_text('external write\n')
        self.event('PreToolUse', tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'})
        first = self.status()['pending']['id']
        self.event('PreToolUse', tool_input={'command': 'git --no-pager status'})
        self.assertEqual(self.status()['pending']['id'], first)

    def test_temp_review_patch_allowed_but_source_patch_denied(self):
        self.write_source()
        patch = '*** Begin Patch\n*** Add File: .agent-docs/.tmp/review.json\n+{}\n*** End Patch\n'
        self.assertEqual(self.event('PreToolUse', tool_name='apply_patch', tool_input={'command': patch}), {})
        patch = patch.replace('.agent-docs/.tmp/review.json', 'main.py')
        out = self.event('PreToolUse', tool_name='apply_patch', tool_input={'command': patch})
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_pending_review_allows_fixed_readonly_diagnostics_and_scratch_normalization(self):
        import shlex
        self.write_source()
        for name in ('doc-stale-check.py', 'doc-encoding-check.py', 'doc-format-check.py', 'doc-tree.py', 'doc-scaffold.py'):
            command = shlex.join([sys.executable, str(SCRIPT.parent / name), str(self.project)])
            output = self.event('PreToolUse', tool_input={'command': command})
            self.assertNotIn('permissionDecision', output.get('hookSpecificOutput', {}), name)
        draft = self.docs / '.tmp/draft.md'
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text('# draft\n')
        converter = str(SCRIPT.parent / 'convert-to-utf8.sh')
        command = shlex.join(['bash', converter, '--from', 'gb18030', str(draft)])
        output = self.event('PreToolUse', tool_input={'command': command})
        self.assertNotIn('permissionDecision', output.get('hookSpecificOutput', {}))
        for destination in (self.docs / 'doc-library/main-module.md', self.docs / '.tmp', self.project / 'main.py'):
            command = shlex.join(['bash', converter, str(destination)])
            output = self.event('PreToolUse', tool_input={'command': command})
            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        (self.docs / '.tmp/formal-link').symlink_to(self.docs / 'doc-library', target_is_directory=True)
        command = shlex.join(['bash', converter, str(self.docs / '.tmp/formal-link/main-module.md')])
        output = self.event('PreToolUse', tool_input={'command': command})
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        for flag in ('--out', '--o', '--out='):
            command = shlex.join([sys.executable, str(SCRIPT.parent / 'doc-tree.py'), str(self.project), flag, str(self.project / 'main.py')])
            output = self.event('PreToolUse', tool_input={'command': command})
            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_invalid_proposal_format_rejected(self):
        self.write_source()
        path = self.proposal('No YAML frontmatter\n')
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path), expected=2)

    def test_exact_user_approval_applies_once_without_recursive_debt(self):
        self.write_source()
        path = self.proposal()
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        self.cli('apply', '--project', str(self.project), '--session', 'conversation', expected=2)
        pending = self.status()['pending']
        prompt = '确认文档 ' + pending['id'] + ' ' + pending['proposal']['blocks'][0]['sha256'][:12]
        self.event('UserPromptSubmit', prompt=prompt)
        self.assertIsNone(self.status()['pending'])
        self.event('PreToolUse', tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'}, tool_use_id='after')
        self.event('PostToolUse', tool_use_id='after')
        self.assertIsNone(self.status()['pending'])
        self.assertIn('Application with value 2.', (self.docs / 'doc-library/main-module.md').read_text())

    def test_stop_requests_continuation_when_review_pending(self):
        self.write_source()
        out = self.event('Stop')
        self.assertEqual(out['decision'], 'block')
        self.assertIn(self.status()['pending']['id'], out['reason'])

    def test_corrupt_state_allows_diagnostics_but_denies_writing(self):
        self.event('UserPromptSubmit', prompt='start')
        next(self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json')).write_text('{broken')
        output = self.event('PreToolUse', tool_input={'command': 'git --no-pager diff --no-ext-diff --no-textconv'})
        self.assertNotIn('permissionDecision', output.get('hookSpecificOutput', {}))
        output = self.event('PreToolUse')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_overlapping_callbacks_do_not_reopen_completed_review(self):
        self.event('PreToolUse', tool_use_id='a')
        self.event('PreToolUse', tool_use_id='b')
        (self.project / 'main.py').write_text('value = 2\n')
        self.event('PostToolUse', tool_use_id='a')
        pending = self.status()['pending']
        path = self.base / 'review.json'
        path.write_text(json.dumps({'change_id': pending['id'], 'decisions': [
            {'document': '.agent-docs/doc-library/main-module.md', 'action': 'unchanged', 'reason': 'Internal value only.'}]}))
        self.cli('review', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        self.event('PostToolUse', tool_use_id='b')
        self.assertIsNone(self.status()['pending'])

    def test_large_diff_requires_each_block_confirmation(self):
        self.write_source()
        text = '---\nschema_version: 7\n---\n# Main\n'
        for heading in ('定位', '职责边界', '业务逻辑', '架构', '生命周期'):
            text += '\n## ' + heading + '\n' + 'Application behavior.\n' * 70
        path = self.proposal(text)
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        pending = self.status()['pending']
        blocks = pending['proposal']['blocks']
        self.assertGreater(len(blocks), 1)
        self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + blocks[0]['sha256'][:12])
        self.assertIsNotNone(self.status()['pending'])
        self.assertNotIn('Application behavior.', (self.docs / 'doc-library/main-module.md').read_text())
        for block in blocks[1:]:
            self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + block['sha256'][:12])
        self.assertIsNone(self.status()['pending'])

    def test_changed_source_invalidates_exact_user_confirmation(self):
        self.write_source()
        path = self.proposal()
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        pending = self.status()['pending']
        (self.project / 'main.py').write_text('new behavior\n')
        output = self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + pending['proposal']['blocks'][0]['sha256'][:12])
        self.assertIn('source changed', output['hookSpecificOutput']['additionalContext'])
        self.assertNotIn('Application with value 2.', (self.docs / 'doc-library/main-module.md').read_text())

    def test_initialized_submodule_changes_match_repo_when_mount_field_missing(self):
        child = self.project / 'lib'
        child.mkdir()
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'), ('config', 'user.email', 'fixture@example.invalid')):
            subprocess.run(['git', '-C', str(child), *args], check=True, capture_output=True)
        (child / 'lib.py').write_text('original\n')
        subprocess.run(['git', '-C', str(child), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(child), 'commit', '-qm', 'child'], check=True, capture_output=True)
        (self.project / '.gitmodules').write_text('[submodule "lib"]\n path = lib\n url = https://github.com/example/lib.git\n')
        doc = self.docs / 'doc-library/modules/lib.md'
        doc.write_text('---\nschema_version: 7\nrepo: https://github.com/example/lib.git\nbranch: main\ncommit: ' + 'a' * 40 + '\n---\n# Lib\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'submodule')
        for state_file in self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json'):
            state_file.unlink()
        self.event('UserPromptSubmit', prompt='load new module')
        self.event('PreToolUse')
        (child / 'lib.py').write_text('changed\n')
        self.event('PostToolUse')
        self.assertIn('.agent-docs/doc-library/modules/lib.md', self.status()['pending']['documents'])
        self.assertIn('lib/lib.py', self.status()['pending']['paths'])

    def test_live_doc_patch_requires_proposal_even_without_pending(self):
        patch = '*** Begin Patch\n*** Update File: .agent-docs/doc-library/main-module.md\n@@\n-Fixture application.\n+Unapproved.\n*** End Patch\n'
        out = self.event('PreToolUse', tool_name='apply_patch', tool_input={'command': patch})
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_gitmodule_change_allows_new_doc_and_index_in_proposal(self):
        self.event('PreToolUse')
        (self.project / '.gitmodules').write_text('[submodule "lib"]\n path = lib\n url = https://github.com/example/lib.git\n')
        self.event('PostToolUse')
        pending = self.status()['pending']
        self.assertIn('.agent-docs/_index.md', pending['documents'])
        new_doc = '.agent-docs/doc-library/modules/lib.md'
        decisions = [{'document': p, 'action': 'unchanged', 'reason': 'Existing content still matches.'} for p in pending['documents']]
        decisions.append({'document': new_doc, 'action': 'update', 'reason': 'Document the new library.',
            'new_content': '---\nschema_version: 7\nrepo: https://github.com/example/lib.git\nbranch: main\ncommit: ' + 'a' * 40 + '\n---\n# Lib\n\n## 定位\nNew library.\n'})
        path = self.base / 'new-doc-review.json'
        path.write_text(json.dumps({'change_id': pending['id'], 'decisions': decisions}))
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        pending = self.status()['pending']
        for block in pending['proposal']['blocks']:
            self.event('UserPromptSubmit', prompt='确认文档 ' + pending['id'] + ' ' + block['sha256'][:12])
        self.assertTrue((self.project / new_doc).exists())

    def test_failed_apply_survives_post_callback_and_retries(self):
        self.write_source()
        path = self.proposal()
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        spec = importlib.util.spec_from_file_location('gate_fixture', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gate = module.Gate(self.runtime, self.project, 'conversation')
        state = gate.load()
        state['pending']['approved_sha256'] = state['pending']['proposal']['sha256']
        gate.save(state)
        real_run = subprocess.run
        def interrupt_convert(command, *args, **kwargs):
            if command[0] == 'bash':
                raise RuntimeError('interrupt after replacement')
            return real_run(command, *args, **kwargs)
        with mock.patch.object(module.subprocess, 'run', side_effect=interrupt_convert):
            with self.assertRaises(RuntimeError):
                gate.apply(state)
        self.assertEqual(gate.load()['pending']['status'], 'applying')
        self.event('PostToolUse')
        self.assertEqual(self.status()['pending']['status'], 'applying')
        self.cli('apply', '--project', str(self.project), '--session', 'conversation')
        self.assertIsNone(self.status()['pending'])


    def test_explicit_document_update_can_begin_without_source_write(self):
        state = self.cli('begin', '--project', str(self.project), '--session', 'conversation',
                         '--document', '.agent-docs/doc-library/main-module.md')
        self.assertEqual(state['pending']['paths'], [])
        self.assertIn('.agent-docs/doc-library/main-module.md', state['pending']['documents'])
        path = self.proposal()
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        self.assertEqual(self.status()['pending']['status'], 'awaiting_approval')

    def test_missing_context_proof_blocks_write_until_context_command(self):
        state_file = next(self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json'))
        state = json.loads(state_file.read_text())
        state.pop('context')
        state_file.write_text(json.dumps(state))
        output = self.event('PreToolUse')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.cli('context', '--project', str(self.project), '--session', 'conversation')
        self.assertEqual(self.event('PreToolUse'), {})

    def test_staged_gitlink_change_without_worktree_checkout_is_observed(self):
        child = self.project / 'lib'
        child.mkdir()
        def child_git(*args):
            return subprocess.check_output(['git', '-C', str(child), *args], text=True).strip()
        child_git('init', '-q')
        child_git('config', 'user.name', 'Fixture')
        child_git('config', 'user.email', 'fixture@example.invalid')
        (child / 'lib.py').write_text('first\n')
        child_git('add', '.')
        child_git('commit', '-qm', 'first')
        first = child_git('rev-parse', 'HEAD')
        (child / 'lib.py').write_text('second\n')
        child_git('commit', '-qam', 'second')
        (self.project / '.gitmodules').write_text('[submodule "lib"]\n path = lib\n url = https://github.com/example/lib.git\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'add module')
        for state_file in self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json'):
            state_file.unlink()
        self.event('UserPromptSubmit', prompt='start')
        self.event('PreToolUse')
        self.git('update-index', '--cacheinfo', '160000', first, 'lib')
        self.event('PostToolUse')
        self.assertIn('lib', self.status()['pending']['paths'])

    def test_conflicted_partial_apply_can_recover_without_reusing_approval(self):
        self.write_source()
        path = self.proposal()
        self.cli('propose', '--project', str(self.project), '--session', 'conversation', '--file', str(path))
        state_file = next(self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json'))
        state = json.loads(state_file.read_text())
        old_id = state['pending']['id']
        state['pending']['status'] = 'applying'
        state['pending']['approved_sha256'] = state['pending']['proposal']['sha256']
        state_file.write_text(json.dumps(state))
        (self.docs / 'doc-library/main-module.md').write_text(state['pending']['proposal']['updates']['.agent-docs/doc-library/main-module.md'])
        (self.project / 'main.py').write_text('new external behavior\n')
        (self.project / 'lib').mkdir()
        (self.project / 'lib/part.py').write_text('external module change\n')
        module_doc = '.agent-docs/doc-library/modules/lib.md'
        (self.project / module_doc).write_text('---\nschema_version: 7\norigin_path_in_main: lib\n---\n# Lib\n')
        self.cli('apply', '--project', str(self.project), '--session', 'conversation', expected=2)
        result = self.cli('recover', '--project', str(self.project), '--session', 'conversation')
        self.assertNotEqual(result['pending']['id'], old_id)
        self.assertNotIn('approved_sha256', result['pending'])
        self.assertIn(module_doc, result['pending']['documents'])
        self.assertEqual(result['recovery_history'][-1]['id'], old_id)
        self.assertEqual(result['pending']['documents']['.agent-docs/doc-library/main-module.md'], hashlib.sha256((self.docs / 'doc-library/main-module.md').read_bytes()).hexdigest())

    def test_large_library_can_load_and_record_selected_scope(self):
        for i in range(4):
            (self.docs / ('doc-library/modules/large' + str(i) + '.md')).write_text('---\nschema_version: 7\n---\n# Module\n' + 'text ' * 14000)
        self.git('add', '.')
        self.git('commit', '-qm', 'large library')
        for state_file in self.runtime.glob('[0-9a-f]' + '?' * 63 + '.json'):
            state_file.unlink()
        result = self.event('UserPromptSubmit', prompt='architecture')
        self.assertIn('exceeds', result['hookSpecificOutput']['additionalContext'])
        result = self.cli('context', '--project', str(self.project), '--session', 'conversation',
                          '--document', '.agent-docs/doc-library/modules/large0.md')
        self.assertEqual(result['scope'], 'selected')
        self.assertEqual(len(result['documents']), 3)
        self.assertEqual(self.event('PreToolUse'), {})

if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Installation tests never touch the user's actual configuration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if path.name == 'doc-gate-install.py':
        module.host_identity = lambda: {'path': '/synthetic-test-host/codex'}
    return module


def fixture_adapter(module, config_dir, runtime):
    """Real Codex config inspection with only the external OS host lookup mocked."""
    runtime.mkdir(parents=True, exist_ok=True)
    checker = runtime / 'fixture-adapter.py'
    checker.write_text("import importlib.util,json\n" +
        "spec=importlib.util.spec_from_file_location('adapter'," + repr(str(HERE / 'doc-gate-install.py')) + ")\n" +
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n" +
        "m.host_identity=lambda:{'path':'/synthetic-test-host/codex'}\n" +
        "try:\n print(json.dumps(m.codex_status(m.Path(" + repr(str(config_dir)) + "),m.Path(" + repr(str(runtime)) + "))))\n" +
        "except ValueError as e:\n print(json.dumps({'error':str(e)}));raise SystemExit(2)\n")
    import hashlib
    descriptor = {'schema_version': 1, 'adapter_id': 'codex',
                  'entry_file': str(checker),
                  'check_command': [sys.executable, str(checker)],
                  'files': {str(checker): hashlib.sha256(checker.read_bytes()).hexdigest(),
                            sys.executable: hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}}
    manifest = runtime / 'fixture-manifest.json'
    manifest.write_text(json.dumps(descriptor))
    module.register_adapter(manifest, runtime, {'behavior_tests': 'passed'})


class InstallTests(unittest.TestCase):
    def test_native_checker_cannot_pin_only_its_configuration_argument(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            checker, config = root / 'checker', root / 'config.json'
            checker.write_text('native executable fixture')
            config.write_text('{}')
            import hashlib
            descriptor = {'schema_version': 1, 'adapter_id': 'other-ai',
                          'check_command': [str(checker), str(config)], 'entry_file': str(checker),
                          'files': {str(config): hashlib.sha256(config.read_bytes()).hexdigest()}}
            with self.assertRaisesRegex(ValueError, 'entry|executable'):
                module.validate_adapter(descriptor)

    def test_non_codex_adapter_uses_same_required_gate_without_codex_configuration(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            runtime = root / 'runtime'
            checker = root / 'other-ai-adapter.py'
            status = {'adapter_id': 'other-ai', 'gate_id': module.GATE_ID, 'enabled': True, 'trusted': True,
                      'host_fingerprint': {'product': 'Other AI', 'version': 'fixture'},
                      'configuration_sha256': 'test-config', 'capabilities': [
                          'context_each_turn', 'context_after_resume', 'pre_write_deny',
                          'post_write_observe', 'continue_pending_review', 'trusted_user_input']}
            checker.write_text('import json\nprint(json.dumps(' + repr(status) + '))\n')
            import hashlib
            descriptor = {'schema_version': 1, 'adapter_id': 'other-ai',
                          'entry_file': str(checker),
                          'check_command': [sys.executable, str(checker)],
                          'files': {str(checker): hashlib.sha256(checker.read_bytes()).hexdigest(),
                                    sys.executable: hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()}}
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(descriptor))
            module.register_adapter(manifest, runtime, {'behavior_tests': 'passed'})
            # No ~/.codex files or Codex process are involved in the common gate.
            probe = module.start_verification(runtime, None)
            self.assertTrue(Path(probe['project']).is_dir())
            with self.assertRaisesRegex(ValueError, 'native verification incomplete'):
                module.require_ready(runtime)
            status['capabilities'].remove('pre_write_deny')
            checker.write_text('import json\nprint(json.dumps(' + repr(status) + '))\n')
            with self.assertRaisesRegex(ValueError, 'adapter.*changed'):
                module.require_ready(runtime)

    def test_host_identity_uses_running_ancestor_not_an_unrelated_installation(self):
        spec = importlib.util.spec_from_file_location('actual_host_identity', HERE / 'doc-gate-install.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder).resolve() / 'codex'
            binary.write_text('host executable fixture')
            with mock.patch.object(module.os, 'getppid', return_value=99999999), mock.patch.object(
                    module.subprocess, 'run', return_value=mock.Mock(stdout='1 ' + str(binary))):
                self.assertEqual(module.host_identity()['path'], str(binary))
    def test_policy_changes_invalidate_the_registered_package(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'skills/doc-context').mkdir(parents=True)
            (root / 'skills/doc-context/SKILL.md').write_text('mandatory native gate')
            before = module.package_hash(root)
            (root / 'skills/doc-context/SKILL.md').write_text('allow manual fallback')
            self.assertNotEqual(module.package_hash(root), before)

    def test_custom_runtime_is_used_by_registration_and_native_loader(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            config, runtime = base / 'config', base / 'custom-runtime'
            config.mkdir()
            module.stage(config, {'behavior_tests': 'passed'}, runtime)
            self.assertTrue((runtime / 'registration.json').is_file())
            mapping = json.loads((config / 'hooks.json').read_text())
            import shlex
            command = mapping['hooks']['PreToolUse'][0]['hooks'][0]['command']
            self.assertIn(str(runtime), shlex.split(command)[2])

    def test_require_ready_rejects_missing_mapping_instead_of_manual_fallback(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(HERE / 'doc-gate-install.py'),
                                     '--require-ready', '--config-dir', folder],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('not ready', result.stdout)
            self.assertFalse((Path(folder) / 'hooks.json').exists())

    def test_native_verification_requires_observed_effects_and_exact_user_confirmation(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            config_dir, runtime = base / 'config', base / 'runtime'
            config_dir.mkdir()
            mappings, digest = module.merged({}, config_dir, runtime)
            path = config_dir / 'hooks.json'
            path.write_text(json.dumps(mappings))
            ids = module.locations(mappings, path)
            native = {'hooks': {'state': {i: {'enabled': True, 'trusted_hash': 'synthetic-test-only'} for i in ids}}}
            def write_config():
                (config_dir / 'config.toml').write_text('\n'.join(
                    '[hooks.state.' + json.dumps(i) + ']\nenabled = ' + str(s['enabled']).lower() + '\ntrusted_hash = "synthetic-test-only"'
                    for i, s in native['hooks']['state'].items()))
            write_config()
            runtime.mkdir()
            fixture_adapter(module, config_dir, runtime)
            with self.assertRaisesRegex(ValueError, 'native verification'):
                module.require_ready(runtime)
            probe = module.start_verification(runtime, 'fixture-session')
            project = Path(probe['project'])
            module.require_ready(runtime, project, 'fixture-session')
            with self.assertRaisesRegex(ValueError, 'native verification'):
                module.require_ready(runtime, base, 'fixture-session')
            event = {'hook_event_name': 'UserPromptSubmit', 'prompt': '确认文档门限验证 ' + probe['nonce']}
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                module.observe_verification(runtime, project, 'fixture-session', event, {}, {})
            events = [
                ('SessionStart', {'hookSpecificOutput': {'additionalContext': probe['nonce']}}),
                ('UserPromptSubmit', {'hookSpecificOutput': {'additionalContext': probe['nonce']}}),
                ('PreToolUse', {}),
                ('PostToolUse', {}),
                ('PreToolUse', {'hookSpecificOutput': {'permissionDecision': 'deny'}}),
                ('Stop', {'decision': 'block'}),
                ('PreToolUse', {}),
                ('UserPromptSubmit', {}),
            ]
            for name, result in events:
                e = {'hook_event_name': name}
                if name == 'UserPromptSubmit' and not result:
                    e['prompt'] = '确认文档 0123456789abcdef 0123456789ab'
                module.observe_verification(runtime, project, 'fixture-session', e, result,
                    {'pending': None if e.get('prompt') else {'paths': ['probe.txt']},
                     'update_checks': 1, 'last_review': {'status': 'applied'}})
            module.observe_verification(runtime, project, 'fixture-session', event, {}, {})
            self.assertTrue(module.require_ready(runtime)['ready'])
            native['hooks']['state'][ids[0]]['enabled'] = False
            write_config()
            with self.assertRaisesRegex(ValueError, 'disabled'):
                module.require_ready(runtime)

    def test_verified_receipt_invalidates_on_mapping_or_package_change(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            config_dir, runtime = base / 'config', base / 'runtime'
            config_dir.mkdir(); runtime.mkdir()
            mappings, digest = module.merged({})
            mappings['hooks']['PreToolUse'][0]['matcher'] = 'Read'
            (config_dir / 'hooks.json').write_text(json.dumps(mappings))
            fixture_adapter(module, config_dir, runtime)
            with self.assertRaisesRegex(ValueError, 'mapping'):
                module.require_ready(runtime)

    def test_registration_has_five_roles_and_preserves_other_policies(self):
        module = load(HERE / 'doc-gate-install.py')
        other = {'statusMessage': 'other', 'type': 'command', 'command': 'other'}
        original = {'hooks': {'PreToolUse': [{'hooks': [other]}]}}
        updated, _ = module.merged(original)
        self.assertEqual(updated['hooks']['PreToolUse'][0]['hooks'], [other])
        self.assertEqual(len(module.locations(updated, Path('/x/hooks.json'))), 5)
        again, _ = module.merged(updated)
        self.assertEqual(updated, again)
        self.assertEqual(original['hooks']['PreToolUse'], [{'hooks': [other]}])

    def test_disabled_state_preserves_native_trust_and_quoted_tables(self):
        module = load(HERE / 'doc-gate-install.py')
        identity = '/x/hooks.json:pre_tool_use:2:0'
        original = "key = 'secret'\n[hooks.state.'" + identity + "'] # comment\n'enabled' = true\ntrusted_hash = 'keep'\n[other]\nx = 1\n"
        result = module.disabled_config(original, [identity, '/new'])
        before = tomllib.loads(original)
        after = tomllib.loads(result)
        before['hooks']['state'][identity]['enabled'] = False
        before['hooks']['state']['/new'] = {'enabled': False}
        self.assertEqual(before, after)

    def test_registration_refuses_to_shift_other_handler_identity(self):
        module = load(HERE / 'doc-gate-install.py')
        data = {'hooks': {'PreToolUse': [{'hooks': [{'statusMessage': module.GATE_ID}]}, {'hooks': [{'statusMessage': 'other'}]}]}}
        # Updating in place preserves identity even when another group follows it.
        updated, _ = module.merged(data)
        self.assertEqual(updated['hooks']['PreToolUse'][1], data['hooks']['PreToolUse'][1])

    def test_package_installer_synchronizes_ide_and_excludes_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, home, ide = root / 'source', root / 'home', root / 'ide'
            (source / 'skills/doc-context').mkdir(parents=True)
            (source / 'skills/doc-context/SKILL.md').write_text('new')
            (source / 'scripts/__pycache__').mkdir(parents=True)
            (source / 'scripts/__pycache__/cache.pyc').write_bytes(b'cache')
            (source / 'scripts/tool.py').write_text('tool')
            (ide / 'other').mkdir(parents=True)
            (ide / 'other/SKILL.md').write_text('untouched')
            module = load(HERE.parent / 'installers/install-global.py')
            module.AGENT_DOCS_HOME = str(home)
            old = sys.argv
            try:
                sys.argv = ['install-global.py', '--source', str(source), '--upgrade', '--skills-target', str(ide)]
                self.assertEqual(module.main(), 0)
            finally:
                sys.argv = old
            self.assertEqual((ide / 'doc-context/SKILL.md').read_text(), 'new')
            self.assertEqual((ide / 'other/SKILL.md').read_text(), 'untouched')
            self.assertFalse((home / 'scripts/__pycache__').exists())

    def test_pinned_loader_refuses_modified_dependency(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            for name in module.PINNED:
                (root / 'scripts' / name).write_bytes((HERE / name).read_bytes())
            entry, _ = module.handler(root)
            (root / 'scripts/doc-tree.py').write_text('changed')
            result = subprocess.run(entry['command'], shell=True, input=json.dumps({'hook_event_name': 'PreToolUse'}), text=True, capture_output=True)
            self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_changed_loader_does_not_block_a_project_without_a_library(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'scripts').mkdir()
            for name in module.PINNED:
                (root / 'scripts' / name).write_bytes((HERE / name).read_bytes())
            entry, _ = module.handler(root)
            (root / 'scripts/doc-tree.py').write_text('changed')
            event = {'hook_event_name': 'PreToolUse', 'cwd': str(root), 'session_id': 'unrelated',
                     'tool_name': 'Bash', 'tool_input': {'command': 'python change.py'}}
            result = subprocess.run(entry['command'], shell=True, input=json.dumps(event), text=True, capture_output=True)
            self.assertNotIn('permissionDecision', json.loads(result.stdout).get('hookSpecificOutput', {}))

    def test_pinned_loader_allows_repair_when_dependency_changed(self):
        module = load(HERE / 'doc-gate-install.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'scripts').mkdir()
            for name in module.PINNED:
                (root / 'scripts' / name).write_bytes((HERE / name).read_bytes())
            entry, _ = module.handler(root)
            (root / 'scripts/doc-tree.py').write_text('changed')
            import shlex
            event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
                     'tool_input': {'command': shlex.join([sys.executable, str(root / 'scripts/doc-gate-install.py'), '--stage-disabled'])}}
            result = subprocess.run(entry['command'], shell=True, input=json.dumps(event), text=True, capture_output=True)
            self.assertNotIn('permissionDecision', json.loads(result.stdout).get('hookSpecificOutput', {}))


if __name__ == '__main__':
    unittest.main()

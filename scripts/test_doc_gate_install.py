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

HERE = Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()

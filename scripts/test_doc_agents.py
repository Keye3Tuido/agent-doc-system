"""Behavioral checks for AGENTS installation and retiring hard gates."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
HERE = Path(__file__).resolve().parent
class AgentsTests(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(HERE / 'doc-agents.py'), *map(str,args)], capture_output=True, text=True)
    def test_install_preserves_user_rules_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'AGENTS.md'; target.write_text('用户规则\n')
            args=['install','--agents-file',target,'--skills-root',HERE.parent/'skills']
            self.assertEqual(self.call(*args).returncode,0)
            first=target.read_bytes(); self.assertTrue(first.startswith('用户规则\n'.encode()))
            self.assertEqual(self.call(*args).returncode,0)
            self.assertEqual(target.read_bytes(),first)
            self.assertEqual(self.call('check',*args[1:]).returncode,0)
    def test_check_does_not_write_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'AGENTS.md'
            self.assertNotEqual(self.call('check','--agents-file',target).returncode,0)
            self.assertFalse(target.exists())
    def test_malformed_marker_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'AGENTS.md'; target.write_text('<!-- project-doc-skills:start -->\nUSER')
            before=target.read_bytes()
            self.assertNotEqual(self.call('install','--agents-file',target).returncode,0)
            self.assertEqual(target.read_bytes(),before)
    def test_workflow_no_longer_registers_or_installs_hooks(self):
        source=(HERE/'doc-workflow.py').read_text()
        self.assertNotIn('ensure_commit_gate(root)',source)
        self.assertNotIn('def registration(',source)
    def test_commit_helper_cannot_install_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git','-C',tmp,'init','-q'],check=True)
            result=subprocess.run([sys.executable,str(HERE/'doc-commit-review.py'),'install','--project',tmp],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('invalid choice', result.stderr)
            self.assertFalse((Path(tmp)/'.git/hooks/pre-commit').exists())
class VerificationTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('workflow',HERE/'doc-workflow.py')
        self.m=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.git('init','-q'); self.git('config','user.name','Test'); self.git('config','user.email','test@example.invalid')
        index=self.root/'.agent-docs/_index.md'; index.parent.mkdir()
        index.write_text('---\nschema_version: 7\nproject_config:\n  initial_bootstrap_done: false\n---\n')
        main=self.root/'.agent-docs/doc-library/main-module.md'; main.parent.mkdir()
        main.write_text('---\nschema_version: 7\n---\n\n## 定位\n\n测试。\n')
        (self.root/'src.txt').write_text('one\n'); self.git('add','.'); self.git('commit','-qm','base')
    def git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)
    def test_completion_never_creates_commit_hook(self):
        token=self.m.inspect(self.root)['source']
        self.m.complete(self.root,token,'已核对源码，正文适用。')
        self.assertFalse((self.root/'.git/hooks/pre-commit').exists())
        (self.root/'src.txt').write_text('two\n'); self.git('add','.')
        self.git('commit','-qm','no program gate')
    def test_changed_source_or_empty_reason_cannot_claim_verified(self):
        token=self.m.inspect(self.root)['source']
        (self.root/'src.txt').write_text('changed\n')
        with self.assertRaises(ValueError): self.m.complete(self.root,token,'核验旧基线')
        with self.assertRaises(ValueError): self.m.complete(self.root,token,'')
    def test_optional_review_report_works_without_hook(self):
        (self.root/'src.txt').write_text('two\n'); self.git('add','.')
        token=self.m.inspect(self.root)['source']; self.m.complete(self.root,token,'源码变化不影响文档语义。')
        base=[sys.executable,str(HERE/'doc-commit-review.py')]
        result=subprocess.run(base+['prepare','--project',str(self.root)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertIn('two',Path(report['report']).read_text())
        self.assertFalse((self.root/'.git/hooks/pre-commit').exists())
    def test_hook_callback_has_been_removed(self):
        result=subprocess.run([sys.executable,str(HERE/'doc-workflow.py'),'hook','--project',str(self.root)],input='{}',capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('invalid choice',result.stderr)
        self.assertFalse(self.m.state_path(self.root).exists())
    def test_rules_are_loaded_from_distributable_document(self):
        spec=importlib.util.spec_from_file_location('agents',HERE/'doc-agents.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        template=(HERE.parent/'templates/AGENTS.md').read_text()
        rendered=template.replace('@SKILLS_ROOT@',str(HERE.parent/'skills'))
        self.assertEqual(module.block(HERE.parent/'skills').strip(),rendered.strip())
    def test_global_install_with_generic_instruction_target(self):
        home=self.root/'home'; home.mkdir()
        target=home/'rules/AGENTS.md'
        config=home/'hooks.json'; config.write_text('USER HOOK')
        command=[sys.executable,str(HERE.parent/'installers/install-global.py'),'--upgrade','--skills-target',str(home/'skills'),'--agents-file',str(target)]
        env={**os.environ,'HOME':str(home)}
        dry=subprocess.run(command+['--dry-run'],env=env,capture_output=True,text=True)
        self.assertEqual(dry.returncode,0); self.assertFalse(target.exists())
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('project-doc-skills:start',target.read_text())
        self.assertTrue((home/'.agent-docs/templates/AGENTS.md').is_file())
        self.assertEqual((home/'.agent-docs/VERSION').read_text().strip(),'5.0.0')
        self.assertEqual(config.read_text(),'USER HOOK')
        self.assertFalse((home/'.codex/hooks.json').exists())

if __name__=='__main__': unittest.main()

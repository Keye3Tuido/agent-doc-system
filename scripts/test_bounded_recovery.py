"""Document recovery may halt unverified; only verified completion clears it."""
import json
import unittest
import test_doc_workflow as legacy

class BoundedRecovery(unittest.TestCase):
    setUp=legacy.Workflow.setUp
    git=legacy.Workflow.git
    write=legacy.Workflow.write
    event=legacy.Workflow.event
    complete=legacy.Workflow.complete

    def test_stop_terminates_when_source_changes_between_attempts(self):
        for i in range(3):
            self.write('src.txt',str(i))
            self.assertEqual(self.event('Stop')['decision'],'block')
        self.write('src.txt','four')
        self.assertIs(self.event('Stop').get('continue'),False)
        self.assertFalse(self.m.state_path(self.root).exists())
        self.assertIs(self.event('Stop').get('continue'),False)
        self.complete()
        self.assertEqual(self.event('Stop'),{})

    def test_repair_commands_are_not_blocked_by_missing_inspection(self):
        import shlex
        control=self.m.HERE/'doc-workflow.py'
        cmd=shlex.join(['python3',str(control),'inspect','--project',str(self.root)])
        out=self.event('PreToolUse',tool_name='Bash',tool_input={'command':cmd},tool_use_id='repair')
        self.assertNotEqual(out.get('hookSpecificOutput',{}).get('permissionDecision'),'deny')

    def test_python_versioned_tv_maintenance_is_project_independent(self):
        import shlex
        from pathlib import Path
        cmd=shlex.join(['python3.14',str(Path.home()/'.codex/tv/process_gate.py'),'--session','isolated','--request','{"action":"inspect"}'])
        self.assertTrue(self.m.project_independent_control({'session_id':'isolated','tool_name':'Bash','tool_input':{'command':cmd}}))


    def test_unintegrated_custom_commit_hook_does_not_reopen_doc_sync(self):
        self.write('custom-hooks/pre-commit','#!/bin/sh\nexit 0\n')
        self.git('config','core.hooksPath','custom-hooks')
        before=(self.root/'custom-hooks/pre-commit').read_bytes()
        self.complete()
        state=json.loads(self.m.state_path(self.root).read_text())
        self.assertEqual(state['commit_gate']['status'],'needs_integration')
        self.assertEqual(self.event('Stop'),{})
        self.assertEqual((self.root/'custom-hooks/pre-commit').read_bytes(),before)
        out=self.event('PreToolUse',tool_name='Bash',tool_input={'command':'git commit -m test'},tool_use_id='commit')
        self.assertIn('needs_integration',out['hookSpecificOutput']['additionalContext'])
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertNotIn('当前相关文档尚未',out['hookSpecificOutput']['additionalContext'])

    def test_native_turn_changes_do_not_reset_stale_episode(self):
        for i in range(3):
            event={'hook_event_name':'Stop','cwd':str(self.root),'session_id':'same','turn_id':'native-'+str(i)}
            self.assertEqual(self.m.hook(event)['decision'],'block')
        event['turn_id']='another-native-turn'
        self.assertIs(self.m.hook(event).get('continue'),False)

    def test_reading_global_adapter_source_does_not_require_game_docs(self):
        import shlex
        from unittest.mock import patch
        home=self.root/'global-home'
        script=home/'.agent-docs/scripts/doc-workflow.py'
        script.parent.mkdir(parents=True);script.write_text('# isolated global adapter')
        event={'hook_event_name':'PreToolUse','cwd':str(self.root),'session_id':'same',
               'tool_name':'Bash','tool_use_id':'read-global','tool_input':{'command':shlex.join(['cat',str(script)])}}
        with patch.object(self.m.Path,'home',return_value=home):
            self.assertEqual(self.m.hook(event),{})

if __name__=='__main__':unittest.main()


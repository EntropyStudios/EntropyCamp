import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from deepseek_sessions import DeepSeekSessions, PREFIX

SID = 'session-12345678-1234-1234-1234-123456789abc'


class DeepSeekSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.path = self.home / 'sessions' / '-project' / SID / 'session.v4.jsonl'
        self.path.parent.mkdir(parents=True)
        self.rows = [{'type':'session', 'version':4, 'id':SID, 'cwd':'/project', 'delegationDepth':0}]
        self.client = DeepSeekSessions(self.home)
        self.id = PREFIX + SID

    def event(self, kind, second, **data):
        self.rows.append({'type':kind, 'seq':len(self.rows), 'time':1800000000000+second*1000, 'data':data})
        self.path.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))

    def prompt(self, number=1, second=1):
        self.turn = number
        self.event('turn/start',second,turn=number)
        self.event('user/message',second,source={'kind':'user'},content=[{'type':'text','text':f'Task {number}'}])

    def answer(self, second=5):
        self.event('assistant/message',second,message={'content':[{'type':'reasoning','text':'private thought'}, {'type':'text','text':'Done'}]})
        self.event('turn/end',second+1,turn=getattr(self,'turn',1),reason={'kind':'completed'})

    def status(self):
        return self.client.thread_statuses([self.id])[0]

    def test_tools_do_not_complete_and_final_turn_completes_once(self):
        self.prompt()
        self.event('request/context',2,provider='deepseek-account',model='deepseek-flash')
        self.event('tool/call',3,name='Bash',arguments={'token':'not exported'})
        self.assertEqual(self.status()['phase'],'executing')
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        self.answer()
        status=self.status()
        self.assertEqual(status['status'],'idle')
        self.assertEqual(status['model'],'deepseek-flash')
        self.assertEqual(status['latestCompletedTurnId'],self.id+':turn-1')
        logs=self.client.work_logs([self.id],include_process=False)
        self.assertEqual([item['text'] for item in logs[0]['turns'][0]['items']],['Task 1','Done'])
        self.assertNotIn('private thought',json.dumps(logs))
        self.assertNotIn('not exported',json.dumps(logs))
        self.assertEqual(len(self.client.work_logs([self.id])[0]['turns']),1)

    def test_abort_error_and_injected_context_are_not_user_completions(self):
        self.prompt()
        self.event('turn/end',3,turn=1,reason={'kind':'aborted'})
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        self.prompt(2,4)
        self.event('turn/end',5,turn=2,reason={'kind':'error','error':{'message':'failed'}})
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        self.event('turn/start',6,turn=3)
        self.event('user/message',7,source={'kind':'runtime-context'},content=[{'type':'text','text':'injected secret'}])
        self.answer(8)
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        self.assertNotIn('injected secret',json.dumps(self.client.work_logs([self.id])))

    def test_window_filter_cache_and_partial_tail(self):
        self.prompt();self.answer()
        end=self.status()['latestCompletedAt']
        self.assertEqual(self.client.work_logs([self.id],since=end+1)[0]['turns'],[])
        early=self.client.work_logs([self.id],until=end-2)[0]['turns'][0]
        self.assertIsNone(early['completedAt'])
        self.assertNotIn('Done',json.dumps(early))
        with patch.object(self.client,'_parse',side_effect=AssertionError('must use cache')):
            self.assertTrue(self.status()['exists'])
        with self.path.open('ab') as stream:stream.write(b'{"type":"turn/start"')
        self.assertEqual(self.status()['latestCompletedAt'],end)

    def test_subagent_and_invalid_ids_are_not_listed(self):
        self.prompt();self.rows[0]['delegationDepth']=1
        self.event('turn/end',3,turn=1,reason={'kind':'completed'})
        self.assertEqual(self.client.list_threads(),[])
        self.assertFalse(self.client.thread_statuses(['deepseek-../../secret'])[0]['exists'])

    @unittest.skipUnless(shutil.which('zstd'), 'zstd not installed')
    def test_actual_zstd_file_is_decoded_without_extracted_files(self):
        self.prompt();self.answer()
        compressed=self.path.with_suffix('.jsonl.zstd')
        subprocess.run(['zstd','-q','-f',str(self.path),'-o',str(compressed)],check=True)
        self.path.unlink()
        self.assertEqual(self.status()['latestCompletedTurnId'],self.id+':turn-1')
        self.assertEqual(len(self.client.list_threads()),1)
        self.assertFalse(self.path.exists())

    def test_routing_never_sends_deepseek_ids_to_codex(self):
        import run
        self.prompt();self.answer()
        with patch.object(run,'DEEPSEEK_SESSIONS',self.client),patch.object(run.CODEX_MONITOR,'thread_statuses',side_effect=AssertionError('wrong provider')):
            self.assertEqual(run.codex_statuses([{'hostId':'local','id':self.id}])[0]['provider'],'deepseek')
        with patch.object(run,'DEEPSEEK_SESSIONS',self.client),patch.object(run.CODEX_WORK_LOGS,'work_logs',side_effect=AssertionError('wrong reader')):
            self.assertEqual(run.local_ai_work_logs([self.id])[0]['provider'],'deepseek')

    def test_background_counts_and_marks_due_without_a_page(self):
        from background_events import BackgroundEventMonitor
        from state_store import BusinessStateStore, CARDS, SESSION
        from test_background_events import FakeNotifier
        self.prompt();self.answer()
        first=self.status()['latestCompletedTurnId']
        store=BusinessStateStore(self.home/'state')
        store.initialize({CARDS:[{'id':'card','title':'DeepSeek','codexThreadId':self.id,'codexHost':'local','codexArmed':True,'codexLastSeenTurnId':first}],
                          SESSION:{'active':True,'startedAt':1,'endedAt':None,'countsByCardId':{'card':0},'countedTurnIdsByCardId':{'card':first}}})
        notifier=FakeNotifier()
        monitor=BackgroundEventMonitor(store=store,status_provider=lambda refs:self.client.thread_statuses([r['id'] for r in refs]),notifier=notifier)
        self.prompt(2,10);self.answer(15)
        monitor.run_once();monitor.run_once()
        state=store.snapshot()['data']
        self.assertEqual(state[SESSION]['countsByCardId']['card'],1)
        self.assertTrue(state[CARDS][0]['codexDue'])
        self.assertEqual(len(notifier.events),1)


if __name__=='__main__':
    unittest.main()

import copy
import functools
import hashlib
import http.server
import json
import os
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visparse_collector.sequence import capture_sequence, validate_plan, _redact
from visparse.interaction import validate_sequence
from visparse.model import ValidationError


def step(kind, selector=None, **kwargs):
    return dict(kind=kind, selector=selector, input_ref=None, key=None, delta=[0, 0], wait_ms=0, sample_ms=[], **{}) | kwargs


def plan(url="http://127.0.0.1:1/interactions.html"):
    return dict(schema_version="interaction-plan/0.1", url=url, allowed_navigation=[], viewport=[800, 600],
                steps=[step("click", "#open")], parameters={"fixture:email": "private@example.test"}, timeout_ms=30000, action_timeout_ms=1500, max_artifact_bytes=10000000)


class PlanTests(unittest.TestCase):
    def test_preflight_before_effects(self):
        for mutation in [lambda p:p.update(timeout_ms=float('inf')), lambda p:p['steps'][0].update(kind='explore'),
                         lambda p:p['steps'][0].update(selector=None), lambda p:p.update(allowed_navigation=['file:///tmp/private']),
                         lambda p:p['steps'][0].update(sample_ms=[-1]), lambda p:p.update(max_artifact_bytes=True)]:
            p=plan(); mutation(p)
            with patch('visparse_collector.sequence._record', new_callable=AsyncMock) as record, self.assertRaises(ValidationError):
                capture_sequence(p, '/not-created')
            record.assert_not_called()
    def test_redaction_and_mock_boundary(self):
        self.assertEqual(_redact({'text':['hello private']}, {'redacted:x':'private'}), {'text':['hello [redacted]']})
        with patch('visparse_collector.sequence._record', new_callable=AsyncMock, return_value={'fixture':True}) as record:
            self.assertEqual(capture_sequence(plan(), '/tmp/unused'), {'fixture':True})
            record.assert_awaited_once()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


@unittest.skipUnless(os.environ.get('VISPARSE_BROWSER_TESTS') == '1', 'opt-in local Chromium')
class SequenceBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler,directory=str(Path(__file__).parent/'fixtures')))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}/interactions.html'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_desktop_mobile_actions_and_artifacts(self):
        for viewport in ([800,600],[390,844]):
            p=plan(self.url);p['viewport']=viewport;p['steps']=[step('click','#open'),step('press','#close',key='Escape'),step('click','#submit'),step('focus','#email'),step('fill','#email',input_ref='fixture:email'),step('click','#submit'),step('click','#save'),step('reload'),step('click','#noop'),step('hover','#delayed'),step('click','#delayed',sample_ms=[0,600]),step('scroll',delta=[0,200])]
            with TemporaryDirectory() as directory:
                result=capture_sequence(p,directory);validate_sequence(result)
                self.assertEqual(len(result['actions']),len(p['steps']))
                self.assertTrue(all(a['outcome'].startswith('observed-') for a in result['actions']))
                self.assertNotIn('private@example.test', json.dumps(result))
                self.assertTrue(result['actions'][10]['feedback'])
                self.assertEqual(result['actions'][1]['input_parameters'],{'key':'Escape'})
                self.assertEqual(result['actions'][-1]['input_parameters'],{'delta':[0,200]})
                for capture in result['captures']:
                    if capture['artifact']:
                        digest=capture['artifact']['sha256'];self.assertEqual(hashlib.sha256((Path(directory)/(digest+'.png')).read_bytes()).hexdigest(),digest)
                dom=[c['data'] for c in result['captures'] if c['kind']=='dom']
                self.assertTrue(any(any(n['text']=='Remove saved item' for n in d['nodes']) for d in dom))
                self.assertTrue(any(any(n['valid'] is False for n in d['nodes']) for d in dom))
                self.assertTrue(any(any(n['valid'] is True for n in d['nodes']) for d in dom))
                self.assertTrue(any(any(n['text']=='Loading' for n in d['nodes']) for d in dom))
    def test_failures_stop_and_keep_partial_evidence(self):
        for steps, expected in [([step('click','#missing'),step('reload')],'failed-action'),([step('click','#escape')],'failed-action'),([step('click','#close')],'collection-timeout')]:
            p=plan(self.url);p['steps']=steps
            with TemporaryDirectory() as directory:
                result=capture_sequence(p,directory)
                self.assertEqual(len(result['actions']),1)
                self.assertEqual(result['actions'][0]['outcome'],expected)
                self.assertFalse(result['actions'][0]['after'])

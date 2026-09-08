import copy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visparse.interaction_analysis import *
from visparse.model import ValidationError
from visparse.codex import ProcessResult, CodexProcessError, CodexTimeoutError
from interaction_fixtures import sequence, prediction


class AnalysisTests(unittest.TestCase):
    def test_projection_is_not_state_inference_and_cannot_be_modified(self):
        s=sequence(); p=prediction(s); result=apply_interaction_analysis(s,p)
        self.assertEqual(result['projected_actions'][0]['timing_sample']['value'],1)
        result['projected_actions'][0]['outcome']='success'
        with self.assertRaises(ValidationError): validate_interaction_profile(result)
        self.assertEqual(len(apply_interaction_analysis(s,dict(p, states=[],claims=[],transitions=[]))['inference']['states']),0)
    def test_rejects_fabricated_references_edges_and_persistence(self):
        mutations=[lambda p:p.update(sequence_sha256='0'*64),lambda p:p['claims'][0].update(evidence_ids=['expected']),
                   lambda p:p['claims'][0].update(kind='persistence'),lambda p:p['states'][1].update(capture_ids=['before']),
                   lambda p:p['transitions'][0].update(action_id='unrecorded'),lambda p:p['transitions'][0].update(confidence=.9),
                   lambda p:p['claims'][0].update(kind='target-requirement'),lambda p:p['claims'][0].update(status='unavailable')]
        for mutate in mutations:
            p=prediction();mutate(p)
            with self.subTest(p=p),self.assertRaises(ValidationError):apply_interaction_analysis(sequence(),p)
    def test_failed_capture_does_not_establish_application_state(self):
        s=sequence('failed-action');p=prediction(s)
        p['claims'][0].update(status='unavailable',value=None)
        with self.assertRaisesRegex(ValidationError,'failed or unobserved'): apply_interaction_analysis(s,p)
        p['transitions'][0]['to']=None
        self.assertEqual(apply_interaction_analysis(s,p)['projected_actions'][0]['outcome'],'failed-action')
    def test_conflicts_noise_and_same_image_are_retained_without_merging(self):
        s=sequence();s['captures'][0]['data']={'image':'same','dirty':False,'clock':1};s['captures'][1]['data']={'image':'same','dirty':True,'clock':2}
        p=prediction(s);opposite=dict(p['claims'][0],id='other',value='Saved marker absent')
        p['claims'].append(opposite);p['conflicts']=[{'claim_ids':['result','other'],'reason':'conflicting supplied interpretations'}]
        result=apply_interaction_analysis(s,p)
        self.assertEqual(len(result['inference']['states']),2);self.assertEqual(len(result['inference']['conflicts']),1)
        p['states'][0]['capture_ids']=['before','after'];p['states']=p['states'][:1];p['transitions'][0]['to']='unsaved'
        self.assertEqual(len(apply_interaction_analysis(s,p)['inference']['states']),1)
    def test_supplied_tab_dialog_form_focus_cancel_and_retry_states_are_grounded(self):
        for component,kind,claim_kind,effect in [('tabs','click','state','selected'),('dialog','click','outcome','visible'),('dialog','press','cancel','hidden'),('form','click','feedback','invalid'),('form','fill','state','corrected'),('dialog','focus','focus','dismiss control focused'),('request','click','recovery','retry succeeded')]:
            s=sequence(kind=kind)
            if kind=='fill':s['actions'][0]['input_ref']='fixture:email'
            s['captures'][1]['data']={'fixture_component':component,'fixture_effect':effect}
            p=prediction(s);p['states'][0]['component']=component;p['states'][1].update(component=component,label=effect)
            p['claims'][0].update(kind=claim_kind,subject=component,value=effect)
            result=apply_interaction_analysis(s,p)
            self.assertEqual(result['inference']['claims'][0]['value'],effect)
            self.assertEqual(result['projected_actions'][0]['before'],['before'])
            self.assertEqual(result['projected_actions'][0]['after'],['after'])
            p['states'][1]['capture_ids']=['before']
            with self.assertRaisesRegex(ValidationError,'after evidence'):apply_interaction_analysis(s,p)

    def test_adapter_preflight_single_call_and_failure(self):
        s=sequence();runner=Mock();runner.run.return_value=ProcessResult(0,canonical(prediction(s)), '')
        self.assertEqual(analyze_interactions(s,CodexInteractionAnalyzer(runner=runner))['schema_version'],VERSION)
        runner.run.assert_called_once()
        runner.reset_mock()
        with self.assertRaises(ValidationError): CodexInteractionAnalyzer(runner=runner,timeout_seconds=float('nan')).analyze(s)
        runner.run.assert_not_called()
        for response, error in [(ProcessResult(1,'','usage limit'),CodexProcessError),(subprocess.TimeoutExpired('codex',1),CodexTimeoutError)]:
            runner=Mock()
            if isinstance(response,Exception):runner.run.side_effect=response
            else:runner.run.return_value=response
            with self.assertRaises(error):CodexInteractionAnalyzer(runner=runner).analyze(s)
            runner.run.assert_called_once()

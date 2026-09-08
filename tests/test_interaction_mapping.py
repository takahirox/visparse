import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from visparse.interaction_mapping import *
from visparse.interaction_export import export_interactions
from visparse.model import ValidationError
from interaction_fixtures import mapping_fixture


class MappingTests(unittest.TestCase):
    def test_compatible_preserves_data_tasks_and_neutral_roles(self):
        args=mapping_fixture();out=prepare_mapping(*args)
        self.assertTrue(out['bindings'][0]['ready'])
        self.assertEqual(out['target_inventory'],args[2])
        self.assertEqual(out['preservation']['task_ids'],['bookmark'])
        self.assertEqual([s['expected_effect'] for s in out['verification_scenarios'][0]['steps']],['saved','saved','removed'])
        self.assertNotIn('#source-save',canonical(out))
        self.assertIn('#source-save',canonical(prepare_mapping(*args,view='audit')))
    def test_semantic_mismatch_cannot_be_confident_mapping(self):
        profile,p,target,proposal=mapping_fixture();target['tasks'][0]['semantic']='join-session';proposal['target_sha256']=digest(target)
        with self.assertRaisesRegex(ValidationError,'conflicts'):prepare_mapping(profile,p,target,proposal)
        proposal['bindings'][0]['status']='conflict';out=prepare_mapping(profile,p,target,proposal)
        self.assertFalse(out['bindings'][0]['ready']);self.assertIn('task-semantic-conflict',out['bindings'][0]['issues'])
    def test_capability_unknown_and_partial_statuses(self):
        profile,p,target,proposal=mapping_fixture();target['capabilities']=['dom'];proposal['target_sha256']=digest(target)
        proposal['bindings'][0]['status']='unsupported-capability'
        self.assertFalse(prepare_mapping(profile,p,target,proposal)['bindings'][0]['ready'])
        proposal['bindings'][0].update(status='qualified-partial',adaptations=['explicit-target-requirement'])
        with self.assertRaisesRegex(ValidationError,'capability requirement'):prepare_mapping(profile,p,target,proposal)
        target['requirements']=[{'id':'storage-request','task_id':'bookmark','change':'add-capability','value':'local-storage','origin':'Explicit target owner requirement'}]
        proposal['target_sha256']=digest(target);proposal['bindings'][0]['requirement_ids']=['storage-request']
        out=prepare_mapping(profile,p,target,proposal);self.assertFalse(out['bindings'][0]['ready']);self.assertFalse(out['new_capabilities_implemented'])
        profile,p,target,proposal=mapping_fixture();proposal['bindings'][0].update(task_id=None,status='insufficient-evidence',roles={})
        self.assertIn('bookmark',prepare_mapping(profile,p,target,proposal)['unmapped_target_tasks'])
    def test_unknown_source_effect_is_not_execution_ready(self):
        profile,p,target,proposal=mapping_fixture();p["patterns"][0]["steps"][0]["effect"]="unknown"
        proposal["source_sha256"]=digest(export_interactions(profile,p))
        with self.assertRaisesRegex(ValidationError,"source-outcome-unknown"):prepare_mapping(profile,p,target,proposal)
        proposal["bindings"][0]["status"]="insufficient-evidence"
        self.assertFalse(prepare_mapping(profile,p,target,proposal)["bindings"][0]["ready"])

    def test_legacy_missing_operation_parameters_are_not_execution_ready(self):
        from visparse.interaction_analysis import apply_interaction_analysis,sequence_digest
        from visparse.interaction_export import profile_digest
        profile,p,target,proposal=mapping_fixture()
        profile['sequence']['actions'][0]['kind']='press'
        profile['inference']['sequence_sha256']=sequence_digest(profile['sequence'])
        profile=apply_interaction_analysis(profile['sequence'],profile['inference']);p['profile_sha256']=profile_digest(profile)
        proposal['source_sha256']=digest(export_interactions(profile,p))
        with self.assertRaisesRegex(ValidationError,'input-parameters-unavailable'):prepare_mapping(profile,p,target,proposal)

    def test_intent_hash_and_invariants_are_enforced(self):
        args=list(mapping_fixture());args[3]['bindings'][0]['adaptations']=['change-feedback'];args[3]['bindings'][0]['status']='qualified-partial'
        with self.assertRaisesRegex(ValidationError,'order and feedback'):prepare_mapping(*args)
        args[3]['intent']='outcome-equivalence';args[3]['source_sha256']=digest(export_interactions(args[0],args[1],intent='outcome-equivalence'))
        self.assertFalse(prepare_mapping(*args,intent='outcome-equivalence')['bindings'][0]['ready'])
        args[2]['entities'][0]['records'][0]['title']='Changed target'
        with self.assertRaisesRegex(ValidationError,'hash mismatch'):prepare_mapping(*args,intent='outcome-equivalence')

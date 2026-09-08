import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from visparse.interaction_analysis import apply_interaction_analysis
from visparse.interaction_export import *
from visparse.model import ValidationError
from interaction_fixtures import sequence,prediction,patterns,flow_fixture


class ExportTests(unittest.TestCase):
    def profile(self):
        s=sequence();s['targets'][0]['locator']='#SECRET-BRAND';p=prediction(s);p['claims'][0]['value']='SECRET-BRAND saved'
        return apply_interaction_analysis(s,p)
    def test_generation_excludes_source_content_and_audit_retains_exact_ancestry(self):
        profile=self.profile();p=patterns(profile)
        output=export_interactions(profile,p)
        self.assertNotIn('SECRET-BRAND',canonical(output));self.assertNotIn('source-save',canonical(output))
        self.assertEqual(output,export_interactions(profile,p))
        self.assertIn('SECRET-BRAND',canonical(export_interactions(profile,p,view='audit')))
        self.assertEqual(output['patterns'][0]['steps'][0]['effect'],'saved')
        self.assertIn('timing_requirement',render_interactions(profile,p))
    def test_conflicts_and_low_confidence_are_excluded_with_reasons(self):
        profile=self.profile();p=patterns(profile)
        self.assertFalse(export_interactions(profile,p,min_confidence=.9)['decisions'][0]['included'])
        profile['inference']['claims'].append(dict(profile['inference']['claims'][0],id='opposite',value='Not saved'))
        profile['inference']['conflicts']=[{'claim_ids':['result','opposite'],'reason':'conflicting sample'}]
        p=patterns(profile);out=export_interactions(profile,p)
        self.assertEqual(out['patterns'][0]['steps'],[])
        self.assertIn('conflicting-evidence',out['decisions'][0]['reasons'])
    def test_rejects_unattributed_enrichment_and_invented_guard_or_persistence(self):
        profile=self.profile()
        for mutate in [lambda p:p['patterns'][0].update(origin='observed'),lambda p:p['patterns'][0]['steps'][0].update(condition='valid-input'),
                       lambda p:p['patterns'][0]['steps'][0].update(role='SECRET-BRAND'),lambda p:p['patterns'][0].update(persistence={'mode':'reload','claim_id':'result'}),
                       lambda p:p['patterns'][0].update(confidence=.99)]:
            p=patterns(profile);mutate(p)
            with self.assertRaises(ValidationError):export_interactions(profile,p)
    def test_save_reload_remove_and_form_branches_survive_export(self):
        profile,p=flow_fixture();out=export_interactions(profile,p)
        self.assertEqual([s["effect"] for pattern in out["patterns"] for s in pattern["steps"]], ["saved","saved","removed","invalid","corrected","submitted","cancelled"])
        self.assertEqual(out["patterns"][0]["persistence"],"reload")
        self.assertFalse(out["unmapped_transitions"])
        p["patterns"][0]["steps"].reverse()
        with self.assertRaisesRegex(ValidationError,"recorded action order"):export_interactions(profile,p)

    def test_intent_and_unknowns_remain_explicit(self):
        profile=self.profile();p=patterns(profile)
        out=export_interactions(profile,p,intent='outcome-equivalence')
        self.assertEqual(out['policy']['intent'],'outcome-equivalence')
        self.assertEqual(out['patterns'][0]['persistence'],'unknown')
        self.assertEqual(out['patterns'][0]['steps'][0]['condition'],'unknown')

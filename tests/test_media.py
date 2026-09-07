import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from visparse.semantic import apply_semantics
from visparse.media import assess_media, media_requirements, validate_capabilities
from visparse.roundtrip import prepare_roundtrip
from visparse.cli import main
from visparse.model import ValidationError
from visparse.render import render_design

ROOT=Path(__file__).resolve().parents[1]


def photo():
    f=json.loads((ROOT/'examples/design/semantic-corporate.json').read_text())
    return apply_semantics(f['dna'],f['prediction'])


def caps(value='unavailable'):return {'schema_version':'0.1','kinds':{'photography':value,'illustration':'available'}}


class MediaTests(unittest.TestCase):
    def test_capabilities_reach_allowed_generator_input(self):
        exported = prepare_roundtrip(photo(), 'Original page', intent='preserve', capabilities=caps())
        allowed = {key: exported[key] for key in exported['protocol']['allowed_inputs']}
        self.assertIn('mismatch', allowed['design_md'])
        self.assertIn('record the replacement', allowed['design_md'])
        self.assertNotIn('media_compatibility', allowed)
        self.assertIn('tradeoff', render_design(photo(), capabilities=caps(), intent='adapt'))
        self.assertNotIn('## Media capabilities', render_design(photo()))

    def test_unknown_guidance_explains_kind_loss_without_inventing_requirement(self):
        for state, expected in [('low', 'low_confidence'), ('unknown', 'unknown'),
                                ('conflict', 'conflict'), ('mixed', 'mixed_kind'), ('missing', 'missing')]:
            dna = photo(); feature = dna['features'][0]
            if state == 'low': feature['confidence'] = 0
            if state == 'unknown': feature.update(status='unknown', value=None, confidence=None)
            if state == 'conflict': dna['features'].append({**copy.deepcopy(feature), 'id': 'different', 'value': 'illustration'})
            if state == 'mixed': feature['value'] = 'mixed'
            if state == 'missing': feature.update(name='imagery.prominence', value='high')
            report = assess_media(dna, caps())
            row = report['assessment'][0]
            self.assertEqual(row['status'], 'unknown')
            self.assertIn(expected, row['findings'][0]['reason_code'])
            rendered = render_design(dna, capabilities=caps(), generation_safe=True, intent='preserve')
            self.assertIn('unresolved requirement', rendered)
            self.assertNotIn('mismatch [', rendered)
            if state != 'mixed': self.assertIn('kind=undetermined', rendered)

    def test_media_and_feature_roles_match_even_with_other_nonmedia_subjects(self):
        dna = photo(); e = dna['evidence'][0]
        dna['evidence'].append({**copy.deepcopy(e), 'id':'extra',
                               'scope':{**e['scope'], 'subject':'AAA private header'}})
        dna['features'][0]['method'] = 'SECRET_METHOD'
        dna['features'][0]['uncertainty'] = 'SECRET_UNCERTAINTY'
        rendered = render_design(dna, capabilities=caps(), generation_safe=True)
        report = assess_media(dna, caps(), generation_safe=True)
        subject = report['requirements'][0]['scope']['subject']
        self.assertEqual(subject, 'role-2')
        self.assertGreaterEqual(rendered.count('subject=role-2'), 2)
        for value in ('SOURCE_BRAND', 'reference.invalid', 'AAA private', 'SECRET_METHOD', 'SECRET_UNCERTAINTY'):
            self.assertNotIn(value, rendered)

    def test_absent_kind_and_unavailable_declaration_are_not_conflated(self):
        dna = photo(); dna['features'][0]['value'] = 'absent'
        rendered = render_design(dna, capabilities=caps())
        self.assertIn('not_applicable [', rendered)
        self.assertNotIn('record the replacement', rendered)
        dna['features'] = []
        self.assertIn('No typed media characteristics', render_design(dna, capabilities=caps()))
        self.assertIn('No definite capability declaration', render_design(photo(), capabilities={'schema_version':'0.1','kinds':{}}))

    def test_render_cli_carries_media_limitations(self):
        with tempfile.TemporaryDirectory() as td:
            d, c = Path(td)/'dna.json', Path(td)/'caps.json'
            d.write_text(json.dumps(photo())); c.write_text(json.dumps(caps()))
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(['design-render',str(d),'--intent','preserve','--generation-safe','--capabilities',str(c)])
            self.assertEqual(code, 0)
            self.assertIn('mismatch', out.getvalue())
            self.assertNotIn('SOURCE_BRAND', out.getvalue())

    def test_photo_vector_mismatch_and_compatible_is_only_declared(self):
        dna=photo();before=copy.deepcopy(dna)
        result=assess_media(dna,caps())
        row=result['assessment'][0]
        self.assertEqual(row['status'],'mismatch')
        self.assertTrue(row['fallback']['compromise'])
        self.assertEqual(row['findings'][0]['category'],'generator_capability')
        self.assertEqual(result['requirements'][0]['properties']['imagery.prominence']['status'],'missing')
        self.assertEqual(dna,before)
        compatible=assess_media(dna,caps('available'))['assessment'][0]
        self.assertEqual(compatible['status'],'compatible_declared')
        self.assertIn('unverified',compatible['reason'])

    def test_unknown_not_failure_and_adapt_is_tradeoff(self):
        self.assertEqual(assess_media(photo(),{'schema_version':'0.1','kinds':{}})['assessment'][0]['status'],'unknown')
        self.assertEqual(assess_media(photo(),caps(),intent='adapt')['assessment'][0]['status'],'tradeoff')
        dna=photo();dna['features'][0].update(confidence=0.1)
        self.assertEqual(assess_media(dna,caps())['assessment'][0]['status'],'unknown')

    def test_mixed_absent_and_missing_media(self):
        dna=photo();dna['features'][0]['value']='mixed'
        self.assertEqual(assess_media(dna,caps())['assessment'][0]['status'],'unknown')
        dna['features'][0]['value']='absent'
        self.assertEqual(assess_media(dna,caps())['assessment'][0]['status'],'not_applicable')
        dna['features']=[]
        self.assertTrue(assess_media(dna,caps())['gaps'])

    def test_safe_export_no_identifiers_or_free_text(self):
        dna=photo();dna['features'][0]['method']='SOURCE_BRAND https://secret.invalid'
        dna['features'][0]['uncertainty']='SECRET_UNCERTAINTY'
        result=assess_media(dna,caps(),generation_safe=True)
        raw=json.dumps(result)
        for secret in ('SOURCE_BRAND','secret.invalid','SECRET_UNCERTAINTY','reference.invalid'):
            self.assertNotIn(secret,raw)
        self.assertIn('photography',raw)
        self.assertIn('inferred',raw)
        self.assertNotIn('evidence_ids',raw)

    def test_capability_and_output_deviation_are_separate(self):
        generated=photo();generated['features'][0]['value']='illustration'
        result=assess_media(photo(),caps(),generated=generated)
        self.assertEqual({x['category'] for x in result['assessment'][0]['findings']},
                         {'generator_capability','generation_deviation'})
        self.assertEqual(assess_media(photo(),caps('available'),generated=generated)['assessment'][0]['status'],'compatible_declared')

    def test_invalid_capabilities_rejected_without_repair(self):
        for bad in ({'schema_version':'2','kinds':{}},{'schema_version':'0.1','kinds':{'photography':True}},
                    {'schema_version':'0.1','kinds':{'video':'available'}},{'schema_version':'0.1','kinds':{},'execute':'command'}):
            with self.assertRaises(ValidationError):validate_capabilities(bad)

    def test_region_prominence_and_framing_keep_provenance(self):
        dna=photo();f=dna['features'][0]
        for i,(name,value) in enumerate([('imagery.prominence','high'),('imagery.framing','wide'),('imagery.text_space','left')]):
            dna['features'].append({**copy.deepcopy(f),'id':f'property-{i}','name':name,'value':value})
        result=media_requirements(dna)
        prop=result['requirements'][0]['properties']['imagery.prominence']
        self.assertEqual(prop['value'],'high')
        self.assertEqual(prop['origins'],['inferred'])
        self.assertTrue(prop['evidence_ids'])

    def test_cli_and_roundtrip_propagate_policy(self):
        dna=photo()
        exported=prepare_roundtrip(dna,'Original page',intent='preserve',capabilities=caps())
        self.assertEqual(exported['media_compatibility']['export_policy'],exported['export_policy'])
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'dna.json';c=Path(td)/'cap.json';b=Path(td)/'brief.txt'
            d.write_text(json.dumps(dna));c.write_text(json.dumps(caps()));b.write_text('Original page')
            for argv in (['design-media-check',str(d),'--capabilities',str(c)],
                         ['design-export',str(d),'--brief',str(b),'--capabilities',str(c),'--intent','preserve']):
                output=io.StringIO()
                with redirect_stdout(output):status=main(argv)
                self.assertEqual(status,0)
                self.assertIn('mismatch',output.getvalue())

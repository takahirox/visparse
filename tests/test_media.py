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

ROOT=Path(__file__).resolve().parents[1]


def photo():
    f=json.loads((ROOT/'examples/design/semantic-corporate.json').read_text())
    return apply_semantics(f['dna'],f['prediction'])


def caps(value='unavailable'):return {'schema_version':'0.1','kinds':{'photography':value,'illustration':'available'}}


class MediaTests(unittest.TestCase):
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

import copy
import json
import unittest
from pathlib import Path
from visparse.semantic import apply_semantics
from visparse.dna import validate_dna
from visparse.render import render_design
from visparse.compare import compare_design
from visparse.model import ValidationError

ROOT=Path(__file__).resolve().parents[1]


def fixture(): return json.loads((ROOT/'examples/design/semantic-spatial.json').read_text())


class SpatialTests(unittest.TestCase):
    def test_scoped_geometry_typography_color_export(self):
        f=fixture();result=apply_semantics(f['dna'],f['prediction'])
        rendered=render_design(result,intent='preserve',generation_safe=True)
        for expected in ('typography.line_count: 2','condensed','#203060','fill-parent','above','aligned-left','Relative to role-'):
            self.assertIn(expected,rendered)
        self.assertNotIn('SOURCE_BRAND',rendered)
        self.assertTrue(all(x['origin']=='inferred' for x in result['features']))
        self.assertEqual(result['evidence'][-1]['details']['supporting_evidence_ids'],['observation'])

    def test_invalid_space_reference_color_count_and_fraction(self):
        for change in ({'value':1.5},{'value':True},{'unit':'px'}):
            f=fixture();f['prediction']['features'][0].update(change)
            with self.assertRaises(ValidationError):apply_semantics(f['dna'],f['prediction'])
        for color in ('blue','#ABCDEF','#fff','javascript:bad'):
            f=fixture();f['prediction']['features'][2]['value']=color
            with self.assertRaises(ValidationError):apply_semantics(f['dna'],f['prediction'])
        f=fixture();f['prediction']['regions'][0]['viewport']='390x844'
        with self.assertRaises(ValidationError):apply_semantics(f['dna'],f['prediction'])
        f=fixture();f['prediction']['features'][3]['relative_to']='missing'
        with self.assertRaises(ValidationError):apply_semantics(f['dna'],f['prediction'])

    def test_relationships_keep_separate_comparison_keys(self):
        f=fixture();result=apply_semantics(f['dna'],f['prediction'])
        rel=next(x for x in result['features'] if x['name']=='layout.relative_position')
        result['features'].append({**copy.deepcopy(rel),'id':'another','relative_to':'container'})
        report=compare_design(result,result)
        rows=[r for r in report['dimensions']['composition']['features'] if r['name']=='layout.relative_position']
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['score']==1 for r in rows))

    def test_measured_image_pixels_are_not_css_and_colors_are_validated(self):
        f=fixture();dna=f['dna'];dna['vocabulary_version']='0.3'
        e=dna['evidence'][0];e['kind']='measured';e['details']={'coordinate_space':'image-px'}
        for name,value,unit in [('image.width',1440,'image-px'),('color.background_hex','#203060',None)]:
            dna['features']=[{'id':'m','name':name,'value':value,'unit':unit,'status':'known','origin':'measured','confidence':None,'scope':e['scope'],'evidence_ids':[e['id']],'method':'synthetic deterministic image sampler'}]
            validate_dna(dna)
            if name=='image.width':
                dna['features'][0]['unit']='px'
                with self.assertRaises(ValidationError):validate_dna(dna)
        dna['evidence'][0]['kind']='inferred';dna['evidence'][0]['confidence']=0.9
        with self.assertRaises(ValidationError):validate_dna(dna)

    def test_color_difference_coverage_and_legacy_vocabulary(self):
        f=fixture();a=apply_semantics(f['dna'],f['prediction']);b=copy.deepcopy(a)
        next(x for x in b['features'] if x['name']=='color.background_hex')['value']='#304060'
        self.assertEqual(compare_design(a,b)['dimensions']['color_strategy']['score'],0)
        b['features']=[]
        self.assertIsNone(compare_design(a,b)['dimensions']['typography']['score'])
        a['vocabulary_version']='0.2'
        with self.assertRaises(ValidationError):validate_dna(a)

import copy
import unittest
from visparse.semantic import apply_semantics
from visparse.render import render_design, export_policy
from visparse.roundtrip import prepare_roundtrip
from visparse.model import ValidationError
from test_semantic import sample


class ExportIntentTests(unittest.TestCase):
    def fixture(self):
        raw=sample();dna=apply_semantics(raw['dna'],raw['prediction'])
        dna['principles'].append({'id':'simplify','statement':'Simplify the text outlines.',
            'evidence_ids':['observation'],'confidence':0.8,'strength':'SHOULD',
            'scope':copy.deepcopy(dna['evidence'][0]['scope']),'basis':'inferred'})
        return dna

    def test_preserve_excludes_remediation_but_keeps_observation(self):
        dna=self.fixture();before=copy.deepcopy(dna)
        for safe in (True,False):
            output=render_design(dna,intent='preserve',generation_safe=safe)
            self.assertIn('outline-and-shadow',output)
            self.assertNotIn('Simplify the text outlines.',output)
        self.assertEqual(dna,before)

    def test_adapt_qualifies_suggestion_and_preserves_default(self):
        dna=self.fixture()
        self.assertEqual(render_design(dna),render_design(dna,intent='adapt'))
        text=render_design(dna,intent='adapt')
        self.assertIn('Simplify the text outlines.',text)
        self.assertIn('basis=inferred',text)
        self.assertIn('not verified defects',text)

    def test_explicit_policy_is_not_inferred_source_rule(self):
        dna=self.fixture();p=dna['principles'][0]
        p.update(basis='explicit_policy',strength='MUST',statement='Use the supplied accent.')
        self.assertIn('MUST: Use the supplied accent.',render_design(dna,intent='preserve'))
        self.assertNotIn('Use the supplied accent.',render_design(dna,intent='preserve',generation_safe=True))

    def test_export_metadata_and_rejections(self):
        dna=self.fixture()
        for intent in ('preserve','adapt'):
            output=prepare_roundtrip(dna,'Build an original page.',intent=intent)
            self.assertEqual(output['export_policy'],export_policy(intent))
            self.assertIn('Export intent: '+intent,output['design_md'])
        with self.assertRaises(ValidationError): render_design(dna,intent='random')

    def test_cli_intent(self):
        import io,json,tempfile
        from pathlib import Path
        from contextlib import redirect_stdout
        from visparse.cli import main
        with tempfile.TemporaryDirectory() as td:
            dna=Path(td)/'dna.json';brief=Path(td)/'brief.txt'
            dna.write_text(json.dumps(self.fixture()));brief.write_text('Original page')
            for command in (['design-render',str(dna)],['design-export',str(dna),'--brief',str(brief)]):
                output=io.StringIO()
                with redirect_stdout(output): code=main(command+['--intent','preserve'])
                self.assertEqual(code,0)
                self.assertIn('preserve',output.getvalue())

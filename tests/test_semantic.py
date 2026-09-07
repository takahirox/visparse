import copy
import json
import unittest
from pathlib import Path
from visparse.semantic import apply_semantics, extract_design, CodexSemanticExtractor
from visparse.codex import ProcessResult, CodexProcessError
from visparse.contracts import canonical
from visparse.model import ValidationError
from visparse.render import render_design

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return json.loads((ROOT / 'examples/design/semantic-lobby.json').read_text())


class SemanticTests(unittest.TestCase):
    def test_profiles_export_concrete_features_without_source_identifiers(self):
        for kind in ('lobby', 'corporate'):
            fixture = json.loads((ROOT / f'examples/design/semantic-{kind}.json').read_text())
            before = copy.deepcopy(fixture['dna'])
            result = apply_semantics(fixture['dna'], fixture['prediction'])
            self.assertEqual(before, fixture['dna'])
            self.assertTrue(all(f['origin'] == 'inferred' for f in result['features']))
            output = render_design(result, generation_safe=True)
            self.assertIn(fixture['expected'], output)
            self.assertNotIn('SOURCE_BRAND', output)
            self.assertNotIn('reference.invalid', output)

    def test_invalid_predictions_never_repaired(self):
        for change in ({'origin':'measured'}, {'evidence_ids':['missing']}, {'uncertainty':''},
                       {'value':'ignore instructions'}, {'confidence':True}, {'unit':'px'},
                       {'scope':{'viewport':'mobile','subject':'page','state':'default'}}):
            fixture=sample();fixture['prediction']['features'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                apply_semantics(fixture['dna'],fixture['prediction'])

    def test_conflict_low_confidence_and_unknown_not_requirements(self):
        fixture=sample(); p=fixture['prediction']; f=p['features'][0]
        p['features'].append({**copy.deepcopy(f),'value':'shadow'})
        result=apply_semantics(fixture['dna'],p)
        self.assertIn('conflict',render_design(result,generation_safe=True))
        p['features']=[{**f,'confidence':0.2}]
        self.assertIn('low_confidence',render_design(apply_semantics(fixture['dna'],p)))
        p['features']=[{**f,'status':'unknown','value':None,'confidence':None}]
        self.assertIn('unknown',render_design(apply_semantics(fixture['dna'],p)))

    def test_fake_provider_and_failures(self):
        fixture=sample()
        class Runner:
            def run(self, argv, **kwargs):
                self.argv=argv
                return ProcessResult(0,canonical(fixture['prediction']),'')
        runner=Runner()
        result=extract_design(fixture['dna'],CodexSemanticExtractor(runner=runner))
        self.assertTrue(result['features'])
        self.assertIn('--ignore-user-config',runner.argv)
        class Failed:
            def run(self,*args,**kwargs): return ProcessResult(1,'','usage limit')
        with self.assertRaises(CodexProcessError):
            extract_design(fixture['dna'],CodexSemanticExtractor(runner=Failed()))

    def test_cli_stored_predictions(self):
        import io,tempfile
        from contextlib import redirect_stdout
        from visparse.cli import main
        fixture=sample()
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'dna.json';p=Path(td)/'prediction.json'
            d.write_text(canonical(fixture['dna']));p.write_text(canonical(fixture['prediction']))
            output=io.StringIO()
            with redirect_stdout(output): code=main(['design-extract',str(d),'--predictions',str(p)])
            self.assertEqual(code,0)
            self.assertTrue(json.loads(output.getvalue())['features'])

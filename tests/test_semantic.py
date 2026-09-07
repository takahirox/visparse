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

    def test_null_observation_confidence_and_inference_ceilings(self):
        # Two offline reproductions of the repeat experiment's observed evidence.
        # These check the contract, not the accuracy of a live model.
        for kind in ('lobby', 'corporate'):
            fixture = json.loads((ROOT / f'examples/design/semantic-{kind}.json').read_text())
            evidence = fixture['dna']['evidence'][0]
            self.assertIsNone(evidence['confidence'])
            result = apply_semantics(fixture['dna'], fixture['prediction'])
            self.assertIn(fixture['expected'], render_design(result, intent='preserve'))
            evidence.update(kind='inferred', confidence=0.4)
            with self.assertRaisesRegex(ValidationError, 'exceeds supporting inference'):
                apply_semantics(fixture['dna'], fixture['prediction'])
            feature = fixture['prediction']['features'][0]
            feature['confidence'] = 0.3
            self.assertIn('low_confidence', render_design(apply_semantics(fixture['dna'], fixture['prediction'])))
            evidence['confidence'] = 0
            with self.assertRaises(ValidationError):
                apply_semantics(fixture['dna'], fixture['prediction'])
            feature['confidence'] = 0
            result = apply_semantics(fixture['dna'], fixture['prediction'])
            self.assertEqual(result['features'][0]['confidence'], 0)

    def test_region_confidence_does_not_turn_missing_metadata_into_zero(self):
        fixture = sample()
        source_scope = fixture['dna']['evidence'][0]['scope']
        region = dict(id='hero', viewport=source_scope['viewport'], state=source_scope['state'],
                      evidence_ids=['observation'], confidence=0.8, method='Identify visible hero',
                      uncertainty='Only the supplied viewport')
        prediction = fixture['prediction']
        prediction.update(schema_version='0.2', regions=[region])
        feature = prediction['features'][0]
        feature.update(scope={**source_scope, 'subject':'hero'}, evidence_ids=['region:hero'], confidence=0.8)
        result = apply_semantics(fixture['dna'], prediction)
        self.assertEqual(result['features'][0]['confidence'], 0.8)
        region['confidence'] = 0
        with self.assertRaises(ValidationError):
            apply_semantics(fixture['dna'], prediction)
        feature['confidence'] = 0
        self.assertIn('low_confidence', render_design(apply_semantics(fixture['dna'], prediction)))

    def test_provider_instructions_explain_unspecified_confidence(self):
        fixture = sample()
        class Runner:
            def run(self, argv, **kwargs):
                self.prompt = argv[-1]
                return ProcessResult(0, canonical(fixture['prediction']), '')
        runner = Runner()
        extract_design(fixture['dna'], CodexSemanticExtractor(runner=runner))
        self.assertIn('unspecified confidence, not zero', runner.prompt)
        self.assertIn('Only supporting evidence of kind inferred', runner.prompt)
        self.assertIn('genuine inferred confidence of zero', runner.prompt)

    def test_timeout_defaults_overrides_and_invalid_values(self):
        from unittest.mock import Mock
        fixture = sample()
        for timeout in (300, 450, 900, 1):
            runner = Mock()
            runner.run.return_value = ProcessResult(0, canonical(fixture['prediction']), '')
            provider = CodexSemanticExtractor(runner=runner) if timeout == 300 else CodexSemanticExtractor(runner=runner, timeout_seconds=timeout)
            extract_design(fixture['dna'], provider)
            self.assertEqual(runner.run.call_args.kwargs['timeout'], timeout)
            self.assertEqual(runner.run.call_count, 1)
        for timeout in (0, -1, 901, float('nan'), float('inf'), True):
            runner = Mock()
            with self.subTest(timeout=timeout), self.assertRaises(ValidationError):
                extract_design(fixture['dna'], CodexSemanticExtractor(runner=runner, timeout_seconds=timeout))
            runner.run.assert_not_called()

    def test_timeout_is_reported_without_retry(self):
        import subprocess
        from unittest.mock import Mock
        from visparse.codex import CodexTimeoutError
        fixture = sample()
        runner = Mock()
        runner.run.side_effect = subprocess.TimeoutExpired('codex', 300)
        with self.assertRaisesRegex(CodexTimeoutError, '300 seconds; no automatic retry'):
            extract_design(fixture['dna'], CodexSemanticExtractor(runner=runner))
        self.assertEqual(runner.run.call_count, 1)

    def test_cli_timeout_is_forwarded_only_for_live_extraction(self):
        import io, tempfile
        from contextlib import redirect_stdout
        from unittest.mock import Mock, patch
        from visparse.cli import main
        fixture = sample()
        with tempfile.TemporaryDirectory() as td:
            d, p = Path(td)/'dna.json', Path(td)/'prediction.json'
            d.write_text(canonical(fixture['dna'])); p.write_text(canonical(fixture['prediction']))
            for options, timeout in [([], 300), (['--timeout-seconds', '450'], 450)]:
                provider = Mock()
                provider.extract.return_value = fixture['prediction']
                with patch('visparse.cli.CodexSemanticExtractor', return_value=provider) as factory, redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['design-extract', str(d), *options]), 0)
                factory.assert_called_once_with(timeout_seconds=timeout)
                provider.extract.assert_called_once()
            with patch('visparse.cli.CodexSemanticExtractor') as factory, redirect_stdout(io.StringIO()):
                self.assertEqual(main(['design-extract', str(d), '--predictions', str(p), '--timeout-seconds', '450']), 0)
            factory.assert_not_called()

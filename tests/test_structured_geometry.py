import copy
import json
import unittest
from unittest.mock import Mock

from test_design import evidence, profile, FakeRunner
from visparse.codex import CodexValidationError, ProcessResult
from visparse.design import CodexDesignAnalyzer, validate_design_profile
from visparse.dna import build_dna
from visparse.model import ValidationError
from visparse.render import render_design
from visparse.semantic import CodexSemanticExtractor, extract_design


def geometry_profile():
    value = profile([evidence('source')])
    value['measurements'] = []
    interpretation = value['interpretations'][0]
    interpretation.update(category='layout', geometry={
        'region': 'hero-headline', 'coordinate_space': 'viewport-ratio',
        'bounds': {axis: {'value': v, 'uncertainty': 'Approximate visible edge; roughly 0.02 tolerance.'}
                   for axis, v in [('x', .17), ('y', .3), ('width', .32), ('height', None)]}})
    interpretation['geometry']['bounds']['height']['uncertainty'] = 'Lower text boundary is obscured.'
    return value


class StructuredGeometryTests(unittest.TestCase):
    def test_legacy_profiles_remain_valid_but_cannot_claim_new_extension(self):
        value = geometry_profile(); value['schema_version'] = '0.1'
        with self.assertRaises(ValidationError): validate_design_profile(value)
        del value['interpretations'][0]['geometry']
        validate_design_profile(value)

    def test_geometry_validation_rejects_invalid_coordinates_and_duplicate_regions(self):
        for axis, v in [('x', True), ('y', -0.1), ('width', 0), ('height', float('nan')), ('width', .9)]:
            value = geometry_profile(); value['interpretations'][0]['geometry']['bounds'][axis]['value'] = v
            with self.subTest(axis=axis, value=v), self.assertRaises(ValidationError): validate_design_profile(value)
        for change in [{'region': 'Source Brand'}, {'coordinate_space': 'css-px'}, {'bounds': {}}]:
            value = geometry_profile(); value['interpretations'][0]['geometry'].update(change)
            with self.assertRaises(ValidationError): validate_design_profile(value)
        value = geometry_profile()
        value['interpretations'].append({**copy.deepcopy(value['interpretations'][0]), 'id': 'duplicate-geometry'})
        with self.assertRaisesRegex(ValidationError, 'duplicate geometry'): validate_design_profile(value)

    def test_geometry_must_be_grounded_in_one_source(self):
        value = geometry_profile()
        value['sources'].append({'id':'other','kind':'screenshot','locator':'memory://other','role':'reference'})
        value['provenance']['inputs'].append('other')
        value['observations'][0]['source_ids'].append('other')
        with self.assertRaisesRegex(ValidationError, 'exactly one source'): validate_design_profile(value)

    def test_request_coverage_is_enforced_without_inventing_missing_regions(self):
        value = geometry_profile()
        runner = FakeRunner(ProcessResult(0, json.dumps(value), ''))
        analyzer = CodexDesignAnalyzer(runner=runner, estimate_geometry=True, geometry_regions=('hero-headline',))
        self.assertEqual(analyzer.analyze([evidence('source')]), value)
        self.assertIn('hero-headline', runner.argv[-1])
        self.assertIn('Use null with a concrete reason', runner.argv[-1])
        analyzer.geometry_regions = ('hero-headline', 'hero')
        with self.assertRaisesRegex(CodexValidationError, 'missing requested geometry.*hero'):
            analyzer.analyze([evidence('source')])
        for bound in value['interpretations'][0]['geometry']['bounds'].values():
            bound.update(value=None, uncertainty='Requested region is not identifiable.')
        analyzer.geometry_regions = ('hero-headline',)
        analyzer.runner = FakeRunner(ProcessResult(0, json.dumps(value), ''))
        self.assertEqual(analyzer.analyze([evidence('source')]), value)

    def test_bad_configuration_never_calls_provider(self):
        for kwargs in [dict(geometry_regions=['hero']), dict(estimate_geometry=True, geometry_regions='hero'),
                       dict(estimate_geometry=True, geometry_regions=['hero','hero']),
                       dict(estimate_geometry=True, geometry_regions=[[]])]:
            runner = Mock()
            with self.assertRaises(ValidationError):
                CodexDesignAnalyzer(runner=runner, **kwargs).analyze([evidence('source')])
            runner.run.assert_not_called()

    def test_requests_cover_each_image_and_target_geometry_stays_out_of_dna(self):
        reference, target = evidence('source'), evidence('target')
        value = profile([reference], [target]); value['measurements'] = []
        value['interpretations'][0] = geometry_profile()['interpretations'][0]
        analyzer = CodexDesignAnalyzer(estimate_geometry=True, geometry_regions=('hero-headline',),
                                      runner=FakeRunner(ProcessResult(0, json.dumps(value), '')))
        with self.assertRaisesRegex(CodexValidationError, 'missing requested geometry.*target'):
            analyzer.analyze([reference], [target])
        target_geometry = copy.deepcopy(value['interpretations'][0])
        target_geometry.update(id='target-geometry', observation_ids=['observation-2'])
        value['interpretations'].append(target_geometry)
        analyzer.runner = FakeRunner(ProcessResult(0, json.dumps(value), ''))
        self.assertEqual(analyzer.analyze([reference], [target]), value)
        dna = build_dna(value)
        self.assertEqual(len(dna['features']), 4)
        self.assertFalse(any(e['id'] == 'profile:target-geometry' for e in dna['evidence']))

    def test_direct_projection_keeps_unknowns_scope_confidence_and_uncertainty(self):
        value = geometry_profile()
        dna = build_dna(value, contexts={'profile:source':{'subject':'page','viewport':'1440x900','state':'initial'}})
        self.assertEqual(len(dna['features']), 4)
        for f in dna['features']:
            self.assertEqual((f['origin'], f['confidence'], f['scope']['subject']), ('inferred', .7, 'hero-headline'))
        self.assertEqual(next(f for f in dna['features'] if f['name'].endswith('height_ratio'))['status'], 'unknown')
        output = render_design(dna, intent='preserve')
        self.assertIn('geometry.viewport_x_ratio: 0.17ratio', output)
        self.assertIn('inferred, confidence=0.70', output)
        self.assertIn('0.02 tolerance', output)
        self.assertIn('height_ratio', output)
        self.assertEqual(next(e for e in dna['evidence'] if e['id'] == 'profile:interpretation-1')['kind'], 'inferred')
        with self.assertRaisesRegex(ValidationError, 'conflicts with supplied context'):
            build_dna(value, contexts={'profile:interpretation-1':{'subject':'other','viewport':'1440x900','state':'initial'}})
        value['confidence'][0]['level'] = .4
        self.assertIn('low_confidence', render_design(build_dna(value), intent='preserve'))

    def test_semantic_step_knows_which_geometry_is_already_mapped(self):
        dna = build_dna(geometry_profile())
        class Runner:
            def run(self, argv, **kwargs):
                self.prompt = argv[-1]
                return ProcessResult(0, '{"schema_version":"0.2","features":[]}', '')
        runner = Runner()
        result = extract_design(dna, CodexSemanticExtractor(runner=runner))
        self.assertEqual(result['features'], dna['features'])
        self.assertIn('already_mapped', runner.prompt)
        self.assertIn('geometry.viewport_x_ratio', runner.prompt)

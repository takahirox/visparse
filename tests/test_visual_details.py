import copy
import json
import unittest
from unittest.mock import Mock

from test_design import FakeRunner, evidence, profile
from test_structured_geometry import geometry_profile
from visparse.codex import CodexValidationError, ProcessResult
from visparse.design import CodexDesignAnalyzer, validate_design_profile
from visparse.dna import build_dna, feature_key, validate_dna
from visparse.model import ValidationError
from visparse.render import render_design
from visparse.semantic import CodexSemanticExtractor, extract_design
from visparse.visual_details import APPEARANCE


def q(value, reason='Approximate visual estimate; original CSS is unavailable.'):
    return {'value': value, 'uncertainty': reason}


def bounds(x=.1, y=.2, width=.3, height=.4):
    return dict(zip(('x', 'y', 'width', 'height'), map(q, (x, y, width, height))))


def details_profile():
    result = profile([evidence('source')]); result['measurements'] = []
    base = result['interpretations'][0]
    appearance = {'region': 'headline', 'properties': dict(zip(APPEARANCE, map(q,
        ('#ffffff', '#123456', None, 700, 'condensed', 2, -.02, 1.1))))}
    media = {'region': 'hero-photo', 'coordinate_space': 'media-ratio', 'coverage': q('partial'),
             'subjects': [{'region': 'table', 'kind': q('table'), 'bounds': bounds(), 'visibility': q('occluded'), 'crop': q('none')}]}
    result['interpretations'] = [
        {**copy.deepcopy(base), 'id': 'appearance', 'category': 'typography', 'appearance': appearance},
        {**copy.deepcopy(base), 'id': 'composition', 'category': 'imagery_media', 'media': media},
    ]
    result['principles'][0]['interpretation_ids'] = ['appearance']
    return result


class VisualDetailsTests(unittest.TestCase):
    def test_legacy_versions_and_new_vocabulary_are_explicit(self):
        for version in ('0.1', '0.2'):
            old = profile([evidence('source')]); old['schema_version'] = version
            validate_design_profile(old)
            new = details_profile(); new['schema_version'] = version
            with self.assertRaises(ValidationError): validate_design_profile(new)
        legacy = geometry_profile(); legacy['schema_version'] = '0.2'
        validate_design_profile(legacy)
        legacy['interpretations'][0]['geometry']['visibility'] = q('occluded')
        with self.assertRaises(ValidationError): validate_design_profile(legacy)
        dna = build_dna(details_profile())
        self.assertEqual(dna['vocabulary_version'], '0.5')
        for version in ('0.1', '0.2', '0.3', '0.4'):
            dna['vocabulary_version'] = version
            with self.assertRaises(ValidationError): validate_dna(dna)

    def test_appearance_projects_without_reextracting_or_promoting_estimates(self):
        dna = build_dna(details_profile())
        features = {f['name']: f for f in dna['features'] if f['scope']['subject'] == 'headline'}
        self.assertEqual(len(features), 8)
        self.assertEqual(features['color.background_hex']['value'], '#123456')
        self.assertEqual(features['color.accent_hex']['status'], 'unknown')
        self.assertEqual(features['typography.letter_spacing_em']['unit'], 'em')
        for f in features.values():
            self.assertEqual((f['origin'], f['confidence'], f['evidence_ids']), ('inferred', .7, ['profile:appearance']))
            self.assertIn('original CSS', f['uncertainty'])
        for safe in (False, True):
            output = render_design(dna, intent='preserve', generation_safe=safe)
            self.assertIn('#123456', output)
            self.assertIn('not a sampled pixel', output)
            self.assertIn('color.accent_hex', output)
            self.assertIn('unknown', output)
            self.assertIn('font size', output)
        value = details_profile(); value['confidence'][0]['level'] = .3
        output = render_design(build_dna(value), intent='preserve')
        self.assertNotIn('#123456', output)
        self.assertIn('low_confidence', output)

    def test_appearance_rejects_invalid_and_incomplete_properties(self):
        for field, v in [('foreground', '#FFF'), ('font_weight', True), ('font_weight', 1001),
                         ('line_count', 2.5), ('width_style', []), ('line_height_factor', 0),
                         ('letter_spacing_em', float('inf'))]:
            value = details_profile(); value['interpretations'][0]['appearance']['properties'][field] = q(v)
            with self.subTest(field=field), self.assertRaises(ValidationError): validate_design_profile(value)
        for change in ('missing-field', 'missing-reason'):
            value = details_profile(); props = value['interpretations'][0]['appearance']['properties']
            if change == 'missing-field': del props['accent']
            else: props['accent']['uncertainty'] = ''
            with self.assertRaises(ValidationError): validate_design_profile(value)

    def test_full_bounds_preserve_hidden_extent_and_unknowns_separately(self):
        value = geometry_profile()
        geometry = value['interpretations'][0]['geometry']
        geometry.update(visibility=q('occluded-and-clipped'), full_bounds=bounds(-.05, .3, .6, None))
        dna = build_dna(value)
        features = {f['name']: f for f in dna['features']}
        self.assertEqual(features['geometry.viewport_x_ratio']['value'], .17)
        self.assertEqual(features['geometry.full_viewport_x_ratio']['value'], -.05)
        self.assertEqual(features['geometry.full_viewport_height_ratio']['status'], 'unknown')
        output = render_design(dna, intent='preserve', generation_safe=True)
        self.assertIn('visible fragment', output)
        self.assertIn('separate full-element estimate', output)
        self.assertIn('occluded-and-clipped', output)

    def test_full_bounds_cannot_exclude_visible_fragment_or_claim_false_visibility(self):
        for full in (bounds(.2, .3, .6, None), bounds(.1, .3, .1, None), bounds(.0, .3, .32, None)):
            value = geometry_profile(); geo = value['interpretations'][0]['geometry']
            geo.update(visibility=q('occluded'), full_bounds=full)
            with self.assertRaises(ValidationError): validate_design_profile(value)
        value = geometry_profile(); geo = value['interpretations'][0]['geometry']
        geo.update(visibility=q('fully-visible'), full_bounds=bounds(.1, .3, .5, None))
        with self.assertRaises(ValidationError): validate_design_profile(value)
        del geo['visibility']
        with self.assertRaises(ValidationError): validate_design_profile(value)

    def test_media_local_subjects_keep_frame_parent_and_source(self):
        value = details_profile()
        # Reusing a subject label in a different media region must not merge them.
        duplicate = copy.deepcopy(value['interpretations'][1]); duplicate['id'] = 'composition-2'
        duplicate['media']['region'] = 'lower-photo'; value['interpretations'].append(duplicate)
        dna = build_dna(value)
        subjects = [f for f in dna['features'] if f['name'] == 'imagery.subject_width_ratio']
        self.assertEqual({f['relative_to'] for f in subjects}, {'hero-photo', 'lower-photo'})
        self.assertEqual(len({feature_key(f) for f in subjects}), 2)
        for f in subjects:
            e = next(e for e in dna['evidence'] if e['id'] == f['evidence_ids'][0])
            self.assertEqual(e['details']['coordinate_space'], 'media-ratio')
            self.assertEqual(e['source_ids'], ['profile:source'])
            self.assertEqual(e['scope'], f['scope'])
            self.assertEqual(e['confidence'], f['confidence'])
        changed = {**subjects[0], 'value': .5}
        self.assertEqual(feature_key(subjects[0]), feature_key(changed))
        for safe in (True, False):
            output = render_design(dna, generation_safe=safe, intent='preserve')
            self.assertIn('visible enclosing media rectangle', output)
            self.assertIn('Relative to', output)
            self.assertIn('imagery.subject_kind: table', output)
            if safe: self.assertNotIn('hero-photo', output)
        subjects[0]['relative_to'] = 'missing-media'
        with self.assertRaisesRegex(ValidationError, 'target missing'): validate_dna(dna)

    def test_media_rejects_conflicting_crops_and_invalid_frames(self):
        for visibility, crop in [('fully-visible', 'left'), ('occluded', 'bottom'), ('clipped', 'none')]:
            value = details_profile(); subject = value['interpretations'][1]['media']['subjects'][0]
            subject.update(visibility=q(visibility), crop=q(crop))
            with self.assertRaises(ValidationError): validate_design_profile(value)
        for change in ('frame', 'bounds', 'duplicate'):
            value = details_profile(); media = value['interpretations'][1]['media']
            if change == 'frame': media['coordinate_space'] = 'viewport-ratio'
            elif change == 'bounds': media['subjects'][0]['bounds']['width'] = q(.95)
            else: media['subjects'].append(copy.deepcopy(media['subjects'][0]))
            with self.assertRaises(ValidationError): validate_design_profile(value)

    def test_extension_scope_source_uniqueness_and_target_exclusion(self):
        for extension in ('appearance', 'media'):
            original = details_profile()
            index = 0 if extension == 'appearance' else 1
            value = copy.deepcopy(original); duplicate = copy.deepcopy(value['interpretations'][index])
            duplicate['id'] += '-duplicate'; value['interpretations'].append(duplicate)
            with self.assertRaisesRegex(ValidationError, 'duplicate'): validate_design_profile(value)
            value = copy.deepcopy(original)
            value['sources'].append({'id': 'target', 'kind': 'screenshot', 'locator': 'memory://target', 'role': 'target'})
            value['provenance']['inputs'].append('target')
            value['observations'].append({'id': 'target-observation', 'source_ids': ['target'], 'category': 'layout', 'statement': 'Target region.'})
            record = value['interpretations'][index]
            record['observation_ids'].append('target-observation')
            with self.assertRaisesRegex(ValidationError, 'exactly one source'): validate_design_profile(value)
            record['observation_ids'] = ['target-observation']
            dna = build_dna(value)
            self.assertFalse(any(e['id'] == 'profile:' + record['id'] for e in dna['evidence']))
            self.assertFalse(any('profile:target' in e['source_ids'] for e in dna['evidence']))
            with self.assertRaisesRegex(ValidationError, 'conflicts with supplied context'):
                build_dna(original, contexts={'profile:' + record['id']: {'viewport': '1440x900', 'state': 'default', 'subject': 'wrong'}})

    def test_requests_require_coverage_and_unknowns_without_fabrication(self):
        value = details_profile()
        runner = FakeRunner(ProcessResult(0, json.dumps(value), ''))
        analyzer = CodexDesignAnalyzer(runner=runner, estimate_geometry=True,
                                      appearance_regions=('headline',), media_regions=('hero-photo',))
        self.assertEqual(analyzer.analyze([evidence('source')]), value)
        self.assertIn('media-ratio', runner.argv[-1])
        analyzer.appearance_regions = ('absent',)
        with self.assertRaisesRegex(CodexValidationError, 'missing requested appearance'): analyzer.analyze([evidence('source')])
        analyzer.appearance_regions = ('headline',); analyzer.media_regions = ('absent',)
        with self.assertRaisesRegex(CodexValidationError, 'missing requested media'): analyzer.analyze([evidence('source')])
        value['interpretations'][1]['media'].update(region='absent', subjects=[], coverage=q(None, 'No identifiable media.'))
        analyzer.runner = FakeRunner(ProcessResult(0, json.dumps(value), ''))
        self.assertEqual(analyzer.analyze([evidence('source')]), value)
        self.assertIn('imagery.composition_coverage', render_design(build_dna(value)))

    def test_invalid_configuration_and_unrequested_media_are_rejected(self):
        for kwargs in ({'media_regions': ['hero']}, {'appearance_regions': 'hero'},
                       {'appearance_regions': ['hero', 'hero']}, {'appearance_regions': ['bad name']}):
            runner = Mock()
            with self.assertRaises(ValidationError): CodexDesignAnalyzer(runner=runner, **kwargs).analyze([evidence('source')])
            runner.run.assert_not_called()
        runner = FakeRunner(ProcessResult(0, json.dumps(details_profile()), ''))
        with self.assertRaisesRegex(CodexValidationError, 'media geometry was not requested'):
            CodexDesignAnalyzer(runner=runner).analyze([evidence('source')])

    def test_semantic_stage_preserves_all_directly_projected_details(self):
        dna = build_dna(details_profile())
        class Runner:
            def run(self, argv, **kwargs):
                self.argv = argv
                return ProcessResult(0, '{"schema_version":"0.2","features":[]}', '')
        runner = Runner()
        result = extract_design(dna, CodexSemanticExtractor(runner=runner))
        self.assertEqual(result['features'], dna['features'])
        self.assertIn('appearance or media estimates', runner.argv[-1])
        self.assertIn('imagery.subject_width_ratio', runner.argv[-1])


if __name__ == '__main__':
    unittest.main()

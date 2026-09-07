import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from visparse.cli import main
from visparse.render import render_design
from visparse.semantic import apply_semantics
from visparse.trace import trace_guidance

ROOT = Path(__file__).resolve().parents[1]


def sample():
    f = json.loads((ROOT / 'examples/design/semantic-spatial.json').read_text())
    return apply_semantics(f['dna'], f['prediction'])


class TraceTests(unittest.TestCase):
    def test_region_ancestry_counts_and_actual_rendered_rules(self):
        dna = sample()
        before = copy.deepcopy(dna)
        for safe in (False, True):
            report = trace_guidance(dna, generation_safe=safe, intent='preserve')
            rendered = render_design(dna, generation_safe=safe, intent='preserve')
            self.assertEqual(report['counts']['raw_features'], len(dna['features']))
            self.assertEqual(report['counts']['retained_groups'], rendered.count('- SHOULD:'))
            for group in report['groups']:
                self.assertIn('observation', group['ancestry_evidence_ids'])
                self.assertTrue(group['source_ids'])
                self.assertFalse(group['ancestry_issues'])
            self.assertNotIn('observation', report['evidence_without_feature_lineage'])
        self.assertEqual(dna, before)

    def test_rejection_reasons_and_grouped_counts(self):
        dna = sample()
        first = dna['features'][0]
        dna['features'] = [first]
        for change, expected in [({'confidence': 0}, 'low_confidence'),
                                 ({'status': 'unknown', 'value': None, 'confidence': None}, 'unknown'),
                                 ({'name': 'color.background', 'value': 'blue'}, 'free_text_filtered')]:
            changed = copy.deepcopy(dna)
            changed['features'][0].update(change)
            report = trace_guidance(changed, generation_safe=True)
            self.assertEqual(report['counts']['group_export_statuses'], {expected: 1})
            self.assertEqual(report['counts']['retained_groups'], 0)
        dna['features'].append({**copy.deepcopy(first), 'id': 'opposite', 'value': first['value'] + 1})
        report = trace_guidance(dna)
        self.assertEqual(report['counts']['raw_features'], 2)
        self.assertEqual(report['counts']['feature_groups'], 1)
        self.assertEqual(report['groups'][0]['export_status'], 'conflict')

    def test_safe_redaction_does_not_create_cross_state_conflicts(self):
        dna = sample()
        first = dna['features'][0]
        anchor = next(e for e in dna['evidence'] if e['id'] == first['evidence_ids'][0])
        first['scope']['state'] = 'original-state-one'
        anchor['scope']['state'] = 'original-state-one'
        dna['features'] = [first]
        other_scope = {**first['scope'], 'state': 'original-state-two'}
        dna['evidence'].append({**copy.deepcopy(anchor), 'id': 'other', 'scope': other_scope})
        dna['features'].append({**copy.deepcopy(first), 'id': 'other-feature', 'scope': other_scope,
                                'value': first['value'] + 1, 'evidence_ids': ['other']})
        report = trace_guidance(dna, generation_safe=True)
        rendered = render_design(dna, generation_safe=True)
        self.assertEqual(report['counts']['retained_groups'], 2)
        self.assertEqual(rendered.count('- SHOULD:'), 2)
        self.assertNotIn('original-state', rendered)
        self.assertNotIn('conflict', rendered)
        self.assertIn('state=state-2', rendered)
        self.assertIn('state=state-3', rendered)

    def test_invalid_ancestry_metadata_is_bounded_and_reported(self):
        for links, expected in [(['missing'], 'unresolved_support_metadata'),
                                (123, 'malformed_support_metadata'),
                                (['observation'], 'cyclic_support_metadata')]:
            dna = sample()
            dna['evidence'][0]['details']['supporting_evidence_ids'] = links
            report = trace_guidance(dna)
            self.assertTrue(any(expected in g['ancestry_issues'] for g in report['groups']))

    def test_principle_exclusions_and_cli(self):
        dna = sample()
        e = dna['evidence'][0]
        dna['principles'] = [dict(id='principle', statement='Adapt the layout', evidence_ids=[e['id']],
                                 confidence=.9, strength='SHOULD', scope=e['scope'], basis='inferred')]
        self.assertEqual(trace_guidance(dna, intent='preserve')['principles'][0]['export_status'], 'adaptation_filtered')
        self.assertEqual(trace_guidance(dna, generation_safe=True)['principles'][0]['export_status'], 'free_text_filtered')
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'dna.json'; path.write_text(json.dumps(dna))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(['design-trace', str(path), '--intent', 'preserve']), 0)
            self.assertEqual(json.loads(out.getvalue())['counts'], trace_guidance(dna, intent='preserve')['counts'])

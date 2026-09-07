import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from visparse.cli import main
from visparse.coverage import audit_coverage
from visparse.model import ValidationError
from visparse.semantic import apply_semantics

ROOT = Path(__file__).resolve().parents[1]


def sample(kind='corporate'):
    fixture = json.loads((ROOT / f'examples/design/semantic-{kind}.json').read_text())
    f = fixture['prediction']['features'][0]
    expectations = {'schema_version': '0.1', 'items': [
        {'id': 'expected', 'name': f['name'], 'scope': f['scope'],
         'source_status': 'supported', 'evidence_ids': f['evidence_ids']}]}
    return fixture, expectations


class CoverageTests(unittest.TestCase):
    def test_both_patterns_distinguish_missing_extraction_from_coverage(self):
        for kind in ('lobby', 'corporate'):
            fixture, expectations = sample(kind)
            self.assertEqual(audit_coverage(fixture['dna'], expectations)['counts'], {'extraction_gap': 1})
            enriched = apply_semantics(fixture['dna'], fixture['prediction'])
            self.assertEqual(audit_coverage(enriched, expectations)['counts'], {'covered': 1})

    def test_source_absence_unknown_judgment_and_confidence_are_distinct(self):
        fixture, expectations = sample()
        e = expectations['items'][0]
        for source_status, expected in [('absent', 'source_absent'), ('unknown', 'source_unknown')]:
            e['source_status'] = source_status
            self.assertEqual(audit_coverage(fixture['dna'], expectations)['items'][0]['status'], expected)
        enriched = apply_semantics(fixture['dna'], fixture['prediction'])
        e['source_status'] = 'absent'
        self.assertEqual(audit_coverage(enriched, expectations)['counts'], {'declaration_conflict': 1})
        e['source_status'] = 'supported'
        enriched['features'][0]['confidence'] = 0
        self.assertEqual(audit_coverage(enriched, expectations)['counts'], {'low_confidence': 1})
        enriched['features'][0].update(status='unknown', value=None, confidence=None)
        self.assertEqual(audit_coverage(enriched, expectations)['counts'], {'explicit_unknown': 1})
        e['source_status'] = 'absent'
        self.assertEqual(audit_coverage(enriched, expectations)['counts'], {'source_absent': 1})

    def test_invalid_declarations_and_scope_boundaries(self):
        for change in ({'name': []}, {'source_status': []}, {'source_status': 'guess'},
                       {'evidence_ids': []}, {'evidence_ids': ['missing']}, {'relative_to': None},
                       {'scope': {'subject': 'page', 'viewport': '390x844', 'state': 'default'}}):
            fixture, expectations = sample()
            expectations['items'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                audit_coverage(fixture['dna'], expectations)
        fixture, expectations = sample()
        expectations['items'].append({**expectations['items'][0], 'id': 'duplicate'})
        with self.assertRaises(ValidationError):
            audit_coverage(fixture['dna'], expectations)

    def test_relationship_axes_are_not_false_conflicts(self):
        fixture = json.loads((ROOT / 'examples/design/semantic-spatial.json').read_text())
        dna = apply_semantics(fixture['dna'], fixture['prediction'])
        rel = next(f for f in dna['features'] if f['name'] == 'layout.relative_position')
        dna['features'].append({**copy.deepcopy(rel), 'id': 'aligned', 'value': 'aligned-left'})
        expected = {'schema_version': '0.1', 'items': [dict(id='rel', name=rel['name'],
            scope=rel['scope'], relative_to=rel['relative_to'], source_status='supported', evidence_ids=rel['evidence_ids'])]}
        self.assertEqual(audit_coverage(dna, expected)['counts'], {'covered': 1})
        dna['features'].append({**copy.deepcopy(rel), 'id': 'opposite', 'value': 'below'})
        self.assertEqual(audit_coverage(dna, expected)['counts'], {'conflict': 1})

    def test_cli_and_input_immutability(self):
        fixture, expectations = sample()
        before = copy.deepcopy((fixture, expectations))
        with tempfile.TemporaryDirectory() as td:
            d, e = Path(td) / 'dna.json', Path(td) / 'expected.json'
            d.write_text(json.dumps(fixture['dna'])); e.write_text(json.dumps(expectations))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['design-coverage', str(d), '--expectations', str(e)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())['counts'], {'extraction_gap': 1})
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(main(['design-coverage', str(d), '--expectations', str(e), '--min-confidence', 'nan']), 2)
        self.assertEqual((fixture, expectations), before)

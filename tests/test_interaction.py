import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visparse.interaction import OUTCOMES, load_sequence, summarize_sequence, validate_sequence
from visparse.contracts import canonical
from visparse.model import ValidationError
from visparse.cli import main
from interaction_fixtures import sequence


class InteractionTests(unittest.TestCase):
    def test_outcomes_and_reload_remain_explicit(self):
        for outcome in OUTCOMES:
            value = sequence(outcome)
            self.assertEqual(load_sequence(canonical(value)), value)
            self.assertEqual(summarize_sequence(value)["outcomes"][outcome], 1)
        self.assertEqual(validate_sequence(sequence(kind="reload"))["sessions"][0]["reset"], "fresh context, empty storage")

    def test_invalid_context_timing_ancestry_and_bounds(self):
        mutations = [lambda v: v.update(schema_version="next"),
            lambda v: v["actions"][0].update(order=True),
            lambda v: v["actions"][0].update(after=[]),
            lambda v: v["actions"][0].update(before=["missing"]),
            lambda v: v["actions"][0].update(start_ms=float("nan")),
            lambda v: v["captures"][1].update(start_ms=1),
            lambda v: v["clocks"][0].update(unit="seconds"),
            lambda v: v["targets"][0].update(session_id="elsewhere"),
            lambda v: v["actions"][0].update(input_ref="secret"),
            lambda v: v["expectations"][0].update(id="action"),
            lambda v: v["actions"].extend(copy.deepcopy(v["actions"]) * 100)]
        for mutate in mutations:
            value = sequence(); mutate(value)
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_sequence(value)
        value = sequence(); other = dict(value["clocks"][0], id="other-clock"); value["clocks"].append(other)
        value["captures"][1]["clock_id"] = "other-clock"
        with self.assertRaisesRegex(ValidationError, "not aligned"):
            validate_sequence(value)

    def test_v2_retains_typed_keys_scroll_and_wait_without_inventing_legacy_data(self):
        for kind,parameters in [('press',{'key':'Escape'}),('scroll',{'delta':[0,200]}),('wait',{'wait_ms':250})]:
            value=sequence(kind=kind);value['schema_version']='interaction-sequence/0.2';value['actions'][0]['input_parameters']=parameters
            self.assertEqual(load_sequence(canonical(value))['actions'][0]['input_parameters'],parameters)
            del value['actions'][0]['input_parameters']
            with self.assertRaises(ValidationError):validate_sequence(value)
        self.assertNotIn('input_parameters',validate_sequence(sequence(kind='press'))['actions'][0])

    def test_expected_facts_are_separate_and_summary_offline(self):
        value = sequence("unobserved")
        self.assertEqual(summarize_sequence(value)["outcomes"]["observed-effect"], 0)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["ux-summary", "examples/interaction/sequence.json"]), 0)
        self.assertIn("atomic_snapshot", output.getvalue())

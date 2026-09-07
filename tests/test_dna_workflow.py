from __future__ import annotations

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse import ValidationError, build_dna, compare_design, evaluate_analysis, evaluate_roundtrip, load_dna, normalize_dna, prepare_roundtrip, render_design, validate_dna
from visparse.cli import main
from visparse.contracts import load_json
from visparse.dna import DEFAULT_SCOPE
from design_fixtures import analysis_fixture, collector_bundle, dna
from test_design import evidence, profile


class DNAContractTests(unittest.TestCase):
    def test_canonical_roundtrip(self):
        value = dna()
        self.assertEqual(normalize_dna(load_dna(normalize_dna(value))), normalize_dna(value))

    def test_invalid_shapes_versions_numbers_references_and_promotions(self):
        for mutate in (
            lambda v: v.update(schema_version="next"),
            lambda v: v.update(vocabulary_version="next"),
            lambda v: v.update(extra=True),
            lambda v: v["features"][0].update(value=True),
            lambda v: v["features"][0].update(unit="rem"),
            lambda v: v["features"][0].update(evidence_ids=["missing"]),
            lambda v: v["features"][1].update(origin="observed"),
            lambda v: v["features"][1].update(confidence=float("nan")),
            lambda v: v["sources"][0].update(role="target"),
            lambda v: v["principles"][0].update(strength="NEVER"),
            lambda v: v["features"][0].update(id="font"),
            lambda v: v["features"][0].update(status="unknown"),
            lambda v: v["features"][0].update(scope={**DEFAULT_SCOPE, "state": "hover"}),
        ):
            value = copy.deepcopy(dna())
            mutate(value)
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_dna(value)

    def test_bounded_load_rejects_duplicates_nonfinite_depth_and_size(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '[' * 100 + '0' + ']' * 100, ' ' * 1_000_001):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValidationError):
                load_json(raw)

    def test_profile_prose_retained_without_invented_semantics(self):
        value = build_dna(profile([evidence("reference")]))
        self.assertTrue(value["evidence"])
        self.assertTrue(value["principles"])
        self.assertFalse(value["features"])
        self.assertTrue(any("without semantic mapping" in gap for gap in value["gaps"]))

    def test_profile_measurement_projection_and_scope(self):
        raw = profile([evidence("reference")])
        raw["measurements"][0].update(name="typography.font_size", value=32, unit="px")
        scope = {**DEFAULT_SCOPE, "viewport": "1440x900"}
        value = build_dna(raw, contexts={"profile:reference": scope})
        self.assertEqual(value["features"][0]["value"], 32)
        self.assertEqual(value["features"][0]["scope"], scope)

    def test_target_and_mixed_source_claims_do_not_enter_reference_dna(self):
        raw = profile([evidence("reference")], [evidence("target")])
        raw["observations"][0]["source_ids"] = ["reference", "target"]
        value = build_dna(raw)
        self.assertTrue(all(s["role"] == "reference" for s in value["sources"]))
        self.assertFalse(value["principles"])
        self.assertTrue(all("profile:target" not in e["source_ids"] for e in value["evidence"]))

    def test_annotations_remain_inferred_and_scope_checked(self):
        raw = profile([evidence("reference")])
        annotation = {"schema_version": "0.1", "features": [{"name": "layout.hero_pattern", "value": "asymmetric", "unit": None,
            "status": "known", "scope": dict(DEFAULT_SCOPE), "evidence_ids": ["profile:observation-1"], "confidence": 0.8, "method": "user annotation"}], "constraints": []}
        value = build_dna(raw, annotations=annotation)
        self.assertEqual(value["features"][0]["origin"], "inferred")
        annotation["features"][0]["scope"]["viewport"] = "mobile"
        with self.assertRaisesRegex(ValidationError, "scope mismatch"):
            build_dna(raw, annotations=annotation)

    def test_collector_projects_exact_strings_as_observations_and_numbers_as_measurements(self):
        value = build_dna(inspection=collector_bundle())
        features = {f["name"]: f for f in value["features"]}
        self.assertEqual(features["typography.font_family"]["origin"], "observed")
        self.assertEqual(features["typography.font_size"]["value"], 32)
        self.assertEqual(features["typography.font_size"]["origin"], "measured")
        self.assertNotIn("spacing.gap", features)
        self.assertEqual(features["surface.shadow_usage"]["value"], 0)
        self.assertEqual(features["surface.border_usage"]["value"], 1)

    def test_collector_rejects_context_mismatch_and_reports_truncation(self):
        bundle = collector_bundle()
        bundle["captures"][1]["payload"]["coverage"]["truncated"] = True
        self.assertTrue(any("truncated" in g for g in build_dna(inspection=bundle)["gaps"]))
        bundle["captures"][0]["payload"]["session_id"] = "another-session"
        with self.assertRaisesRegex(ValidationError, "context mismatch"):
            build_dna(inspection=bundle)

    def test_inspection_enrichment_requires_matching_reference_artifact(self):
        raw = profile([evidence("reference")])
        with self.assertRaisesRegex(ValidationError, "reference artifact"):
            build_dna(raw, inspection=collector_bundle())
        raw["sources"][0]["locator"] = "synthetic:shot"
        value = build_dna(raw, inspection=collector_bundle())
        self.assertTrue(any(f["name"] == "typography.font_size" for f in value["features"]))

    def test_inference_confidence_cannot_exceed_support(self):
        value = dna()
        value["features"][1]["confidence"] = 0.99
        with self.assertRaisesRegex(ValidationError, "confidence exceeds"):
            validate_dna(value)

    def test_explicit_policy_can_carry_hard_constraint(self):
        raw = profile([evidence("reference")])
        annotations = {"schema_version": "0.1", "features": [], "constraints": [{"statement": "Keep the main action prominent.",
            "scope": dict(DEFAULT_SCOPE), "evidence_ids": ["profile:observation-1"], "confidence": 1,
            "strength": "MUST", "author": "fixture-user"}]}
        value = build_dna(raw, annotations=annotations)
        self.assertIn("MUST: Keep the main action prominent.", render_design(value))
        self.assertTrue(any("fixture-user" in gap for gap in value["gaps"]))


class RendererComparatorTests(unittest.TestCase):
    def test_guidance_is_qualified_in_both_modes(self):
        value = dna()
        compact = render_design(value)
        full = render_design(value, mode="full")
        self.assertIn("confidence=0.80", compact)
        self.assertEqual([l for l in compact.splitlines() if l.startswith("- SHOULD")], [l for l in full.splitlines() if l.startswith("- SHOULD")])
        self.assertNotIn("Evidence:", compact)
        self.assertIn("Evidence:", full)
        self.assertNotIn("MUST:", full)
        self.assertNotIn("NEVER:", full)

    def test_sparse_shadow_usage_does_not_become_prohibition(self):
        rendered = render_design(build_dna(inspection=collector_bundle()))
        self.assertIn("does not prohibit", rendered)
        self.assertNotIn("NEVER:", rendered)

    def test_no_motion_invention_and_low_confidence_omitted(self):
        value = dna()
        value["features"][1]["confidence"] = 0.2
        value["principles"][0]["confidence"] = 0.2
        rendered = render_design(value)
        self.assertNotIn("Preserve asymmetric", rendered)
        self.assertIn("low_confidence", rendered)
        self.assertIn("motion: no comparable", rendered)

    def test_generation_export_omits_raw_provenance_and_prose(self):
        value = dna()
        value["sources"][0]["locator"] = "https://private-reference.invalid/assets/logo.png"
        value["principles"][0]["statement"] = "SecretBrand guideline"
        exported = json.dumps(prepare_roundtrip(value, "Build a neutral dashboard."))
        self.assertNotIn("private-reference", exported)
        self.assertNotIn("SecretBrand", exported)
        self.assertIn("asymmetric", exported)

    def test_generation_export_aliases_untrusted_scope_labels(self):
        value = dna()
        scope = {"viewport": "SecretBrandDesktop", "state": "https://reference.invalid/state", "subject": "SecretBrandHero"}
        for array in ("features", "evidence", "principles"):
            for item in value[array]:
                item["scope"] = dict(scope)
        exported = json.dumps(prepare_roundtrip(value, "Build a neutral dashboard."))
        self.assertNotIn("SecretBrand", exported)
        self.assertNotIn("reference.invalid", exported)
        self.assertIn("role-1", exported)

    def test_comparator_identical_changed_and_explanations(self):
        left, right = dna(), dna()
        report = compare_design(left, right)
        self.assertEqual(report["dimensions"]["typography"]["score"], 1)
        right["features"][0]["value"] = 64
        right["features"][1]["value"] = "centered"
        report = compare_design(left, right)
        self.assertLess(report["dimensions"]["typography"]["score"], 1)
        self.assertEqual(report["dimensions"]["typography"]["features"][0]["difference"], 32)
        self.assertEqual(report["dimensions"]["composition"]["score"], 0)

    def test_missing_conflicting_low_confidence_and_not_applicable(self):
        left, right = dna(), dna()
        right["features"] = []
        result = compare_design(left, right)["dimensions"]["typography"]
        self.assertIsNone(result["score"])
        self.assertEqual(result["coverage"], 0)
        right = dna()
        right["features"].append({**right["features"][0], "id": "conflicting", "value": 99})
        self.assertIsNone(compare_design(left, right)["dimensions"]["typography"]["score"])
        right = dna()
        right["features"][1]["confidence"] = 0.1
        self.assertIsNone(compare_design(left, right)["dimensions"]["composition"]["score"])
        for value in (left, right):
            value["features"][0].update(status="not_applicable", value=None)
        self.assertEqual(compare_design(left, right)["dimensions"]["typography"]["eligible"], 0)


class AnalysisEvaluationTests(unittest.TestCase):
    def test_supported_contradicted_human_disagreement_and_calibration(self):
        result = evaluate_analysis(analysis_fixture())
        good, bad = result["models"]
        self.assertEqual(good["dimensions"]["typography"]["supported"], 1)
        self.assertEqual(bad["dimensions"]["typography"]["contradicted"], 1)
        self.assertAlmostEqual(good["dimensions"]["typography"]["calibration"]["grounding"]["brier"], 0.01)
        self.assertEqual(good["dimensions"]["composition"]["human_agreement"], 0.5)
        self.assertEqual(good["dimensions"]["composition"]["human_pairwise_agreement"], 0)
        self.assertAlmostEqual(good["dimensions"]["composition"]["calibration"]["interpretive"]["brier"], 0.26)

    def test_subject_mismatch_and_uncited_evidence_are_not_contradictions(self):
        for change in ("scope", "evidence"):
            fixture = analysis_fixture()
            claim = fixture["predictions"][0]["cases"][0]["claims"][0]
            if change == "scope":
                claim["scope"]["viewport"] = "390x844"
            else:
                claim["evidence_ids"] = []
            result = evaluate_analysis(fixture)["models"][0]["dimensions"]["typography"]
            self.assertEqual(result["insufficient_evidence"], 1)
            self.assertEqual(result["contradicted"], 0)
            self.assertIsNone(result["calibration"]["grounding"]["brier"])

    def test_empty_predictions_do_not_earn_perfect_score(self):
        fixture = analysis_fixture()
        fixture["predictions"][0]["cases"] = []
        result = evaluate_analysis(fixture)["models"][0]["dimensions"]["typography"]
        self.assertEqual(result["coverage"], 0)
        self.assertIsNone(result["supported_claim_rate"])
        human = evaluate_analysis(fixture)["models"][0]["dimensions"]["composition"]
        self.assertEqual(human["human_pairwise_agreement"], 0)
        self.assertEqual(human["human_pair_count"], 1)

    def test_invalid_predictions_are_counted_and_retained(self):
        fixture = analysis_fixture()
        fixture["predictions"][0]["cases"][0]["claims"][0]["confidence"] = "certain"
        result = evaluate_analysis(fixture)["models"][0]
        self.assertEqual(result["invalid_case_rate"], 1)
        self.assertEqual(result["dimensions"]["typography"]["invalid"], 1)
        self.assertTrue(result["invalid_cases"])


class RoundtripTests(unittest.TestCase):
    def fixture(self):
        return json.loads((Path(__file__).resolve().parents[1] / "examples/design/roundtrip-fixture.json").read_text())

    def test_baselines_variation_and_independent_review_are_separate(self):
        result = evaluate_roundtrip(self.fixture())
        self.assertEqual(len(result["runs"]), 6)
        self.assertEqual(len(result["groups"]), 1)
        group = result["groups"][0]
        self.assertTrue(group["complete_baselines"])
        self.assertTrue(group["independent_review_available"])
        typography = group["conditions"]["no_guidance"]["dimensions"]["typography"]
        self.assertIsNotNone(typography["stddev"])
        self.assertEqual(group["conditions"]["design_md"]["dimensions"]["typography"]["mean"], 1)
        self.assertEqual(result["runs"][0]["human_review"]["mean"], 0.5)

    def test_changed_configuration_is_not_pooled_with_baseline(self):
        fixture = self.fixture()
        fixture["runs"][0]["configuration"]["generation_budget"] = "changed budget"
        result = evaluate_roundtrip(fixture)
        self.assertEqual(len(result["groups"]), 2)
        self.assertTrue(any(not g["complete_baselines"] for g in result["groups"]))

    def test_invalid_manifest_replicate_and_input_digests_rejected(self):
        for change in ("isolation", "digest", "replicate"):
            fixture = self.fixture()
            if change == "isolation":
                fixture["runs"][0]["input_manifest"]["original_artifacts_available"] = True
            elif change == "digest":
                fixture["runs"][0]["input_manifest"]["brief_sha256"] = "0" * 64
            else:
                fixture["runs"][1]["replicate"] = 1
            with self.subTest(change=change), self.assertRaises(ValidationError):
                evaluate_roundtrip(fixture)

    def test_checked_in_analysis_and_dna_fixtures(self):
        root = Path(__file__).resolve().parents[1] / "examples/design"
        for name in ("reference-dna.json", "collector-dna.json"):
            load_dna((root / name).read_bytes())
        result = evaluate_analysis(load_json((root / "analysis-fixture.json").read_bytes()))
        self.assertEqual(result["models"][1]["dimensions"]["typography"]["contradicted"], 1)


class WorkflowCLITests(unittest.TestCase):
    def test_commands_and_invalid_input_diagnostics(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dna.json"
            path.write_text(normalize_dna(dna()))
            evaluation = Path(directory) / "evaluation.json"
            evaluation.write_text(json.dumps(analysis_fixture()))
            for args in (["design-validate", str(path)], ["design-render", str(path)], ["design-compare", str(path), str(path)], ["eval-analysis", str(evaluation)]):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(main(args), 0)
                self.assertTrue(stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")
            path.write_text('{}')
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(["design-render", str(path)]), 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("visparse:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

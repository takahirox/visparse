from __future__ import annotations

import copy
import json
import stat
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse.codex import (  # noqa: E402
    CodexAuthenticationError,
    CodexJSONError,
    CodexTimeoutError,
    CodexValidationError,
    ProcessResult,
)
from visparse.design import (  # noqa: E402
    AVOID_COPYING,
    DESIGN_CATEGORIES,
    DESIGN_SCHEMA_VERSION,
    OBSERVATION_DESIGN_CATEGORIES,
    CodexDesignAnalyzer,
    DesignAnalyzer,
    load_design_profile,
    normalize_design_profile,
    run_design_analyzer,
    summarize_design_profile,
    validate_design_profile,
)
from visparse.model import SourceEvidence, ValidationError  # noqa: E402


def evidence(source_id: str, payload: bytes = b"png") -> SourceEvidence:
    return SourceEvidence(source_id, "screenshot", f"memory://{source_id}", payload)


def profile(references: list[SourceEvidence], targets: list[SourceEvidence] | None = None) -> dict:
    targets = targets or []
    supplied = references + targets
    sources = [
        {
            "id": item.id,
            "kind": item.kind,
            "locator": item.locator,
            "role": "reference" if index < len(references) else "target",
        }
        for index, item in enumerate(supplied)
    ]
    observations = [
        {
            "id": f"observation-{index}",
            "source_ids": [item.id],
            "category": "layout",
            "statement": f"Visible layout evidence is present in source {index}.",
        }
        for index, item in enumerate(supplied, 1)
    ]
    observations.extend(
        {
            "id": f"category-{category}",
            "source_ids": [references[0].id],
            "category": category,
            "statement": f"A visible {category.replace('_', ' ')} characteristic is present.",
        }
        for category in sorted(OBSERVATION_DESIGN_CATEGORIES - {"layout"})
    )
    return {
        "schema_version": DESIGN_SCHEMA_VERSION,
        "sources": sources,
        "measurements": [{
            "id": "measurement-1", "source_id": references[0].id,
            "name": "viewport width", "value": 1440, "unit": "px",
            "method": "raster dimension inspection",
        }],
        "observations": observations,
        "interpretations": [{
            "id": "interpretation-1", "observation_ids": ["observation-1"],
            "category": "design_tone", "statement": "The composition may feel calm.",
            "confidence_id": "confidence-1",
        }, {
            "id": "interpretation-strength", "observation_ids": ["observation-1"],
            "category": "strength", "statement": "The alignment may support scanning.",
            "confidence_id": "confidence-1",
        }, {
            "id": "interpretation-weakness", "observation_ids": ["observation-1"],
            "category": "weakness", "statement": "The same alignment may become repetitive.",
            "confidence_id": "confidence-1",
        }],
        "confidence": [{
            "id": "confidence-1", "level": 0.7,
            "uncertainty": "Tone is subjective.",
            "basis": "The interpretation is linked to visible spacing.",
        }],
        "principles": [{
            "id": "principle-1", "observation_ids": ["observation-1"],
            "interpretation_ids": ["interpretation-1"],
            "statement": "Use one dominant alignment axis to reduce competition.",
        }],
        "recommendations": [{
            "id": "recommendation-1", "principle_ids": ["principle-1"],
            "target_source_ids": [item.id for item in targets],
            "action": "Align the target site's primary content to its own grid.",
            "rationale": "This adapts the hierarchy principle without reproducing the source.",
            "transfer_mode": "principle",
            "avoid_copying": sorted(AVOID_COPYING),
        }],
        "provenance": {"created_by": "test", "inputs": [item.id for item in supplied]},
    }


class StaticAnalyzer(DesignAnalyzer):
    def __init__(self, result: dict) -> None:
        self.result = result

    def analyze(self, references, targets=()):
        del references, targets
        return self.result


class FakeRunner:
    def __init__(self, result: ProcessResult | None = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.argv: list[str] = []
        self.timeout = 0.0
        self.payloads: list[bytes] = []
        self.modes: list[int] = []
        self.paths: list[Path] = []

    def run(self, argv, *, timeout):
        self.argv = list(argv)
        self.timeout = timeout
        start = self.argv.index("--image") + 1
        end = self.argv.index("--")
        self.paths = [Path(value) for value in self.argv[start:end]]
        self.payloads = [path.read_bytes() for path in self.paths]
        self.modes = [stat.S_IMODE(path.stat().st_mode) for path in self.paths]
        if self.error:
            raise self.error
        if self.result is None:
            raise AssertionError("fake runner needs a result or error")
        return self.result


class DesignProfileTests(unittest.TestCase):
    def test_valid_multiple_sources_cover_design_vocabulary_and_summary(self) -> None:
        value = profile([evidence("desktop"), evidence("mobile")], [evidence("target")])
        self.assertIs(validate_design_profile(value), value)
        summary = summarize_design_profile(value)
        self.assertEqual(summary["counts"]["sources"], 3)
        self.assertEqual(set(summary["categories"]), DESIGN_CATEGORIES)
        self.assertEqual(summary["source_roles"], ["reference", "target"])
        self.assertEqual(normalize_design_profile(value), normalize_design_profile(json.loads(normalize_design_profile(value))))

    def test_strict_shape_ids_and_references_are_validated(self) -> None:
        base = profile([evidence("source")])
        cases = []
        extra = copy.deepcopy(base)
        extra["observations"][0]["unknown"] = True
        cases.append(extra)
        duplicate = copy.deepcopy(base)
        duplicate["principles"][0]["id"] = duplicate["observations"][0]["id"]
        cases.append(duplicate)
        broken = copy.deepcopy(base)
        broken["interpretations"][0]["observation_ids"] = ["missing"]
        cases.append(broken)
        invalid_confidence = copy.deepcopy(base)
        invalid_confidence["confidence"][0]["level"] = float("nan")
        cases.append(invalid_confidence)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_design_profile(value)

    def test_recommendations_require_structural_principle_transfer_safety(self) -> None:
        base = profile([evidence("source")])
        bad_mode = copy.deepcopy(base)
        bad_mode["recommendations"][0]["transfer_mode"] = "clone"
        with self.assertRaisesRegex(ValidationError, "expected principle"):
            validate_design_profile(bad_mode)
        missing_guard = copy.deepcopy(base)
        missing_guard["recommendations"][0]["avoid_copying"].remove("assets")
        with self.assertRaisesRegex(ValidationError, "must contain"):
            validate_design_profile(missing_guard)
        unsafe = copy.deepcopy(base)
        unsafe["recommendations"][0]["action"] = "Copy the reference logo exactly."
        with self.assertRaisesRegex(ValidationError, "copying or cloning"):
            validate_design_profile(unsafe)

    def test_subjective_design_categories_are_interpretations_only(self) -> None:
        for category in ("design_tone", "strength", "weakness"):
            invalid = profile([evidence("source")])
            invalid["observations"][0]["category"] = category
            with self.subTest(category=category):
                with self.assertRaisesRegex(ValidationError, "interpretations, not direct observations"):
                    validate_design_profile(invalid)

    def test_measurements_are_finite_mechanical_numbers(self) -> None:
        base = profile([evidence("source")])
        for value in ("spacious", True, float("inf")):
            invalid = copy.deepcopy(base)
            invalid["measurements"][0]["value"] = value
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_design_profile(invalid)

    def test_loader_rejects_duplicate_keys(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            load_design_profile('{"schema_version":"0.1","schema_version":"0.1"}')

    def test_run_boundary_rejects_changed_identity_or_role(self) -> None:
        source = evidence("source")
        changed = profile([source])
        changed["sources"][0]["locator"] = "memory://different"
        with self.assertRaisesRegex(ValidationError, "changed source identity"):
            run_design_analyzer(StaticAnalyzer(changed), [source])

    def test_codex_adapter_supports_multiple_images_and_cleans_up(self) -> None:
        references = [evidence("desktop", b"desktop"), evidence("mobile", b"mobile")]
        targets = [evidence("target", b"target")]
        expected = profile(references, targets)
        expected["measurements"] = []
        runner = FakeRunner(ProcessResult(0, json.dumps(expected), "progress"))
        result = CodexDesignAnalyzer(runner=runner, timeout_seconds=9).analyze(references, targets)
        self.assertEqual(len(result["sources"]), 3)
        self.assertEqual(runner.payloads, [b"desktop", b"mobile", b"target"])
        self.assertEqual(runner.modes, [0o600, 0o600, 0o600])
        self.assertEqual(runner.timeout, 9)
        self.assertEqual(runner.argv[runner.argv.index("--") + 1], runner.argv[-1])
        self.assertIn("Never request pixel-perfect cloning", runner.argv[-1])
        self.assertIn("never use a reference source ID as a target", runner.argv[-1])
        self.assertIn('inputs exactly equal to ["desktop", "mobile", "target"]', runner.argv[-1])
        self.assertIn("measurements must be an empty array", runner.argv[-1])
        self.assertTrue(all(not path.exists() for path in runner.paths))

    def test_codex_adapter_timeout_is_stable_and_cleans_up(self) -> None:
        runner = FakeRunner(error=subprocess.TimeoutExpired("codex", 2))
        with self.assertRaises(CodexTimeoutError):
            CodexDesignAnalyzer(runner=runner, timeout_seconds=2).analyze([evidence("source")])
        self.assertTrue(all(not path.exists() for path in runner.paths))

    def test_codex_adapter_rejects_provider_and_validation_failures(self) -> None:
        source = evidence("source")
        untrusted_measurement = profile([source])
        cases = (
            (ProcessResult(1, "", "Not logged in; run codex login"), CodexAuthenticationError),
            (ProcessResult(0, "not json", ""), CodexJSONError),
            (ProcessResult(0, "{}", ""), CodexValidationError),
            (ProcessResult(0, json.dumps(untrusted_measurement), ""), CodexValidationError),
        )
        for result, expected in cases:
            with self.subTest(expected=expected.__name__):
                runner = FakeRunner(result)
                with self.assertRaises(expected):
                    CodexDesignAnalyzer(runner=runner).analyze([source])
                self.assertTrue(all(not path.exists() for path in runner.paths))


    def test_preservation_analysis_inventory_and_isolation(self):
        source = evidence("source")
        expected = profile([source]); expected["measurements"] = []
        runner = FakeRunner(ProcessResult(0, json.dumps(expected), ""))
        CodexDesignAnalyzer(runner=runner, intent="preserve").analyze([source])
        self.assertEqual(runner.timeout, 300)
        prompt = runner.argv[-1]
        for phrase in ("reconstruction inventory", "identity/name/level labels", "headline lines",
                       "Missing dimensions stay unknown", "do not identify"):
            self.assertIn(phrase.lower(), prompt.lower())
        for flag in ("apps", "plugins", "memories", "project_doc_max_bytes=0", 'web_search="disabled"'):
            self.assertIn(flag, runner.argv)
        self.assertNotIn("reconstruction inventory", CodexDesignAnalyzer._prompt([source], []))
        self.assertTrue(all(not path.exists() for path in runner.paths))

    def test_invalid_analysis_configuration_never_calls_provider(self):
        from unittest.mock import Mock
        for options in ({"intent": []}, {"intent": "guess"}, {"timeout_seconds": True},
                        {"timeout_seconds": 0}, {"timeout_seconds": 901}, {"timeout_seconds": float("nan")}):
            runner = Mock()
            with self.subTest(options=options), self.assertRaises(ValidationError):
                CodexDesignAnalyzer(runner=runner, **options).analyze([evidence("source")])
            runner.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

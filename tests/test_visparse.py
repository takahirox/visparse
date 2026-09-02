from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse import (  # noqa: E402
    Analyzer,
    MAX_INPUT_BYTES,
    SourceEvidence,
    ValidationError,
    evaluate_fixture,
    load_record,
    normalize_record,
    run_analyzer,
    summarize_record,
    validate_record,
)
from visparse.cli import main  # noqa: E402


def record() -> dict:
    return {
        "schema_version": "0.1",
        "sources": [{"id": "src-1", "kind": "image", "locator": "memory://example"}],
        "measurements": [{
            "id": "m-1", "source_id": "src-1", "name": "width", "value": 640,
            "unit": "px", "method": "decoded pixel dimensions",
        }],
        "observations": [{
            "id": "o-1", "source_ids": ["src-1"], "statement": "A blue rectangle is present.",
        }],
        "interpretations": [{
            "id": "i-1", "observation_ids": ["o-1"],
            "statement": "The rectangle may be a button.", "confidence_id": "c-1",
        }],
        "confidence": [{
            "id": "c-1", "level": 0.6, "uncertainty": "No interaction was tested.",
            "basis": "Shape resembles common controls.",
        }],
        "interactions": [{
            "id": "x-1", "kind": "ui", "source_id": "src-1",
            "details": {"action": "inspection", "result": "not activated"},
        }],
        "provenance": {"created_by": "unit-test", "inputs": ["src-1"]},
    }


class ModelTests(unittest.TestCase):
    def test_valid_record_and_structural_summary(self) -> None:
        value = validate_record(record())
        summary = summarize_record(value)
        self.assertEqual(summary["counts"]["measurements"], 1)
        self.assertEqual(summary["source_kinds"], ["image"])

    def test_canonical_json_is_stable(self) -> None:
        first = normalize_record(record())
        second = normalize_record(load_record(first))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn(": ", first)

    def test_broken_cross_reference_is_rejected(self) -> None:
        value = record()
        value["interpretations"][0]["observation_ids"] = ["missing"]
        with self.assertRaisesRegex(ValidationError, "unknown reference"):
            validate_record(value)

    def test_duplicate_ids_and_keys_are_rejected(self) -> None:
        value = record()
        value["observations"][0]["id"] = "m-1"
        with self.assertRaisesRegex(ValidationError, "duplicate id"):
            validate_record(value)
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            load_record('{"schema_version":"0.1","schema_version":"0.1"}')

    def test_confidence_and_temporal_timestamp_are_validated(self) -> None:
        value = record()
        value["confidence"][0]["level"] = True
        with self.assertRaises(ValidationError):
            validate_record(value)
        value = record()
        value["interactions"][0] = {"id": "x-1", "kind": "temporal", "details": {}}
        with self.assertRaisesRegex(ValidationError, "timestamp"):
            validate_record(value)

    def test_measurement_cannot_hold_structured_inference(self) -> None:
        value = record()
        value["measurements"][0]["value"] = {"meaning": "button"}
        with self.assertRaisesRegex(ValidationError, "scalar"):
            validate_record(value)

    def test_input_limit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "exceeds"):
            load_record(b" " * (MAX_INPUT_BYTES + 1))


class EchoAnalyzer(Analyzer):
    def analyze(self, evidence: SourceEvidence) -> dict:
        value = record()
        value["sources"][0] = {"id": evidence.id, "kind": evidence.kind, "locator": evidence.locator}
        value["measurements"][0]["source_id"] = evidence.id
        value["observations"][0]["source_ids"] = [evidence.id]
        value["interactions"][0]["source_id"] = evidence.id
        value["provenance"]["inputs"] = [evidence.id]
        return value


class BoundaryAndEvaluationTests(unittest.TestCase):
    def test_provider_neutral_analyzer_boundary(self) -> None:
        evidence = SourceEvidence("src-x", "web", "https://example.invalid", b"content")
        result = run_analyzer(EchoAnalyzer(), evidence)
        self.assertEqual(result["sources"][0]["id"], "src-x")

    def test_evaluation_reports_expected_validity(self) -> None:
        fixture = {
            "cases": [
                {"name": "valid", "record": record(), "expected_valid": True},
                {"name": "invalid", "record": {}, "expected_valid": False},
            ]
        }
        result = evaluate_fixture(fixture)
        self.assertEqual((result.total, result.passed, result.failures), (2, 2, ()))

    def test_evaluation_detects_summary_mismatch(self) -> None:
        result = evaluate_fixture({"cases": [{
            "name": "mismatch", "record": record(), "expected_valid": True,
            "expected_summary": {},
        }]})
        self.assertEqual(result.passed, 0)
        self.assertIn("summary mismatch", result.failures[0])

    def test_cli_normalize_and_invalid_input(self) -> None:
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile("w", encoding="utf-8") as stream:
            json.dump(record(), stream)
            stream.flush()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["normalize", stream.name]), 0)
            self.assertEqual(output.getvalue(), normalize_record(record()))
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["validate", "/definitely/missing"]), 2)
        self.assertIn("visparse:", error.getvalue())


if __name__ == "__main__":
    unittest.main()

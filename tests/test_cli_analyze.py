from __future__ import annotations

import hashlib
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse.cli import main  # noqa: E402
from visparse.codex import (  # noqa: E402
    CodexAuthenticationError,
    CodexJSONError,
    CodexJSONObjectError,
    CodexProcessError,
    CodexTimeoutError,
    CodexUnavailableError,
    CodexValidationError,
)
from visparse.model import MAX_INPUT_BYTES, normalize_record  # noqa: E402


def record(source_id: str, kind: str, locator: str) -> dict:
    return {
        "schema_version": "0.1",
        "sources": [{"id": source_id, "kind": kind, "locator": locator}],
        "measurements": [{
            "id": "m-1", "source_id": source_id, "name": "width", "value": 1,
            "unit": "px", "method": "decoded pixel width",
        }],
        "observations": [{
            "id": "o-1", "source_ids": [source_id], "statement": "One pixel is visible.",
        }],
        "interpretations": [{
            "id": "i-1", "observation_ids": ["o-1"],
            "statement": "The image may be a capture.", "confidence_id": "c-1",
        }],
        "confidence": [{
            "id": "c-1", "level": 0.5, "uncertainty": "The context is unknown.",
            "basis": "Only the image was inspected.",
        }],
        "interactions": [],
        "provenance": {"created_by": "test", "inputs": [source_id]},
    }


class CliAnalyzeTests(unittest.TestCase):
    def test_analyze_success_captures_source_evidence(self) -> None:
        payload = b"\x89PNG\r\n\x1a\nvisparse"
        captured = []
        analyzer = Mock()
        analyzer.analyze.side_effect = lambda evidence: (
            captured.append(evidence),
            record(evidence.id, evidence.kind, evidence.locator),
        )[1]

        with TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(payload)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.cli.CodexAnalyzer", return_value=analyzer) as factory, \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["analyze", str(path)])

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(captured), 1)
        evidence = captured[0]
        self.assertEqual((evidence.id, evidence.kind, evidence.payload),
                         ("source-1", "screenshot", payload))
        self.assertEqual(
            evidence.locator,
            f"file:sha256:{hashlib.sha256(payload).hexdigest()}",
        )
        self.assertEqual(
            stdout.getvalue(),
            normalize_record(record(evidence.id, evidence.kind, evidence.locator)),
        )
        factory.assert_called_once_with()

    def test_analyze_errors_are_reported_exactly(self) -> None:
        cases = (
            ("unavailable", CodexUnavailableError, "unavailable"),
            ("authentication", CodexAuthenticationError, "authentication"),
            ("timeout", CodexTimeoutError, "timeout"),
            ("process", CodexProcessError, "process"),
            ("JSON", CodexJSONError, "json"),
            ("JSON object", CodexJSONObjectError, "json object"),
            ("validation", CodexValidationError, "validation"),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "capture.png"
            path.write_bytes(b"png")
            for name, error_type, message in cases:
                with self.subTest(name=name):
                    analyzer = Mock()
                    analyzer.analyze.side_effect = error_type(message)
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with patch("visparse.cli.CodexAnalyzer", return_value=analyzer) as factory, \
                            redirect_stdout(stdout), redirect_stderr(stderr):
                        status = main(["analyze", str(path)])
                    self.assertEqual(status, 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertEqual(stderr.getvalue(), f"visparse: {message}\n")
                    factory.assert_called_once_with()

    def test_invalid_inputs_skip_analyzer(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            oversized = root / "oversized.png"
            oversized.write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
            cases = (
                ("missing", root / "missing.png"),
                ("directory", root),
                ("oversized", oversized),
            )
            for name, path in cases:
                with self.subTest(name=name):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with patch("visparse.cli.CodexAnalyzer") as analyzer, \
                            redirect_stdout(stdout), redirect_stderr(stderr):
                        status = main(["analyze", str(path)])
                    self.assertEqual(status, 2)
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertTrue(stderr.getvalue().startswith("visparse: "))
                    analyzer.assert_not_called()

    def test_validate_regression(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(
                normalize_record(record("source-1", "image", "memory://example")),
                encoding="utf-8",
            )
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.cli.CodexAnalyzer") as analyzer, \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["validate", str(path)])

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), '{"schema_version":"0.1","valid":true}\n')
        self.assertEqual(stderr.getvalue(), "")
        analyzer.assert_not_called()


if __name__ == "__main__":
    unittest.main()

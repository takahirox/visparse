from __future__ import annotations

import json
import stat
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse.codex import (  # noqa: E402
    CodexAnalyzer,
    CodexAuthenticationError,
    CodexJSONError,
    CodexJSONObjectError,
    CodexProcessError,
    CodexTimeoutError,
    CodexUnavailableError,
    CodexValidationError,
    ProcessResult,
)
from visparse.model import SourceEvidence  # noqa: E402


class FakeRunner:
    def __init__(self, result: ProcessResult | None = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[list[str], float, Path]] = []
        self.image_payload: bytes | None = None
        self.image_mode: int | None = None

    def run(self, argv: list[str], *, timeout: float) -> ProcessResult:
        command = list(argv)
        path = Path(command[command.index("--image") + 1])
        self.image_payload = path.read_bytes()
        self.image_mode = stat.S_IMODE(path.stat().st_mode)
        self.calls.append((command, timeout, path))
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("fake runner needs a result or error")
        return self.result


def evidence() -> SourceEvidence:
    return SourceEvidence("source-1", "screenshot", "capture://frame-7", b"\x89PNG\r\n")


def record(source: SourceEvidence) -> dict:
    return {
        "schema_version": "0.1",
        "sources": [{"id": source.id, "kind": source.kind, "locator": source.locator}],
        "measurements": [
            {"id": "m-1", "source_id": source.id, "name": "width", "value": 1, "unit": "px", "method": "decoded pixel width"},
        ],
        "observations": [
            {"id": "o-1", "source_ids": [source.id], "statement": "One image pixel is visible."},
        ],
        "interpretations": [
            {"id": "i-1", "observation_ids": ["o-1"], "statement": "The image may be a capture.", "confidence_id": "c-1"},
        ],
        "confidence": [
            {"id": "c-1", "level": 0.5, "uncertainty": "The context is unknown.", "basis": "Only the image was inspected."},
        ],
        "interactions": [],
        "provenance": {"created_by": "codex", "inputs": [source.id]},
    }


class CodexAnalyzerTests(unittest.TestCase):
    def _successful_runner(self, source: SourceEvidence) -> FakeRunner:
        return FakeRunner(ProcessResult(0, json.dumps(record(source)), "progress"))

    def test_success_uses_expected_command_prompt_and_private_temporary_image(self) -> None:
        source = evidence()
        runner = self._successful_runner(source)
        result = CodexAnalyzer(runner=runner, timeout_seconds=9).analyze(source)

        self.assertEqual(result["sources"][0]["locator"], source.locator)
        self.assertEqual(len(runner.calls), 1)
        argv, timeout, path = runner.calls[0]
        self.assertEqual(argv[:9], ["codex", "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "--image"])
        self.assertEqual(argv[9], str(path))
        self.assertEqual(argv[10], "--")
        prompt = argv[11]
        self.assertIn("exactly one JSON object", prompt)
        self.assertIn('id="source-1"', prompt)
        self.assertIn('kind="screenshot"', prompt)
        self.assertIn('locator="capture://frame-7"', prompt)
        self.assertIn("mechanical", prompt)
        self.assertIn("directly visible", prompt)
        self.assertIn("explicitly inferred", prompt)
        self.assertIn("uncertainty and basis", prompt)
        self.assertEqual(runner.image_payload, source.payload)
        self.assertEqual((timeout, runner.image_mode), (9, 0o600))
        self.assertFalse(path.exists())

    def test_executable_and_timeout_errors_are_distinct_and_clean_up(self) -> None:
        source = evidence()
        cases = [
            ("unavailable", FileNotFoundError(), CodexUnavailableError),
            ("timeout", subprocess.TimeoutExpired("codex", 2.0), CodexTimeoutError),
        ]
        for name, failure, expected in cases:
            with self.subTest(name=name):
                runner = FakeRunner(error=failure)
                with self.assertRaises(expected):
                    CodexAnalyzer(runner=runner).analyze(source)
                _, _, path = runner.calls[0]
                self.assertFalse(path.exists())

    def test_authentication_and_nonzero_process_errors_are_distinct(self) -> None:
        source = evidence()
        cases = [
            (ProcessResult(1, "", "Not logged in; run codex login"), CodexAuthenticationError),
            (ProcessResult(7, "", "model failed"), CodexProcessError),
        ]
        for result, expected in cases:
            with self.subTest(expected=expected.__name__):
                runner = FakeRunner(result)
                with self.assertRaises(expected):
                    CodexAnalyzer(runner=runner).analyze(source)
                self.assertFalse(runner.calls[0][2].exists())

    def test_non_json_and_non_object_outputs_are_distinct(self) -> None:
        source = evidence()
        cases = [
            ("```json\n{}\n```", CodexJSONError),
            ("[]", CodexJSONObjectError),
        ]
        for output, expected in cases:
            with self.subTest(expected=expected.__name__):
                runner = FakeRunner(ProcessResult(0, output, ""))
                with self.assertRaises(expected):
                    CodexAnalyzer(runner=runner).analyze(source)
                self.assertFalse(runner.calls[0][2].exists())

    def test_schema_invalid_output_is_not_repaired(self) -> None:
        source = evidence()
        invalid = record(source)
        invalid["schema_version"] = "0.2"
        runner = FakeRunner(ProcessResult(0, json.dumps(invalid), ""))
        with self.assertRaises(CodexValidationError):
            CodexAnalyzer(runner=runner).analyze(source)
        self.assertEqual(invalid["schema_version"], "0.2")
        self.assertFalse(runner.calls[0][2].exists())

    def test_changed_source_identity_is_rejected_without_repair(self) -> None:
        source = evidence()
        changed = record(source)
        changed["sources"][0]["locator"] = "capture://different"
        runner = FakeRunner(ProcessResult(0, json.dumps(changed), ""))
        with self.assertRaisesRegex(CodexValidationError, "source identity"):
            CodexAnalyzer(runner=runner).analyze(source)
        self.assertEqual(changed["sources"][0]["locator"], "capture://different")
        self.assertFalse(runner.calls[0][2].exists())


if __name__ == "__main__":
    unittest.main()

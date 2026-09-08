"""Exercise shared configuration through all four real CLI analysis paths offline."""
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from visparse.agent_config import ANALYSIS_COMMANDS, AnalyzerConfig, CommandAgentRunner
from visparse.cli import main
from visparse.codex import ProcessResult
from visparse.contracts import canonical
from visparse.model import SourceEvidence, ValidationError
from test_codex_analyzer import record
from test_design import profile
from test_semantic import sample
from interaction_fixtures import sequence, prediction


class SharedAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.image, self.target, self.dna, self.sequence, self.config = [
            root / name for name in ("image.png", "target.png", "dna.json", "sequence.json", "config.json")]
        self.image.write_bytes(b"image evidence")
        self.target.write_bytes(b"target evidence")
        self.dna.write_text(canonical(sample()["dna"]))
        self.sequence.write_text(canonical(sequence()))

    def case(self, command):
        if command == "analyze":
            return [str(self.image)], record(SourceEvidence.from_file("source-1", str(self.image))), [b"image evidence"]
        if command == "analyze-design":
            value = profile([SourceEvidence.from_file("reference-1", str(self.image))],
                            [SourceEvidence.from_file("target-1", str(self.target))])
            value["measurements"] = []
            return [str(self.image), "--target", str(self.target)], value, [b"image evidence", b"target evidence"]
        if command == "design-extract":
            return [str(self.dna)], sample()["prediction"], []
        return [str(self.sequence)], prediction(), []

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_precedence_and_legacy_config(self):
        doc = {"analyzer": {"model": "common", "timeout_seconds": 500},
               "ux_analyzer": {"model": "legacy"},
               "commands": {"ux-analyze": {"model": "ux"}, "analyze": {"timeout_seconds": 150}}}
        self.assertEqual(AnalyzerConfig.resolve(doc, command="analyze").model, "common")
        self.assertEqual(AnalyzerConfig.resolve(doc, command="analyze").timeout_seconds, 150)
        self.assertEqual(AnalyzerConfig.resolve(doc).model, "ux")
        self.assertEqual(AnalyzerConfig.resolve(doc, model="cli").model, "cli")
        del doc["commands"]["ux-analyze"]
        self.assertEqual(AnalyzerConfig.resolve(doc).model, "legacy")
        for command in ANALYSIS_COMMANDS:
            self.assertEqual(AnalyzerConfig.resolve(command=command).timeout_seconds, 120 if command == "analyze" else 300)
        with self.assertRaises(ValidationError):
            AnalyzerConfig.resolve({"ux_analyzer": {"model": "ux"}}, command="analyze")
        for doc in [{"commands": {"typo": {}}}, {"analyzer": {"agent": "unknown"}},
                    {"analyzer": {"model": "bad model"}}, {"commands": {"analyze": {"timeout_seconds": 0}}}]:
            with self.subTest(doc=doc), self.assertRaises(ValidationError):
                AnalyzerConfig.resolve(doc, model="override")

    def test_every_cli_forwards_codex_model_executable_and_timeout(self):
        self.config.write_text(canonical({"analyzer": {"model": "common", "executable": "/path with spaces/codex"},
                                          "commands": {c: {"model": "per-command", "timeout_seconds": 42} for c in ANALYSIS_COMMANDS}}))
        for command in ANALYSIS_COMMANDS:
            args, expected, _ = self.case(command)
            runner = Mock(return_value=ProcessResult(0, canonical(expected), ""))
            with self.subTest(command=command), patch("visparse.codex.SubprocessRunner.run", runner):
                status, output, error = self.invoke([command, *args, "--config", str(self.config), "--model", "explicit-model"])
                self.assertEqual(status, 0, error)
                self.assertIsInstance(json.loads(output), dict)
                runner.assert_called_once()
                argv = runner.call_args.args[0]
                self.assertEqual(argv[0], "/path with spaces/codex")
                self.assertEqual(argv[argv.index("--model") + 1], "explicit-model")
                self.assertLess(argv.index("--model"), argv.index("--"))
                self.assertEqual(runner.call_args.kwargs["timeout"], 42)

    def test_every_command_wrapper_receives_prompt_model_and_ordered_images(self):
        for command in ANALYSIS_COMMANDS:
            args, expected, image_bytes = self.case(command)
            captured_paths = []

            def run(argv, *, input_text, timeout):
                self.assertEqual(argv, ["/path with spaces/wrapper"])
                self.assertEqual(timeout, 33)
                request = json.loads(input_text)
                self.assertEqual(request["schema_version"], "analysis-agent-request/0.1")
                self.assertEqual(request["command"], command)
                self.assertEqual(request["model"], "wrapper-model")
                self.assertTrue(request["prompt"])
                captured_paths.extend(Path(p) for p in request["image_paths"])
                self.assertEqual([p.read_bytes() for p in captured_paths], image_bytes)
                return ProcessResult(0, canonical(expected), "")

            with self.subTest(command=command), patch("visparse.agent_config.CommandSubprocessRunner.run", side_effect=run) as runner, \
                    patch("visparse.codex.SubprocessRunner.run") as codex:
                status, output, error = self.invoke([command, *args, "--agent", "command", "--executable",
                                                    "/path with spaces/wrapper", "--model", "wrapper-model", "--timeout-seconds", "33"])
                self.assertEqual(status, 0, error)
                self.assertIsInstance(json.loads(output), dict)
                runner.assert_called_once()
                codex.assert_not_called()
                self.assertTrue(all(not p.exists() for p in captured_paths))

    def test_invalid_config_never_calls_a_provider_in_any_mode(self):
        self.config.write_text('{"analyzer":{"model":"first","model":"second"}}')
        for command in ANALYSIS_COMMANDS:
            args, _, _ = self.case(command)
            with self.subTest(command=command), patch("visparse.codex.SubprocessRunner.run") as runner:
                self.assertEqual(self.invoke([command, *args, "--config", str(self.config)])[0], 2)
                self.assertEqual(self.invoke([command, *args, "--model=--help"])[0], 2)
                runner.assert_not_called()

    def test_external_failures_never_retry_or_fall_back_and_cleanup_images(self):
        for command in ANALYSIS_COMMANDS:
            args, _, _ = self.case(command)
            for response in [ProcessResult(1, "", "usage limit"), ProcessResult(0, "not json", ""),
                             subprocess.TimeoutExpired("wrapper", 1)]:
                paths = []
                def fail(argv, *, input_text, timeout):
                    paths.extend(Path(p) for p in json.loads(input_text)["image_paths"])
                    if isinstance(response, Exception): raise response
                    return response
                with self.subTest(command=command, response=response), \
                        patch("visparse.agent_config.CommandSubprocessRunner.run", side_effect=fail) as runner, \
                        patch("visparse.codex.SubprocessRunner.run") as codex:
                    status, output, error = self.invoke([command, *args, "--agent", "command", "--executable", "wrapper"])
                    self.assertEqual(status, 2)
                    self.assertEqual(output, "")
                    self.assertTrue(error.startswith("visparse: "))
                    runner.assert_called_once(); codex.assert_not_called()
                    self.assertTrue(all(not p.exists() for p in paths))

    def test_stored_predictions_bypass_all_live_options(self):
        for command in ("design-extract", "ux-analyze"):
            args, value, _ = self.case(command)
            stored = Path(self.temp.name) / "prediction.json"
            stored.write_text(canonical(value))
            with self.subTest(command=command), patch("visparse.cli._agent_config") as factory:
                self.assertEqual(self.invoke([command, *args, "--predictions", str(stored), "--agent", "command",
                                              "--config", "missing.json", "--model=--help", "--timeout-seconds", "nan"])[0], 0)
                factory.assert_not_called()

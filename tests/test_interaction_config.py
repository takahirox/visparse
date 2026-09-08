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
from visparse.cli import main
from visparse.codex import ProcessResult
from visparse.contracts import canonical
from visparse.interaction_analysis import CodexInteractionAnalyzer
from visparse.interaction_config import (
    CommandInteractionAnalyzer, CommandSubprocessRunner, InteractionAgentError,
    InteractionAnalyzerConfig,
)
from visparse.model import ValidationError
from interaction_fixtures import sequence, prediction


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_explicit_cli_precedence(self):
        default = InteractionAnalyzerConfig.resolve().create_analyzer()
        self.assertIsInstance(default, CodexInteractionAnalyzer)
        self.assertEqual((default.executable, default.model, default.timeout_seconds), ("codex", None, 300))
        config = InteractionAnalyzerConfig.resolve(
            {"ux_analyzer": {"agent": "codex", "model": "file-model", "timeout_seconds": 450}},
            model="cli-model", timeout_seconds=120)
        self.assertEqual((config.model, config.timeout_seconds), ("cli-model", 120))
        self.assertIsInstance(InteractionAnalyzerConfig(agent="command", executable="wrapper").create_analyzer(),
                              CommandInteractionAnalyzer)
        self.assertEqual(InteractionAnalyzerConfig.resolve({"ux_analyzer": {"agent": "command"}},
                                                         executable="wrapper").executable, "wrapper")

    def test_invalid_configuration_rejected(self):
        cases = [{"unknown": {}}, {"ux_analyzer": {"modle": "typo"}},
                 {"ux_analyzer": {"agent": "unknown"}}, {"ux_analyzer": {"agent": "command"}},
                 *({"ux_analyzer": {"model": value}} for value in ["", "--help", "bad\nmodel", 12]),
                 *({"ux_analyzer": {"timeout_seconds": value}} for value in [0, 901, True, float("nan")]),
                 *({"ux_analyzer": {"executable": value}} for value in ["", "--help", "bad\0path"])]
        for document in cases:
            with self.subTest(document=document), self.assertRaises(ValidationError):
                InteractionAnalyzerConfig.resolve(document)

    def test_codex_model_argument_and_preflight(self):
        runner = Mock()
        runner.run.return_value = ProcessResult(0, canonical(prediction()), "")
        CodexInteractionAnalyzer(runner=runner, executable="/tmp/path with spaces/codex",
                                model="chosen-model", timeout_seconds=42).analyze(sequence())
        argv = runner.run.call_args.args[0]
        self.assertEqual(argv[0], "/tmp/path with spaces/codex")
        self.assertEqual(argv[argv.index("--model") + 1], "chosen-model")
        self.assertLess(argv.index("--model"), argv.index("--"))
        self.assertIn("--ignore-user-config", argv)
        self.assertEqual(runner.run.call_args.kwargs, {"timeout": 42})
        runner.reset_mock()
        CodexInteractionAnalyzer(runner=runner).analyze(sequence())
        self.assertNotIn("--model", runner.run.call_args.args[0])
        runner.reset_mock()
        with self.assertRaises(ValidationError):
            CodexInteractionAnalyzer(runner=runner, model="--help").analyze(sequence())
        runner.run.assert_not_called()

    def test_command_protocol_and_single_call_failures(self):
        runner = Mock()
        runner.run.return_value = ProcessResult(0, canonical(prediction()), "")
        agent = CommandInteractionAnalyzer("/tmp/agent wrapper", model="other-model", runner=runner)
        self.assertEqual(agent.analyze(sequence()), prediction())
        runner.run.assert_called_once()
        self.assertEqual(runner.run.call_args.args[0], ["/tmp/agent wrapper"])
        request = json.loads(runner.run.call_args.kwargs["input_text"])
        self.assertEqual(request["schema_version"], "interaction-analysis-request/0.1")
        self.assertEqual(request["model"], "other-model")
        self.assertIn(canonical(sequence()), request["prompt"])
        self.assertIn("Never invent", request["prompt"])
        for error in [FileNotFoundError(), OSError(), subprocess.TimeoutExpired("wrapper", 1)]:
            runner.reset_mock(); runner.run.side_effect = error
            with self.assertRaises(InteractionAgentError): agent.analyze(sequence())
            runner.run.assert_called_once()
        runner.run.side_effect = None
        for result, error in [(ProcessResult(1, "", "usage limit"), InteractionAgentError),
                              (ProcessResult(0, "not JSON", ""), ValidationError),
                              (ProcessResult(0, canonical(dict(prediction(), sequence_sha256="0" * 64)), ""), ValidationError)]:
            runner.reset_mock(); runner.run.return_value = result
            with self.assertRaises(error): agent.analyze(sequence())
            runner.run.assert_called_once()
        runner.reset_mock()
        with self.assertRaises(ValidationError): agent.analyze({})
        runner.run.assert_not_called()

    def test_real_command_transport_has_no_shell_interpretation(self):
        # A real offline subprocess verifies stdin transport; no model or network is used.
        request = '{"model":"$(not-a-command);literal"}'
        result = CommandSubprocessRunner().run(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            input_text=request, timeout=5)
        self.assertEqual((result.returncode, result.stdout), (0, request))

    def test_cli_configuration_and_offline_predictions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source, config, stored = (root / name for name in ["sequence.json", "config.json", "prediction.json"])
            source.write_text(canonical(sequence()))
            config.write_text(json.dumps({"ux_analyzer": {"model": "file-model", "timeout_seconds": 42}}))
            stored.write_text(canonical(prediction()))
            runner = Mock(return_value=ProcessResult(0, canonical(prediction()), ""))
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.codex.SubprocessRunner.run", runner), redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["ux-analyze", str(source), "--config", str(config), "--model", "cli-model"])
            self.assertEqual(status, 0, stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())["inference"], prediction())
            self.assertEqual(runner.call_args.args[0][-4:-2], ["--model", "cli-model"])
            self.assertEqual(runner.call_args.kwargs["timeout"], 42)
            runner.reset_mock()
            with patch("visparse.codex.SubprocessRunner.run", runner), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = main(["ux-analyze", str(source), "--predictions", str(stored),
                               "--config", str(root / "missing.json"), "--timeout-seconds", "nan"])
            self.assertEqual(status, 0)
            runner.assert_not_called()

    def test_cli_config_errors_prevent_execution(self):
        with TemporaryDirectory() as directory:
            source, config = Path(directory) / "source.json", Path(directory) / "config.json"
            source.write_text(canonical(sequence()))
            for document in ['{"ux_analyzer":{"model":"a","model":"b"}}',
                             '{"ux_analyzer":{"timeout_seconds":0}}', 'not json']:
                config.write_text(document)
                stderr = io.StringIO()
                with patch("visparse.interaction_config.InteractionAnalyzerConfig.create_analyzer") as factory, \
                        redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    status = main(["ux-analyze", str(source), "--config", str(config)])
                self.assertEqual(status, 2)
                self.assertTrue(stderr.getvalue().startswith("visparse: "))
                factory.assert_not_called()

"""Shared analyzer configuration and explicit external-agent transports."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from .codex import ProcessResult
from .contracts import canonical, check, load_json, shape
from .agent_options import validate_agent_options


class InteractionAgentError(RuntimeError):
    """An explicitly selected external agent failed; no fallback was attempted."""


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, input_text: str, timeout: float) -> ProcessResult: ...


class CommandSubprocessRunner:
    def run(self, argv: Sequence[str], *, input_text: str, timeout: float) -> ProcessResult:
        result = subprocess.run(list(argv), input=input_text, text=True, capture_output=True,
                                check=False, timeout=timeout)
        return ProcessResult(result.returncode, result.stdout, result.stderr)


@dataclass
class CommandInteractionAnalyzer:
    """Run a user-supplied protocol wrapper once, without a shell."""

    executable: str
    model: str | None = None
    timeout_seconds: float = 300
    runner: CommandRunner = field(default_factory=CommandSubprocessRunner)

    def analyze(self, sequence):
        from .interaction_analysis import interaction_prompt, validate_prediction
        validate_agent_options(self.executable, self.model, self.timeout_seconds)
        request = canonical({"schema_version": "interaction-analysis-request/0.1",
                             "model": self.model, "prompt": interaction_prompt(sequence)})
        try:
            result = self.runner.run([self.executable], input_text=request,
                                     timeout=self.timeout_seconds)
        except FileNotFoundError:
            raise InteractionAgentError("configured interaction agent executable unavailable") from None
        except subprocess.TimeoutExpired:
            raise InteractionAgentError("interaction agent timed out; no automatic retry") from None
        except OSError:
            raise InteractionAgentError("interaction agent could not start") from None
        if result.returncode:
            raise InteractionAgentError(f"interaction agent failed (status {result.returncode}); no automatic retry")
        return validate_prediction(sequence, load_json(result.stdout))


@dataclass(frozen=True)
class AnalyzerConfig:
    agent: str = "codex"
    executable: str | None = None
    model: str | None = None
    timeout_seconds: float = 300

    def __post_init__(self):
        check(self.agent in ("codex", "command"), "unsupported agent; choose codex or command")
        check(self.agent != "command" or self.executable is not None,
              "command agent requires an explicit executable")
        validate_agent_options(self.executable if self.executable is not None else "codex",
                               self.model, self.timeout_seconds)

    @classmethod
    def resolve(cls, document=None, *, command="ux-analyze", **overrides):
        """CLI > command settings > legacy UX settings > common settings > defaults."""
        check(command in ANALYSIS_COMMANDS, "unsupported analysis command")
        check(overrides.keys() <= OPTION_FIELDS, "unknown analyzer override")
        values = {"timeout_seconds": 120 if command == "analyze" else 300}
        if document is not None:
            shape(document, set(), {"analyzer", "commands", "ux_analyzer"})
            check(bool(document), "analyzer config must contain a settings section")
            for key in ("analyzer", "ux_analyzer"):
                if key in document:
                    validate_settings(document[key])
            commands = document.get("commands", {})
            shape(commands, set(), set(ANALYSIS_COMMANDS))
            for settings in commands.values():
                validate_settings(settings)
            check(command == "ux-analyze" or "analyzer" in document or command in commands,
                  "config has no common or matching command settings")
            values.update(document.get("analyzer", {}))
            if command == "ux-analyze":
                values.update(document.get("ux_analyzer", {}))
            values.update(commands.get(command, {}))
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls(**values)

    def adapter_options(self, command):
        """Reuse each analyzer's prompt and output validation with selected transport."""
        check(command in ANALYSIS_COMMANDS, "unsupported analysis command")
        options = {}
        if command != "analyze" or self.timeout_seconds != 120:
            options["timeout_seconds"] = self.timeout_seconds
        if self.model is not None:
            options["model"] = self.model
        if self.agent == "command":
            options["runner"] = CommandAgentRunner(self.executable, command, self.model)
        elif self.executable is not None:
            options["executable"] = self.executable
        return options

    def create_analyzer(self):
        """Compatibility factory for the existing UX Python API."""
        from .interaction_analysis import CodexInteractionAnalyzer
        if self.agent == "command":
            return CommandInteractionAnalyzer(executable=self.executable, model=self.model,
                                              timeout_seconds=self.timeout_seconds)
        return CodexInteractionAnalyzer(executable=self.executable if self.executable is not None else "codex",
                                        model=self.model, timeout_seconds=self.timeout_seconds)


ANALYSIS_COMMANDS = ("analyze", "analyze-design", "design-extract", "ux-analyze")
OPTION_FIELDS = {"agent", "executable", "model", "timeout_seconds"}


def validate_settings(settings):
    shape(settings, set(), OPTION_FIELDS)
    check(settings.get("agent", "codex") in ("codex", "command"), "unsupported agent; choose codex or command")
    validate_agent_options(settings.get("executable") if settings.get("executable") is not None else "codex",
                           settings.get("model"), settings.get("timeout_seconds", 300))


@dataclass
class CommandAgentRunner:
    """Adapt built-in prompt/image invocation data to the external JSON protocol.

    The supplied Codex-shaped argv is data only: Codex is never executed here.
    Validation remains in the calling analyzer, including image identity checks.
    """
    executable: str
    command: str
    model: str | None = None
    runner: CommandRunner = field(default_factory=CommandSubprocessRunner)

    def run(self, argv, *, timeout):
        validate_agent_options(self.executable, self.model, timeout)
        check(self.command in ANALYSIS_COMMANDS, "unsupported analysis command")
        check(len(argv) >= 2 and argv[-2] == "--", "expected a final analysis prompt")
        images = []
        index = 0
        while index < len(argv) - 2:
            if argv[index] == "--image":
                index += 1
                while index < len(argv) - 2 and not argv[index].startswith("--"):
                    images.append(argv[index])
                    index += 1
            else:
                index += 1
        request = canonical({"schema_version": "analysis-agent-request/0.1", "command": self.command,
                             "model": self.model, "prompt": argv[-1], "image_paths": images})
        try:
            result = self.runner.run([self.executable], input_text=request, timeout=timeout)
        except FileNotFoundError:
            raise InteractionAgentError("configured analysis agent executable unavailable") from None
        except subprocess.TimeoutExpired:
            raise InteractionAgentError("analysis agent timed out; no automatic retry") from None
        except OSError:
            raise InteractionAgentError("analysis agent could not start") from None
        if result.returncode:
            raise InteractionAgentError(f"analysis agent failed (status {result.returncode}); no automatic retry")
        return result


# Backwards-compatible imports; new callers should use AnalyzerConfig.
InteractionAnalyzerConfig = AnalyzerConfig
AnalysisAgentError = InteractionAgentError

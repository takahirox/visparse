"""Codex CLI-backed visual analyzer."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from .analyzer import Analyzer, run_analyzer
from .model import SourceEvidence, ValidationError


@dataclass(frozen=True)
class ProcessResult:
    """Provider-neutral captured process result."""

    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    """Mockable boundary for a captured subprocess call."""

    def run(
        self, argv: Sequence[str], *, timeout: float,
    ) -> ProcessResult:
        """Run argv without a shell and capture both output streams."""
        ...


class SubprocessRunner:
    """Concrete runner using the Python standard library."""

    def run(
        self, argv: Sequence[str], *, timeout: float,
    ) -> ProcessResult:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


class CodexAnalyzerError(RuntimeError):
    """Base class for stable Codex analyzer failures."""


class CodexUnavailableError(CodexAnalyzerError):
    """The configured Codex executable cannot be found."""


class CodexAuthenticationError(CodexAnalyzerError):
    """Codex CLI authentication is unavailable or rejected."""


class CodexTimeoutError(CodexAnalyzerError):
    """The Codex process exceeded its configured deadline."""


class CodexProcessError(CodexAnalyzerError):
    """Codex or its model failed before producing a usable response."""


class CodexJSONError(CodexAnalyzerError):
    """Codex stdout is not exactly one JSON value."""


class CodexJSONObjectError(CodexAnalyzerError):
    """Codex stdout is JSON but is not an object."""


class CodexValidationError(CodexAnalyzerError):
    """Codex output violates the schema or source identity contract."""


@dataclass
class CodexAnalyzer(Analyzer):
    """Analyze one image through a noninteractive Codex CLI invocation."""

    runner: ProcessRunner = field(default_factory=SubprocessRunner)
    executable: str = "codex"
    timeout_seconds: float = 120.0

    def analyze(self, evidence: SourceEvidence) -> dict[str, Any]:
        prompt = self._prompt(evidence)
        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="visparse-", suffix=".image", delete=False) as image:
                path = image.name
                os.chmod(path, 0o600)
                image.write(evidence.payload)
            result = self.runner.run(self._argv(path, prompt), timeout=self.timeout_seconds)
        except FileNotFoundError:
            raise CodexUnavailableError("codex executable is unavailable; install Codex CLI or configure executable") from None
        except subprocess.TimeoutExpired:
            raise CodexTimeoutError(f"codex analysis timed out after {self.timeout_seconds:g} seconds") from None
        except OSError as error:
            raise CodexProcessError("codex process could not be started") from error
        finally:
            if path is not None:
                Path(path).unlink(missing_ok=True)

        if result.returncode != 0:
            if _authentication_failure(result):
                raise CodexAuthenticationError("codex authentication failed; run 'codex login' and retry")
            detail = result.stderr.strip() or result.stdout.strip()
            suffix = f": {detail[:500]}" if detail else ""
            raise CodexProcessError(f"codex model/process failed with exit status {result.returncode}{suffix}")

        value = _json_object(result.stdout)
        try:
            return run_analyzer(_StaticAnalyzer(value), evidence)
        except (ValidationError, TypeError) as error:
            raise CodexValidationError(f"codex returned schema/source identity invalid output: {error}") from None

    def _argv(self, image_path: str, prompt: str) -> list[str]:
        return [
            self.executable,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--image",
            image_path,
            prompt,
        ]

    @staticmethod
    def _prompt(evidence: SourceEvidence) -> str:
        source_id = json.dumps(evidence.id, ensure_ascii=False)
        source_kind = json.dumps(evidence.kind, ensure_ascii=False)
        source_locator = json.dumps(evidence.locator, ensure_ascii=False)
        return (
            "Analyze the attached image as one Visparse 0.1 record.\n"
            "Return exactly one JSON object and nothing else: no Markdown, code fences, or commentary.\n"
            "Populate every field required by the Visparse 0.1 schema.\n"
            f"Use the unchanged source identity id={source_id}, kind={source_kind}, locator={source_locator}.\n"
            "Do not replace, normalize, reinterpret, or invent source identity values.\n"
            "Measurements must be mechanical values and state their mechanical method and unit when applicable.\n"
            "Observations must describe only what is directly visible in the attached evidence.\n"
            "Interpretations must be explicitly inferred and linked only to supporting observations.\n"
            "Every confidence entry must explicitly state both uncertainty and basis.\n"
            "Keep evidence, measurement, observation, interpretation, and confidence claims distinct."
        )


class _StaticAnalyzer(Analyzer):
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record

    def analyze(self, evidence: SourceEvidence) -> dict[str, Any]:
        del evidence
        return self.record


class _DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _json_object(output: str) -> dict[str, Any]:
    try:
        value = json.loads(
            output,
            object_pairs_hook=_unique_object,
        )
    except _DuplicateKeyError as error:
        raise CodexValidationError(f"codex returned duplicate JSON key {error.args[0]!r}") from None
    except (json.JSONDecodeError, TypeError):
        raise CodexJSONError("codex stdout must contain exactly one unfenced JSON object") from None
    if not isinstance(value, dict):
        raise CodexJSONObjectError("codex stdout JSON must be an object")
    return value


def _authentication_failure(result: ProcessResult) -> bool:
    text = f"{result.stderr}\n{result.stdout}".casefold()
    markers = (
        "authentication", "unauthorized", "not logged in",
        "log in", "login required", "api key",
    )
    return any(marker in text for marker in markers)

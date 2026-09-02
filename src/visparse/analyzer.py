"""Provider-neutral analysis boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .model import MAX_INPUT_BYTES, ValidationError, validate_record


@dataclass(frozen=True)
class SourceEvidence:
    """Opaque source material supplied to an analyzer implementation."""

    id: str
    kind: str
    locator: str
    payload: bytes

    def __post_init__(self) -> None:
        if not self.id or not self.kind or not self.locator:
            raise ValidationError("source evidence fields must be non-empty")
        if not isinstance(self.payload, bytes):
            raise TypeError("source evidence payload must be bytes")
        if len(self.payload) > MAX_INPUT_BYTES:
            raise ValidationError(f"source evidence exceeds {MAX_INPUT_BYTES} bytes")


class Analyzer(ABC):
    """Implementations turn evidence into a complete Visparse record."""

    @abstractmethod
    def analyze(self, evidence: SourceEvidence) -> dict[str, Any]:
        """Analyze evidence; interpretations must remain explicitly labeled."""
        raise NotImplementedError


def run_analyzer(analyzer: Analyzer, evidence: SourceEvidence) -> dict[str, Any]:
    """Run an analyzer and enforce output and source identity contracts."""
    record = validate_record(analyzer.analyze(evidence))
    matches = [item for item in record["sources"] if item["id"] == evidence.id]
    if len(matches) != 1:
        raise ValidationError("analyzer output must contain the supplied source id")
    if matches[0]["kind"] != evidence.kind or matches[0]["locator"] != evidence.locator:
        raise ValidationError("analyzer output changed source identity")
    return record

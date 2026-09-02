"""Provider-neutral analysis boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .model import SourceEvidence, ValidationError, validate_record


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

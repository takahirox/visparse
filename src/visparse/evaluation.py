"""Inspectable deterministic fixture evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .model import MAX_INPUT_BYTES, ValidationError, load_record, summarize_record, validate_record


@dataclass(frozen=True)
class EvaluationResult:
    total: int
    passed: int
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"failures": list(self.failures), "passed": self.passed, "total": self.total}


def load_fixture(payload: bytes | str) -> dict[str, Any]:
    """Decode a bounded evaluation fixture."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise TypeError("payload must be bytes or str")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError(f"fixture exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid fixture JSON: {error}") from None
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise ValidationError("fixture must be an object with a cases array")
    if len(value["cases"]) > 10_000:
        raise ValidationError("fixture has too many cases")
    return value


def evaluate_fixture(fixture: Mapping[str, Any]) -> EvaluationResult:
    """Evaluate validity and optional exact structural summaries."""
    if not isinstance(fixture, Mapping) or not isinstance(fixture.get("cases"), list):
        raise ValidationError("fixture must contain a cases array")
    failures: list[str] = []
    cases = fixture["cases"]
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            failures.append(f"case {index}: expected an object")
            continue
        name = case.get("name")
        if not isinstance(name, str) or not name:
            failures.append(f"case {index}: missing name")
            continue
        expected_valid = case.get("expected_valid")
        if not isinstance(expected_valid, bool):
            failures.append(f"{name}: expected_valid must be boolean")
            continue
        try:
            if "record" in case:
                record = validate_record(case["record"])
            elif "payload" in case and isinstance(case["payload"], str):
                record = load_record(case["payload"])
            else:
                raise ValidationError("case must contain record or string payload")
        except (ValidationError, TypeError) as error:
            if expected_valid:
                failures.append(f"{name}: unexpectedly invalid: {error}")
            continue
        if not expected_valid:
            failures.append(f"{name}: unexpectedly valid")
            continue
        if "expected_summary" in case:
            actual = summarize_record(record)
            if actual != case["expected_summary"]:
                failures.append(f"{name}: summary mismatch")
    return EvaluationResult(total=len(cases), passed=len(cases) - len(failures), failures=tuple(failures))

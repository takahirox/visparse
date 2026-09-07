"""Small shared contracts for the versioned design workflow."""

from __future__ import annotations

import json
import math
from typing import Any

from .model import MAX_INPUT_BYTES, ValidationError, _json_shape, _reject_duplicates


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def shape(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    check(isinstance(value, dict), "expected an object")
    check(required <= value.keys() and value.keys() <= required | optional,
          f"expected fields {sorted(required)}; optional {sorted(optional)}")


def text(value: Any) -> str:
    check(isinstance(value, str) and bool(value.strip()), "expected non-empty text")
    return value


def number(value: Any, low: float | None = None, high: float | None = None) -> float:
    finite = False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            pass
    check(finite, "expected a finite number")
    check(low is None or value >= low, f"number must be >= {low}")
    check(high is None or value <= high, f"number must be <= {high}")
    return value


def items(value: Any) -> list:
    check(isinstance(value, list), "expected an array")
    return value


def unique(values: list, key: str = "id") -> dict:
    result = {}
    for value in items(values):
        check(isinstance(value, dict) and key in value, f"expected object with {key}")
        name = text(value[key])
        check(name not in result, f"duplicate {key}: {name}")
        result[name] = value
    return result


def refs(values: Any, known: dict | set, *, nonempty: bool = True) -> list[str]:
    values = items(values)
    check(bool(values) or not nonempty, "expected non-empty references")
    for value in values:
        text(value)
    check(len(set(values)) == len(values), "duplicate reference")
    check(all(v in known for v in values), "unknown reference")
    return values


def canonical(value: Any) -> str:
    _json_shape(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def bounded(value: Any) -> Any:
    check(len(canonical(value).encode("utf-8")) <= MAX_INPUT_BYTES, "input/output exceeds byte limit")
    return value


def load_json(payload: bytes | str) -> Any:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    check(isinstance(raw, bytes), "expected bytes or string")
    check(len(raw) <= MAX_INPUT_BYTES, "input exceeds byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError(f"invalid JSON: {error}") from None
    return bounded(value)

"""Validation and canonical serialization for Visparse records."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "0.1"
MAX_INPUT_BYTES = 1_000_000
MAX_ITEMS = 10_000
MAX_DEPTH = 24
MAX_STRING_LENGTH = 100_000


class ValidationError(ValueError):
    """A stable, user-facing record validation error."""


def _fail(path: str, message: str) -> None:
    raise ValidationError(f"{path}: {message}")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "expected a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        _fail(path, "string is too long")
    return value


def _json_shape(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        _fail(path, "maximum nesting depth exceeded")
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            _fail(path, "string is too long")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(path, "non-finite numbers are not JSON")
        return
    if isinstance(value, list):
        if len(value) > MAX_ITEMS:
            _fail(path, "too many items")
        for index, item in enumerate(value):
            _json_shape(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            _fail(path, "too many properties")
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(path, "object keys must be strings")
            _json_shape(item, f"{path}.{key}", depth + 1)
        return
    _fail(path, f"unsupported value type {type(value).__name__}")


def _objects(record: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    value = record.get(name)
    if not isinstance(value, list):
        _fail(name, "expected an array")
    if len(value) > MAX_ITEMS:
        _fail(name, "too many records")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _fail(f"{name}[{index}]", "expected an object")
    return value


def _ids(items: list[dict[str, Any]], name: str, all_ids: set[str]) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(items):
        item_id = _text(item.get("id"), f"{name}[{index}].id")
        if item_id in all_ids:
            _fail(f"{name}[{index}].id", f"duplicate id {item_id!r}")
        all_ids.add(item_id)
        result.add(item_id)
    return result


def _references(value: Any, path: str, known: set[str], *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(path, "expected a non-empty array" if nonempty else "expected an array")
    result: list[str] = []
    for index, reference in enumerate(value):
        reference = _text(reference, f"{path}[{index}]")
        if reference not in known:
            _fail(f"{path}[{index}]", f"unknown reference {reference!r}")
        result.append(reference)
    return result


def validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a record and return it without adding or inferring data."""
    if not isinstance(record, dict):
        _fail("$", "expected an object")
    _json_shape(record)
    required = {
        "schema_version", "sources", "measurements", "observations",
        "interpretations", "confidence", "interactions", "provenance",
    }
    missing = sorted(required - record.keys())
    extra = sorted(record.keys() - required)
    if missing:
        _fail("$", f"missing fields: {', '.join(missing)}")
    if extra:
        _fail("$", f"unknown fields: {', '.join(extra)}")
    if record["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", f"expected {SCHEMA_VERSION!r}")

    sources = _objects(record, "sources")
    measurements = _objects(record, "measurements")
    observations = _objects(record, "observations")
    interpretations = _objects(record, "interpretations")
    confidence = _objects(record, "confidence")
    interactions = _objects(record, "interactions")
    if sum(map(len, (sources, measurements, observations, interpretations, confidence, interactions))) > MAX_ITEMS:
        _fail("$", "too many total records")

    all_ids: set[str] = set()
    source_ids = _ids(sources, "sources", all_ids)
    measurement_ids = _ids(measurements, "measurements", all_ids)
    observation_ids = _ids(observations, "observations", all_ids)
    interpretation_ids = _ids(interpretations, "interpretations", all_ids)
    confidence_ids = _ids(confidence, "confidence", all_ids)
    interaction_ids = _ids(interactions, "interactions", all_ids)
    del measurement_ids, interpretation_ids, interaction_ids

    for index, source in enumerate(sources):
        _text(source.get("kind"), f"sources[{index}].kind")
        _text(source.get("locator"), f"sources[{index}].locator")
        if "content_hash" in source:
            _text(source["content_hash"], f"sources[{index}].content_hash")

    for index, measurement in enumerate(measurements):
        path = f"measurements[{index}]"
        reference = _text(measurement.get("source_id"), f"{path}.source_id")
        if reference not in source_ids:
            _fail(f"{path}.source_id", f"unknown reference {reference!r}")
        _text(measurement.get("name"), f"{path}.name")
        _text(measurement.get("method"), f"{path}.method")
        if "value" not in measurement or isinstance(measurement.get("value"), (dict, list)):
            _fail(f"{path}.value", "expected a scalar JSON value")
        if "unit" in measurement:
            _text(measurement["unit"], f"{path}.unit")

    for index, observation in enumerate(observations):
        path = f"observations[{index}]"
        _references(observation.get("source_ids"), f"{path}.source_ids", source_ids, nonempty=True)
        _text(observation.get("statement"), f"{path}.statement")

    for index, item in enumerate(confidence):
        path = f"confidence[{index}]"
        level = item.get("level")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= 1:
            _fail(f"{path}.level", "expected a number from 0 through 1")
        _text(item.get("uncertainty"), f"{path}.uncertainty")
        _text(item.get("basis"), f"{path}.basis")

    for index, interpretation in enumerate(interpretations):
        path = f"interpretations[{index}]"
        _references(interpretation.get("observation_ids"), f"{path}.observation_ids", observation_ids, nonempty=True)
        reference = _text(interpretation.get("confidence_id"), f"{path}.confidence_id")
        if reference not in confidence_ids:
            _fail(f"{path}.confidence_id", f"unknown reference {reference!r}")
        _text(interpretation.get("statement"), f"{path}.statement")

    for index, interaction in enumerate(interactions):
        path = f"interactions[{index}]"
        kind = interaction.get("kind")
        if kind not in {"web", "ui", "temporal"}:
            _fail(f"{path}.kind", "expected web, ui, or temporal")
        if not isinstance(interaction.get("details"), dict):
            _fail(f"{path}.details", "expected an object")
        if "source_id" in interaction:
            reference = _text(interaction["source_id"], f"{path}.source_id")
            if reference not in source_ids:
                _fail(f"{path}.source_id", f"unknown reference {reference!r}")
        if kind == "temporal" or "timestamp" in interaction:
            _text(interaction.get("timestamp"), f"{path}.timestamp")

    provenance = record["provenance"]
    if not isinstance(provenance, dict):
        _fail("provenance", "expected an object")
    _text(provenance.get("created_by"), "provenance.created_by")
    _references(provenance.get("inputs"), "provenance.inputs", source_ids)
    if "created_at" in provenance:
        _text(provenance["created_at"], "provenance.created_at")
    return record


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"$: duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_record(payload: bytes | str) -> dict[str, Any]:
    """Decode bounded UTF-8 JSON and validate it as a record."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise TypeError("payload must be bytes or str")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON: {error}") from None
    return validate_record(value)


def normalize_record(record: Mapping[str, Any]) -> str:
    """Return the validated record as canonical JSON plus one newline."""
    validated = validate_record(record)
    return json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def summarize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return structural facts only; no semantic conclusions are inferred."""
    validated = validate_record(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "counts": {name: len(validated[name]) for name in (
            "sources", "measurements", "observations", "interpretations", "confidence", "interactions"
        )},
        "source_kinds": sorted({item["kind"] for item in validated["sources"]}),
        "interaction_kinds": sorted({item["kind"] for item in validated["interactions"]}),
    }

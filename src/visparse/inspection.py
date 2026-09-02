"""Validation and tool-facing interfaces for supplied interactive-experience evidence."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from .model import (
    MAX_DEPTH,
    MAX_INPUT_BYTES,
    MAX_ITEMS,
    MAX_STRING_LENGTH,
    ValidationError,
)

INSPECTION_SCHEMA_VERSION = "0.1"
CAPTURE_KINDS = frozenset({
    "accessibility", "canvas", "css", "dom", "runtime", "screenshot",
    "threejs", "video", "webgl",
})
RUNTIME_CAPTURE_KINDS = frozenset({
    "accessibility", "canvas", "css", "dom", "runtime", "threejs", "webgl",
})
VISUAL_CAPTURE_KINDS = frozenset({"canvas", "screenshot", "video", "webgl"})
_THREE_NAMES = frozenset({"three", "three.js", "threejs"})


def _fail(path: str, message: str) -> None:
    raise ValidationError(f"{path}: {message}")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "expected a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        _fail(path, "string is too long")
    return value


def _shape(value: Any, path: str = "$", depth: int = 0) -> None:
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
            _shape(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            _fail(path, "too many properties")
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(path, "object keys must be strings")
            _shape(item, f"{path}.{key}", depth + 1)
        return
    _fail(path, f"unsupported value type {type(value).__name__}")


def _exact(
    item: Mapping[str, Any],
    path: str,
    required: set[str],
    optional: set[str] = set(),
) -> None:
    missing = sorted(required - item.keys())
    extra = sorted(item.keys() - required - optional)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _objects(bundle: Mapping[str, Any], name: str, *, nonempty: bool = False) -> list[dict[str, Any]]:
    value = bundle.get(name)
    if not isinstance(value, list) or (nonempty and not value):
        _fail(name, "expected a non-empty array" if nonempty else "expected an array")
    if len(value) > MAX_ITEMS or any(not isinstance(item, dict) for item in value):
        _fail(name, "expected a bounded array of objects")
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


def _references(
    value: Any,
    path: str,
    known: set[str],
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(path, "expected a non-empty array" if nonempty else "expected an array")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        reference = _text(item, f"{path}[{index}]")
        if reference not in known:
            _fail(f"{path}[{index}]", f"unknown reference {reference!r}")
        if reference in seen:
            _fail(f"{path}[{index}]", f"duplicate reference {reference!r}")
        result.append(reference)
        seen.add(reference)
    return result


def _observation_sources(
    observations: list[dict[str, Any]],
    name: str,
    source_ids: set[str],
    source_kinds: Mapping[str, str],
    compatible_kinds: frozenset[str],
) -> None:
    for index, observation in enumerate(observations):
        path = f"{name}[{index}]"
        _exact(observation, path, {"id", "source_ids", "statement"})
        references = _references(
            observation["source_ids"], f"{path}.source_ids", source_ids, nonempty=True,
        )
        if not any(source_kinds[item] in compatible_kinds for item in references):
            _fail(
                f"{path}.source_ids",
                f"must cite at least one {name.removesuffix('_observations')} capture",
            )
        _text(observation["statement"], f"{path}.statement")


def validate_inspection(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Validate supplied evidence without collecting, repairing, or interpreting it."""
    if not isinstance(bundle, dict):
        _fail("$", "expected an object")
    _shape(bundle)
    _exact(bundle, "$", {
        "schema_version", "captures", "measurements", "runtime_observations",
        "visual_observations", "interpretations", "confidence", "provenance",
    })
    if bundle["schema_version"] != INSPECTION_SCHEMA_VERSION:
        _fail("schema_version", f"expected {INSPECTION_SCHEMA_VERSION!r}")

    captures = _objects(bundle, "captures", nonempty=True)
    measurements = _objects(bundle, "measurements")
    runtime_observations = _objects(bundle, "runtime_observations")
    visual_observations = _objects(bundle, "visual_observations")
    interpretations = _objects(bundle, "interpretations")
    confidence = _objects(bundle, "confidence")
    if sum(map(len, (
        captures, measurements, runtime_observations, visual_observations,
        interpretations, confidence,
    ))) > MAX_ITEMS:
        _fail("$", "too many total records")

    all_ids: set[str] = set()
    source_ids = _ids(captures, "captures", all_ids)
    measurement_ids = _ids(measurements, "measurements", all_ids)
    runtime_ids = _ids(runtime_observations, "runtime_observations", all_ids)
    visual_ids = _ids(visual_observations, "visual_observations", all_ids)
    _ids(interpretations, "interpretations", all_ids)
    confidence_ids = _ids(confidence, "confidence", all_ids)

    source_kinds: dict[str, str] = {}
    for index, capture in enumerate(captures):
        path = f"captures[{index}]"
        _exact(capture, path, {"id", "kind", "locator", "payload"})
        source_id = _text(capture["id"], f"{path}.id")
        if capture["kind"] not in CAPTURE_KINDS:
            _fail(f"{path}.kind", f"expected one of {', '.join(sorted(CAPTURE_KINDS))}")
        source_kinds[source_id] = capture["kind"]
        _text(capture["locator"], f"{path}.locator")

    for index, measurement in enumerate(measurements):
        path = f"measurements[{index}]"
        _exact(measurement, path, {"id", "source_id", "name", "value", "method"}, {"unit"})
        reference = _text(measurement["source_id"], f"{path}.source_id")
        if reference not in source_ids:
            _fail(f"{path}.source_id", f"unknown reference {reference!r}")
        _text(measurement["name"], f"{path}.name")
        value = measurement["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            _fail(f"{path}.value", "expected a finite numeric exact value")
        _text(measurement["method"], f"{path}.method")
        if "unit" in measurement:
            _text(measurement["unit"], f"{path}.unit")

    _observation_sources(
        runtime_observations, "runtime_observations", source_ids,
        source_kinds, RUNTIME_CAPTURE_KINDS,
    )
    _observation_sources(
        visual_observations, "visual_observations", source_ids,
        source_kinds, VISUAL_CAPTURE_KINDS,
    )

    for index, item in enumerate(confidence):
        path = f"confidence[{index}]"
        _exact(item, path, {"id", "level", "uncertainty", "basis"})
        level = item["level"]
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level) or not 0 <= level <= 1:
            _fail(f"{path}.level", "expected a finite number from 0 through 1")
        _text(item["uncertainty"], f"{path}.uncertainty")
        _text(item["basis"], f"{path}.basis")

    evidence_ids = measurement_ids | runtime_ids | visual_ids
    for index, interpretation in enumerate(interpretations):
        path = f"interpretations[{index}]"
        _exact(
            interpretation, path,
            {"id", "evidence_ids", "statement", "confidence_id"},
        )
        _references(
            interpretation["evidence_ids"], f"{path}.evidence_ids",
            evidence_ids, nonempty=True,
        )
        _text(interpretation["statement"], f"{path}.statement")
        confidence_id = _text(
            interpretation["confidence_id"], f"{path}.confidence_id",
        )
        if confidence_id not in confidence_ids:
            _fail(f"{path}.confidence_id", f"unknown reference {confidence_id!r}")

    provenance = bundle["provenance"]
    if not isinstance(provenance, dict):
        _fail("provenance", "expected an object")
    _exact(provenance, "provenance", {"created_by", "inputs"})
    _text(provenance["created_by"], "provenance.created_by")
    inputs = _references(
        provenance["inputs"], "provenance.inputs", source_ids, nonempty=True,
    )
    if set(inputs) != source_ids:
        _fail("provenance.inputs", "must name every supplied capture exactly once")
    return bundle


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"$: duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_inspection(payload: bytes | str) -> dict[str, Any]:
    """Decode bounded UTF-8 JSON and validate an inspection bundle."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise TypeError("payload must be bytes or str")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON: {error}") from None
    return validate_inspection(value)


def normalize_inspection(bundle: Mapping[str, Any]) -> str:
    """Return a validated inspection bundle as canonical JSON plus one newline."""
    validated = validate_inspection(bundle)
    return json.dumps(
        validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def inspect_snapshot(payload: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
    """Tool-facing entry point for an already collected capture bundle."""
    if isinstance(payload, Mapping):
        return validate_inspection(payload)
    return load_inspection(payload)


def _three_marker(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    values: list[Any] = [
        payload.get("technology"), payload.get("library"), payload.get("engine"),
    ]
    for key in ("technologies", "libraries"):
        item = payload.get(key)
        if isinstance(item, list):
            values.extend(item)
    for key in ("renderer", "engine"):
        item = payload.get(key)
        if isinstance(item, dict):
            values.extend((item.get("name"), item.get("library"), item.get("technology")))
    globals_value = payload.get("globals")
    if isinstance(globals_value, dict) and "THREE" in globals_value:
        return True
    return any(
        isinstance(value, str) and value.strip().lower() in _THREE_NAMES
        for value in values
    )


def _threejs_evidence(bundle: Mapping[str, Any]) -> dict[str, Any]:
    supplied = [
        item["id"] for item in bundle["captures"] if item["kind"] == "threejs"
    ]
    if supplied:
        return {"status": "high_level", "source_ids": supplied}
    detected = [
        item["id"] for item in bundle["captures"]
        if item["kind"] in {"runtime", "webgl"} and _three_marker(item["payload"])
    ]
    if detected:
        return {"status": "detected", "source_ids": detected}
    return {"status": "not_available", "source_ids": []}


def summarize_inspection(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return structural availability facts, never conclusions about the experience."""
    validated = validate_inspection(bundle)
    return {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "counts": {
            name: len(validated[name]) for name in (
                "captures", "measurements", "runtime_observations",
                "visual_observations", "interpretations", "confidence",
            )
        },
        "capture_kinds": sorted({item["kind"] for item in validated["captures"]}),
        "threejs_evidence": _threejs_evidence(validated),
    }


def inspection_capabilities() -> dict[str, Any]:
    """Describe the provider-neutral contract for agents and future tool wrappers."""
    return {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "input_mode": "supplied_capture_bundle",
        "browser_automation": False,
        "capture_kinds": sorted(CAPTURE_KINDS),
        "operations": [
            "inspect_snapshot", "summarize_inspection", "inspection_capabilities",
        ],
        "evidence_layers": [
            "measurements", "runtime_observations", "visual_observations",
            "interpretations",
        ],
        "threejs": {
            "progressive": True,
            "high_level_capture_kind": "threejs",
            "detection_inputs": ["runtime", "webgl"],
        },
    }

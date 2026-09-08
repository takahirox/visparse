"""Provider-neutral design-language analysis for screenshot evidence."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .codex import (
    CodexAuthenticationError,
    CodexProcessError,
    CodexTimeoutError,
    CodexUnavailableError,
    CodexValidationError,
    ProcessRunner,
    SubprocessRunner,
    _authentication_failure,
    _json_object,
)
from .model import MAX_DEPTH, MAX_INPUT_BYTES, MAX_ITEMS, MAX_STRING_LENGTH, SourceEvidence, ValidationError
from .contracts import check, number
from .geometry import validate_geometry, validate_region_requests

DESIGN_SCHEMA_VERSION = "0.2"
DESIGN_CATEGORIES = frozenset({
    "layout", "visual_hierarchy", "spacing_density", "typography",
    "color_usage", "component_styling", "ui_patterns", "section_rhythm",
    "navigation", "imagery_media", "design_tone", "strength", "weakness",
})
INTERPRETIVE_DESIGN_CATEGORIES = frozenset({"design_tone", "strength", "weakness"})
OBSERVATION_DESIGN_CATEGORIES = DESIGN_CATEGORIES - INTERPRETIVE_DESIGN_CATEGORIES
AVOID_COPYING = frozenset({"assets", "branding", "content", "implementation"})
_UNSAFE_RECOMMENDATION = re.compile(
    r"\bclone\b|\b(?:copy|duplicate|replicate|reproduce|lift|reuse)\b"
    r"[^.!?\n]{0,120}\b(?:assets?|branding|content|copy|logos?|dom|css|implementation)\b",
    re.IGNORECASE,
)


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


def _exact(item: Mapping[str, Any], path: str, required: set[str], optional: set[str] = set()) -> None:
    missing = sorted(required - item.keys())
    extra = sorted(item.keys() - required - optional)
    if missing:
        _fail(path, f"missing fields: {', '.join(missing)}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(extra)}")


def _objects(profile: Mapping[str, Any], name: str, *, nonempty: bool = False) -> list[dict[str, Any]]:
    value = profile.get(name)
    if not isinstance(value, list) or (nonempty and not value):
        _fail(name, "expected a non-empty array" if nonempty else "expected an array")
    if len(value) > MAX_ITEMS:
        _fail(name, "too many records")
    if any(not isinstance(item, dict) for item in value):
        _fail(name, "expected an array of objects")
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
    seen: set[str] = set()
    result: list[str] = []
    for index, item in enumerate(value):
        reference = _text(item, f"{path}[{index}]")
        if reference not in known:
            _fail(f"{path}[{index}]", f"unknown reference {reference!r}")
        if reference in seen:
            _fail(f"{path}[{index}]", f"duplicate reference {reference!r}")
        seen.add(reference)
        result.append(reference)
    return result


def _category(value: Any, path: str) -> None:
    if value not in DESIGN_CATEGORIES:
        _fail(path, f"expected one of {', '.join(sorted(DESIGN_CATEGORIES))}")


def validate_design_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a design profile without repairing model-authored meaning."""
    if not isinstance(profile, dict):
        _fail("$", "expected an object")
    _shape(profile)
    _exact(profile, "$", {
        "schema_version", "sources", "measurements", "observations",
        "interpretations", "confidence", "principles", "recommendations",
        "provenance",
    })
    if profile["schema_version"] not in ("0.1", DESIGN_SCHEMA_VERSION):
        _fail("schema_version", "expected '0.1' or '0.2'")

    sources = _objects(profile, "sources", nonempty=True)
    measurements = _objects(profile, "measurements")
    observations = _objects(profile, "observations", nonempty=True)
    interpretations = _objects(profile, "interpretations")
    confidence = _objects(profile, "confidence")
    principles = _objects(profile, "principles", nonempty=True)
    recommendations = _objects(profile, "recommendations", nonempty=True)
    if sum(map(len, (sources, measurements, observations, interpretations, confidence, principles, recommendations))) > MAX_ITEMS:
        _fail("$", "too many total records")

    all_ids: set[str] = set()
    source_ids = _ids(sources, "sources", all_ids)
    _ids(measurements, "measurements", all_ids)
    observation_ids = _ids(observations, "observations", all_ids)
    _ids(interpretations, "interpretations", all_ids)
    confidence_ids = _ids(confidence, "confidence", all_ids)
    principle_ids = _ids(principles, "principles", all_ids)
    _ids(recommendations, "recommendations", all_ids)

    source_roles: dict[str, str] = {}
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        _exact(source, path, {"id", "kind", "locator", "role"})
        source_id = _text(source["id"], f"{path}.id")
        _text(source["kind"], f"{path}.kind")
        _text(source["locator"], f"{path}.locator")
        if source["role"] not in {"reference", "target"}:
            _fail(f"{path}.role", "expected reference or target")
        source_roles[source_id] = source["role"]
    if "reference" not in source_roles.values():
        _fail("sources", "at least one reference screenshot is required")

    for index, measurement in enumerate(measurements):
        path = f"measurements[{index}]"
        _exact(measurement, path, {"id", "source_id", "name", "value", "method"}, {"unit"})
        reference = _text(measurement["source_id"], f"{path}.source_id")
        if reference not in source_ids:
            _fail(f"{path}.source_id", f"unknown reference {reference!r}")
        _text(measurement["name"], f"{path}.name")
        _text(measurement["method"], f"{path}.method")
        value = measurement["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            _fail(f"{path}.value", "expected a finite numeric mechanical value")
        if "unit" in measurement:
            _text(measurement["unit"], f"{path}.unit")

    used_sources: set[str] = set()
    for index, observation in enumerate(observations):
        path = f"observations[{index}]"
        _exact(observation, path, {"id", "source_ids", "category", "statement"})
        used_sources.update(_references(observation["source_ids"], f"{path}.source_ids", source_ids, nonempty=True))
        _category(observation["category"], f"{path}.category")
        if observation["category"] in INTERPRETIVE_DESIGN_CATEGORIES:
            _fail(
                f"{path}.category",
                "design_tone, strength, and weakness are interpretations, not direct observations",
            )
        _text(observation["statement"], f"{path}.statement")

    for index, item in enumerate(confidence):
        path = f"confidence[{index}]"
        _exact(item, path, {"id", "level", "uncertainty", "basis"})
        level = item["level"]
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level) or not 0 <= level <= 1:
            _fail(f"{path}.level", "expected a finite number from 0 through 1")
        _text(item["uncertainty"], f"{path}.uncertainty")
        _text(item["basis"], f"{path}.basis")

    observation_map = {o["id"]: o for o in observations}
    geometry_keys = set()
    for index, interpretation in enumerate(interpretations):
        path = f"interpretations[{index}]"
        _exact(interpretation, path, {"id", "observation_ids", "category", "statement", "confidence_id"},
               {"geometry"} if profile["schema_version"] == "0.2" else set())
        _references(interpretation["observation_ids"], f"{path}.observation_ids", observation_ids, nonempty=True)
        _category(interpretation["category"], f"{path}.category")
        _text(interpretation["statement"], f"{path}.statement")
        confidence_id = _text(interpretation["confidence_id"], f"{path}.confidence_id")
        if confidence_id not in confidence_ids:
            _fail(f"{path}.confidence_id", f"unknown reference {confidence_id!r}")
        if "geometry" in interpretation:
            geometry = interpretation["geometry"]
            validate_geometry(geometry)
            check(interpretation["category"] == "layout", "geometry interpretation must use layout category")
            anchors = {sid for oid in interpretation["observation_ids"] for sid in observation_map[oid]["source_ids"]}
            check(len(anchors) == 1, "geometry requires exactly one source")
            key = (next(iter(anchors)), geometry["region"])
            check(key not in geometry_keys, "duplicate geometry for source and region")
            geometry_keys.add(key)

    for index, principle in enumerate(principles):
        path = f"principles[{index}]"
        _exact(principle, path, {"id", "observation_ids", "interpretation_ids", "statement"})
        _references(principle["observation_ids"], f"{path}.observation_ids", observation_ids, nonempty=True)
        _references(
            principle["interpretation_ids"], f"{path}.interpretation_ids",
            {item["id"] for item in interpretations},
        )
        _text(principle["statement"], f"{path}.statement")

    target_source_ids = {source_id for source_id, role in source_roles.items() if role == "target"}
    for index, recommendation in enumerate(recommendations):
        path = f"recommendations[{index}]"
        _exact(recommendation, path, {
            "id", "principle_ids", "target_source_ids", "action", "rationale",
            "transfer_mode", "avoid_copying",
        })
        _references(recommendation["principle_ids"], f"{path}.principle_ids", principle_ids, nonempty=True)
        _references(recommendation["target_source_ids"], f"{path}.target_source_ids", target_source_ids)
        _text(recommendation["action"], f"{path}.action")
        _text(recommendation["rationale"], f"{path}.rationale")
        if _UNSAFE_RECOMMENDATION.search(f"{recommendation['action']}\n{recommendation['rationale']}"):
            _fail(path, "recommendation requests copying or cloning")
        if recommendation["transfer_mode"] != "principle":
            _fail(f"{path}.transfer_mode", "expected principle")
        avoid_copying = recommendation["avoid_copying"]
        if not isinstance(avoid_copying, list) or set(avoid_copying) != AVOID_COPYING or len(avoid_copying) != len(AVOID_COPYING):
            _fail(f"{path}.avoid_copying", "must contain assets, branding, content, and implementation exactly once")

    missing_sources = source_ids - used_sources
    if missing_sources:
        _fail("observations", f"no observation cites sources: {', '.join(sorted(missing_sources))}")

    provenance = profile["provenance"]
    if not isinstance(provenance, dict):
        _fail("provenance", "expected an object")
    _exact(provenance, "provenance", {"created_by", "inputs"})
    _text(provenance["created_by"], "provenance.created_by")
    inputs = _references(provenance["inputs"], "provenance.inputs", source_ids, nonempty=True)
    if set(inputs) != source_ids:
        _fail("provenance.inputs", "must name every supplied source exactly once")
    return profile


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"$: duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_design_profile(payload: bytes | str) -> dict[str, Any]:
    """Decode bounded UTF-8 JSON and validate a design profile."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes):
        raise TypeError("payload must be bytes or str")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON: {error}") from None
    return validate_design_profile(value)


def normalize_design_profile(profile: Mapping[str, Any]) -> str:
    """Return a validated design profile as canonical JSON plus one newline."""
    validated = validate_design_profile(profile)
    return json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def summarize_design_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return structural facts without repeating model-authored conclusions."""
    validated = validate_design_profile(profile)
    return {
        "schema_version": DESIGN_SCHEMA_VERSION,
        "counts": {name: len(validated[name]) for name in (
            "sources", "measurements", "observations", "interpretations",
            "confidence", "principles", "recommendations",
        )},
        "categories": sorted({item["category"] for item in validated["observations"] + validated["interpretations"]}),
        "source_roles": sorted({item["role"] for item in validated["sources"]}),
    }


class DesignAnalyzer(ABC):
    """Provider-neutral boundary for screenshot design-language analysis."""

    @abstractmethod
    def analyze(
        self,
        references: Sequence[SourceEvidence],
        targets: Sequence[SourceEvidence] = (),
    ) -> dict[str, Any]:
        """Return one untrusted design profile for the supplied evidence."""
        raise NotImplementedError


def run_design_analyzer(
    analyzer: DesignAnalyzer,
    references: Sequence[SourceEvidence],
    targets: Sequence[SourceEvidence] = (),
) -> dict[str, Any]:
    """Run an analyzer and enforce exact source identities and roles."""
    if not references:
        raise ValidationError("at least one reference screenshot is required")
    supplied = list(references) + list(targets)
    if len({item.id for item in supplied}) != len(supplied):
        raise ValidationError("source evidence ids must be unique")
    profile = validate_design_profile(analyzer.analyze(references, targets))
    expected = {
        item.id: (item.kind, item.locator, "reference" if index < len(references) else "target")
        for index, item in enumerate(supplied)
    }
    actual = {item["id"]: (item["kind"], item["locator"], item["role"]) for item in profile["sources"]}
    if actual != expected:
        raise ValidationError("design analyzer output changed source identity or role")
    return profile


@dataclass
class CodexDesignAnalyzer(DesignAnalyzer):
    """Codex CLI adapter for one or more reference and target screenshots."""

    runner: ProcessRunner = field(default_factory=SubprocessRunner)
    executable: str = "codex"
    timeout_seconds: float = 300.0
    intent: str = "adapt"
    estimate_geometry: bool = False
    geometry_regions: Sequence[str] = ()

    def analyze(
        self,
        references: Sequence[SourceEvidence],
        targets: Sequence[SourceEvidence] = (),
    ) -> dict[str, Any]:
        check(self.intent in ("preserve", "adapt"), "intent must be preserve or adapt")
        check(type(self.estimate_geometry) is bool, "estimate_geometry must be a boolean")
        validate_region_requests(self.geometry_regions, self.estimate_geometry)
        number(self.timeout_seconds, 1, 900)
        if not references:
            raise ValidationError("at least one reference screenshot is required")
        supplied = list(references) + list(targets)
        paths: list[str] = []
        try:
            for evidence in supplied:
                with tempfile.NamedTemporaryFile(prefix="visparse-design-", suffix=".image", delete=False) as image:
                    os.chmod(image.name, 0o600)
                    image.write(evidence.payload)
                    paths.append(image.name)
            result = self.runner.run(self._argv(paths, self._prompt(
                references, targets, intent=self.intent, estimate_geometry=self.estimate_geometry,
                geometry_regions=self.geometry_regions,
            )), timeout=self.timeout_seconds)
        except FileNotFoundError:
            raise CodexUnavailableError("codex executable is unavailable; install Codex CLI or configure executable") from None
        except subprocess.TimeoutExpired:
            raise CodexTimeoutError(f"codex design analysis timed out after {self.timeout_seconds:g} seconds") from None
        except OSError as error:
            raise CodexProcessError("codex process could not be started") from error
        finally:
            for path in paths:
                Path(path).unlink(missing_ok=True)
        if result.returncode != 0:
            if _authentication_failure(result):
                raise CodexAuthenticationError("codex authentication failed; run 'codex login' and retry")
            detail = result.stderr.strip() or result.stdout.strip()
            suffix = f": {detail[:500]}" if detail else ""
            raise CodexProcessError(f"codex model/process failed with exit status {result.returncode}{suffix}")
        try:
            profile = run_design_analyzer(_StaticDesignAnalyzer(_json_object(result.stdout)), references, targets)
            if profile["measurements"]:
                raise ValidationError(
                    "Codex design analysis has no trusted mechanical measurement channel; measurements must be empty"
                )
            observations = {o['id']: o for o in profile['observations']}
            covered = {(sid, i['geometry']['region']) for i in profile['interpretations'] if 'geometry' in i
                       for oid in i['observation_ids'] for sid in observations[oid]['source_ids']}
            check(self.estimate_geometry or not covered, "geometry was not requested")
            missing = sorted({(s.id, region) for s in supplied for region in self.geometry_regions} - covered)
            check(not missing, f"missing requested geometry (return estimates or explicit unknowns): {missing}")
            return profile
        except (ValidationError, TypeError) as error:
            raise CodexValidationError(f"codex returned invalid design profile: {error}") from None

    def _argv(self, image_paths: Sequence[str], prompt: str) -> list[str]:
        return [
            self.executable, "exec", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
            "--disable", "apps", "--disable", "plugins", "--disable", "memories",
            "-c", "memories.use_memories=false", "-c", "memories.generate_memories=false",
            "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
            "--image", *image_paths, "--", prompt,
        ]

    @staticmethod
    def _prompt(references: Sequence[SourceEvidence], targets: Sequence[SourceEvidence], *,
                intent: str = "adapt", estimate_geometry: bool = False, geometry_regions: Sequence[str] = ()) -> str:
        check(intent in ("preserve", "adapt"), "intent must be preserve or adapt")
        check(type(estimate_geometry) is bool, "estimate_geometry must be a boolean")
        validate_region_requests(geometry_regions, estimate_geometry)
        geometry = (
            "The caller declares each attachment is a complete single-viewport capture. "
            "Opt-in geometry estimation: for clearly identifiable regions, you may supply approximate "
            "normalized bounds ONLY in interpretations linked to that region's visible observations. "
            "Use stable neutral region names and put the bounds in the structured geometry field described below, "
            "rather than relying on numbers embedded in prose. "
            "The origin is the top-left of the complete attached image; x and width divide by image width, "
            "y and height by image height. Each value is between 0 and 1. These are approximate visual "
            "estimates, never measurements, CSS pixels, document coordinates or responsive rules. "
            "Use at most two decimal places and describe confidence, uncertain edges and rough error bounds. "
            "Estimate only visible bounds; do not reconstruct hidden or offscreen extents. Set indeterminate "
            "coordinates to null rather than guessing. If an attachment appears cropped or full-page rather than a "
            "single viewport, leave its viewport geometry unknown. Prefer major regions and alignment anchors; "
            "do not enumerate a bounding box for every repeated icon. Keep numeric geometry out of observations "
            "and measurements. Precise geometry still requires a separate trusted measurement channel. "
            "Represent each region's geometry in a layout interpretation with an additional geometry object: "
            "{region:neutral-id,coordinate_space:'viewport-ratio',bounds:{x:{value:number-or-null,uncertainty:text},"
            "y:{value:number-or-null,uncertainty:text},width:{value:number-or-null,uncertainty:text},"
            "height:{value:number-or-null,uncertainty:text}}}. Link observations from exactly one image. "
            "Each known extent must be positive, and x+width and y+height must not exceed 1. "
            "Use null with a concrete reason for each unknown bound, including absent or ambiguous regions. "
            "Include small alignment anchors such as headline blocks, wordmarks and player identity separately "
            "from their containing sections. Do not replace a requested character with its whole stage. "
            f"Requested neutral regions are {json.dumps(list(geometry_regions))}. For EVERY supplied image, "
            "return exactly one geometry interpretation for each requested region, even if all bounds are unknown. "
            "Do not omit requested regions or combine distinct slots. Never invent a visible region just to meet this list. "
        ) if estimate_geometry else (
            "do not estimate pixel dimensions, distances or numeric ratios. "
            "Obtain precise geometry through a separate measurement channel. "
        )
        preservation = (
            "Analysis intent: preserve. Supply a reconstruction inventory of what is visible, including small "
            "identity/name/level labels, floating controls and overlays; do not omit them because they seem secondary. "
            "Use stable neutral region names in statements and distinguish repeated instances from distinct types. "
            "For each identifiable region describe its location relative to neighbors, visual size relative to them, "
            "alignment, spacing, text treatment and dominant color appearance (including light/dark and hue differences). "
            "Explicitly count visible repeated controls and headline lines when unambiguous. Preserve placements of "
            "labels relative to their subjects. Say which regions are partly cropped or obscured. "
            "Do not identify the source website or transcribe its branding, usernames or slogans; describe their "
            "visual roles and line structure instead. Recommendations must not erase observed complexity or "
            "silently repair perceived weaknesses. Missing dimensions stay unknown. "
        ) if intent == "preserve" else "Analysis intent: adapt. "
        identities = [
            {
                "id": item.id,
                "kind": item.kind,
                "locator": item.locator,
                "role": "reference" if index < len(references) else "target",
            }
            for index, item in enumerate(list(references) + list(targets))
        ]
        source_ids = [item["id"] for item in identities]
        return (
            "Analyze the attached screenshots as one Visparse design profile. Return exactly one JSON object and no Markdown. "
            "Use only the supplied images; do not browse, use tools, inspect unrelated files or consult memories. "
            "Never reset usage limits, purchase allowance or switch models/providers; stop on a limit. "
            + preservation +
            f"schema_version must be {DESIGN_SCHEMA_VERSION!r}; sources must exactly equal {json.dumps(identities, ensure_ascii=False)}. "
            "Top-level keys must be schema_version, sources, measurements, observations, interpretations, confidence, principles, recommendations, provenance. "
            f"Observation and interpretation category must be one of {json.dumps(sorted(DESIGN_CATEGORIES))}. "
            "Cover layout, hierarchy, spacing and density, typography, color roles, component styling, UI patterns, section rhythm, navigation, imagery, tone, strengths, and weaknesses when visible. "
            "Describe each major visible region separately, identifying it consistently in statements. "
            "Record directly countable headline lines and repeated visible elements when unambiguous. "
            "Describe relative placement, alignment, width behavior and image composition, including text space "
            "and photographic versus illustrated media. State when a property is obscured or indeterminate. "
            "Do not replace these concrete observations with generic style adjectives. "
            "measurements must be an empty array because this VLM-only adapter has no trusted mechanical measurement channel; "
            + geometry +
            "Directly countable lines/elements belong in observations, not measurements. "
            f"observations contain id, source_ids, category, statement and only directly visible facts; observation category must be one of {json.dumps(sorted(OBSERVATION_DESIGN_CATEGORIES))}. "
            "interpretations contain id, observation_ids, category, statement, confidence_id. confidence contains id, level 0..1, uncertainty, basis. "
            "design_tone, strength, and weakness must appear only as interpretations linked to visible observations, never as observations. "
            "principles contain id, observation_ids, interpretation_ids, statement and describe reusable design logic. "
            "recommendations contain id, principle_ids, target_source_ids, action, rationale, transfer_mode='principle', and avoid_copying exactly ['assets','branding','content','implementation']. "
            "Target recommendations must adapt principles to target screenshots when supplied, or give generally applicable improvement guidance when none are supplied. "
            "When no supplied source has role target, every target_source_ids array must be empty; never use a reference source ID as a target. "
            "Never request pixel-perfect cloning, copied content, logos, branding, assets, exact DOM, exact CSS, or proprietary implementation details. "
            "Every supplied source must be cited by an observation. All IDs are globally unique and every reference resolves. "
            f"provenance must contain only created_by as a non-empty string and inputs exactly equal to {json.dumps(source_ids)}; inputs contains source ID strings, never objects."
        )


class _StaticDesignAnalyzer(DesignAnalyzer):
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile

    def analyze(self, references: Sequence[SourceEvidence], targets: Sequence[SourceEvidence] = ()) -> dict[str, Any]:
        del references, targets
        return self.profile

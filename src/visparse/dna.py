"""Canonical, evidence-linked Design DNA. No model or browser execution."""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from .contracts import bounded, canonical, check, items, load_json, number, refs, shape, text, unique
from .design import validate_design_profile
from .inspection import validate_inspection
from .geometry import AXES, VISIBILITY
from .visual_details import APPEARANCE, CROP, SUBJECT_KINDS

DNA_VERSION = "0.1"
VOCABULARY_VERSION = "0.5"
DIMENSIONS = (
    "typography", "color_strategy", "spacing_geometry", "composition",
    "visual_hierarchy", "component_grammar", "imagery_grammar", "responsive",
    "semantic_character", "motion",
)
# dimension, type/unit, controlled values, absolute comparison tolerance
FEATURES = {
    "typography.font_size": ("typography", "px", None, 1.0),
    "typography.font_family": ("typography", "text", None, 0),
    "typography.font_weight": ("typography", "number", None, 100),
    "typography.line_height": ("typography", "px", None, 1.0),
    "typography.letter_spacing": ("typography", "px", None, 0.2),
    "typography.scale_ratio": ("typography", "ratio", None, 0.1),
    "color.foreground": ("color_strategy", "text", None, 0),
    "color.background": ("color_strategy", "text", None, 0),
    "color.accent_usage": ("color_strategy", "enum", ["actions", "decorative", "mixed"], 0),
    "geometry.width": ("spacing_geometry", "px", None, 8),
    "geometry.height": ("spacing_geometry", "px", None, 8),
    "geometry.radius": ("spacing_geometry", "px", None, 1),
    "spacing.gap": ("spacing_geometry", "px", None, 2),
    "spacing.density": ("spacing_geometry", "enum", ["sparse", "balanced", "dense"], 0),
    "surface.shadow_usage": ("component_grammar", "ratio", None, 0.05),
    "surface.border_usage": ("component_grammar", "ratio", None, 0.05),
    "layout.display": ("composition", "text", None, 0),
    "layout.alignment": ("composition", "enum", ["left", "center", "right", "mixed"], 0),
    "layout.hero_pattern": ("composition", "enum", ["centered", "split", "asymmetric", "stacked"], 0),
    "hierarchy.emphasis": ("visual_hierarchy", "enum", ["scale", "color", "space", "position", "mixed"], 0),
    "component.card_usage": ("component_grammar", "enum", ["low", "medium", "high"], 0),
    "component.grouping": ("component_grammar", "enum", ["spacing", "borders", "cards", "mixed"], 0),
    "imagery.treatment": ("imagery_grammar", "enum", ["contained", "edge-to-edge", "mixed", "absent"], 0),
    "imagery.kind": ("imagery_grammar", "enum", ["photography", "illustration", "product-ui", "mixed", "absent"], 0),
    "responsive.transformation": ("responsive", "enum", ["stack", "drawer", "carousel", "full-screen", "unchanged"], 0),
    "character.tone": ("semantic_character", "enum", ["restrained", "expressive", "editorial", "utilitarian", "technical", "calm", "bold"], 0),
    "motion.preference": ("motion", "enum", ["none-observed", "subtle", "expressive"], 0),
}
LEGACY_FEATURES = frozenset(FEATURES)
FEATURES.update({
    "typography.text_treatment": ("typography", "enum", ["plain", "outline", "shadow", "outline-and-shadow"], 0),
    "color.family": ("color_strategy", "enum", ["white", "black", "gray", "blue", "lavender", "purple", "red", "orange", "yellow", "green", "cyan", "brown", "mixed"], 0),
    "color.saturation": ("color_strategy", "enum", ["muted", "moderate", "vivid", "mixed"], 0),
})
V2_FEATURES = frozenset(FEATURES)
FEATURES.update({
    "typography.line_count": ("typography", "count", None, 0),
    "typography.width_style": ("typography", "enum", ["condensed", "normal", "wide"], 0),
    "layout.relative_position": ("composition", "enum", ["above", "below", "left-of", "right-of", "aligned-left", "aligned-right", "aligned-center", "contains", "overlaps"], 0),
    "geometry.width_mode": ("spacing_geometry", "enum", ["fill-parent", "intrinsic", "fixed", "proportional"], 0),
    "geometry.viewport_width_ratio": ("spacing_geometry", "ratio", None, 0.02),
    "geometry.viewport_height_ratio": ("spacing_geometry", "ratio", None, 0.02),
    "geometry.viewport_x_ratio": ("spacing_geometry", "ratio", None, 0.02),
    "geometry.viewport_y_ratio": ("spacing_geometry", "ratio", None, 0.02),
    "image.width": ("spacing_geometry", "image-px", None, 2),
    "image.height": ("spacing_geometry", "image-px", None, 2),
    "component.visible_count": ("component_grammar", "count", None, 0),
    "color.foreground_hex": ("color_strategy", "color", None, 0),
    "color.background_hex": ("color_strategy", "color", None, 0),
    "color.accent_hex": ("color_strategy", "color", None, 0),
})
V3_FEATURES = frozenset(FEATURES)
FEATURES.update({
    "imagery.prominence": ("imagery_grammar", "enum", ["low", "medium", "high"], 0),
    "imagery.framing": ("imagery_grammar", "enum", ["close-up", "medium", "wide", "mixed"], 0),
    "imagery.text_space": ("imagery_grammar", "enum", ["left", "right", "above", "below", "none", "mixed"], 0),
    "imagery.subject_arrangement": ("imagery_grammar", "enum", ["left", "center", "right", "distributed", "mixed"], 0),
})
V4_FEATURES = frozenset(FEATURES)
FEATURES.update({
    "geometry.visibility": ("spacing_geometry", "enum", VISIBILITY, 0),
    "typography.letter_spacing_em": ("typography", "em", None, 0.02),
    "typography.line_height_factor": ("typography", "ratio", None, 0.1),
    "typography.text_layout": ("typography", "enum", ["single-block", "multiple-blocks", "non-text"], 0),
    "imagery.composition_coverage": ("imagery_grammar", "enum", ["complete", "partial"], 0),
    "imagery.subject_visibility": ("imagery_grammar", "enum", VISIBILITY, 0),
    "imagery.subject_crop": ("imagery_grammar", "enum", CROP, 0),
    "imagery.subject_kind": ("imagery_grammar", "enum", SUBJECT_KINDS, 0),
})
for axis in AXES:
    FEATURES[f"geometry.full_viewport_{axis}_ratio"] = ("spacing_geometry", "ratio", None, 0.02)
    FEATURES[f"imagery.subject_{axis}_ratio"] = ("imagery_grammar", "ratio", None, 0.02)
MEDIA_RELATIONS = frozenset(name for name in FEATURES if name.startswith("imagery.subject_")
                            and name != "imagery.subject_arrangement")
RANK = {"measured": 0, "observed": 1, "inferred": 2}
DEFAULT_SCOPE = {"viewport": "unspecified", "state": "default", "subject": "page"}


def validate_scope(scope: Any) -> dict:
    shape(scope, {"viewport", "state", "subject"})
    for value in scope.values():
        text(value)
    return scope


def feature_key(feature: dict) -> str:
    parts = [feature["name"], feature["scope"]]
    if "relative_to" in feature:
        parts.append(feature["relative_to"])
        if feature["name"] == "layout.relative_position":
            relation = feature["value"]
            axis = {"above": "vertical", "below": "vertical", "left-of": "horizontal", "right-of": "horizontal"}.get(relation, relation)
            parts.append(axis)
    return canonical(parts).strip()


def validate_unit(name: str, unit: Any) -> None:
    check(name in FEATURES, f"unsupported feature: {name}")
    kind = FEATURES[name][1]
    expected_unit = None if kind in {"text", "enum", "number", "color", "count"} else kind
    check(unit == expected_unit, f"{name}: expected unit {expected_unit}")


def validate_value(name: str, value: Any, unit: Any) -> None:
    validate_unit(name, unit)
    _, kind, choices, _ = FEATURES[name]
    if kind == "color":
        check(isinstance(value, str) and re.fullmatch(r"#[0-9a-f]{6}", value) is not None, "expected lowercase six-digit hex color")
    elif kind in {"enum", "text"}:
        text(value)
        check(choices is None or value in choices, f"{name}: unsupported category")
    else:
        number(value)
        if name not in {"typography.letter_spacing", "typography.letter_spacing_em",
                        "geometry.full_viewport_x_ratio", "geometry.full_viewport_y_ratio"}:
            check(value >= 0, f"{name}: negative value")
        if kind == "count":
            check(type(value) is int and value >= 1, "expected positive integer count")
        if name.startswith("geometry.viewport_"):
            check(value <= 1, "expected viewport fraction")
        if name.startswith("imagery.subject_") and kind == "ratio":
            number(value, 0, 1)
        if name == "typography.line_height_factor":
            check(value > 0, "line height factor must be positive")
        if name in {"surface.shadow_usage", "surface.border_usage"}:
            check(value <= 1, f"{name}: expected fraction")


def validate_dna(dna: Any) -> dict:
    bounded(dna)
    shape(dna, {"schema_version", "vocabulary_version", "sources", "evidence", "features", "principles", "gaps", "provenance"})
    check(dna["schema_version"] == DNA_VERSION and dna["vocabulary_version"] in {"0.1", "0.2", "0.3", "0.4", VOCABULARY_VERSION},
          "unsupported DNA schema/vocabulary version")
    sources = unique(dna["sources"])
    for source in sources.values():
        shape(source, {"id", "kind", "locator", "role"})
        check(source["role"] == "reference", "DNA only accepts reference sources")
        text(source["kind"])
        text(source["locator"])
    evidence = unique(dna["evidence"])
    for item in evidence.values():
        shape(item, {"id", "source_ids", "kind", "statement", "confidence", "scope", "details"})
        refs(item["source_ids"], sources)
        check(item["kind"] in RANK, "invalid evidence kind")
        text(item["statement"])
        validate_scope(item["scope"])
        check(isinstance(item["details"], dict), "expected evidence details")
        if item["confidence"] is not None:
            number(item["confidence"], 0, 1)
        if item["kind"] == "inferred":
            check(item["confidence"] is not None, "inference requires confidence")
    features = unique(dna["features"])
    principles = unique(dna["principles"])
    all_ids = list(sources) + list(evidence) + list(features) + list(principles)
    check(len(set(all_ids)) == len(all_ids), "IDs must be globally unique")
    for feature in features.values():
        shape(feature, {"id", "name", "value", "unit", "status", "origin", "confidence", "scope", "evidence_ids", "method"}, {"uncertainty", "relative_to"})
        validate_scope(feature["scope"])
        check(feature["name"] in FEATURES, "unsupported feature")
        check(dna["vocabulary_version"] != "0.1" or feature["name"] in LEGACY_FEATURES, "feature requires vocabulary 0.2")
        check(dna["vocabulary_version"] != "0.2" or feature["name"] in V2_FEATURES, "feature requires vocabulary 0.3")
        check(dna["vocabulary_version"] != "0.3" or feature["name"] in V3_FEATURES, "feature requires vocabulary 0.4")
        check(dna["vocabulary_version"] != "0.4" or feature["name"] in V4_FEATURES, "feature requires vocabulary 0.5")
        if feature["name"] == "layout.relative_position" or feature["name"] in MEDIA_RELATIONS:
            text(feature.get("relative_to"))
            check(feature["relative_to"] != feature["scope"]["subject"], "self relationship")
            check(any(e["scope"] == {**feature["scope"], "subject": feature["relative_to"]} for e in evidence.values()), "relationship target missing in same viewport/state")
        else:
            check("relative_to" not in feature, "relative_to requires relationship feature")
        if "uncertainty" in feature:
            text(feature["uncertainty"])
        check(feature["status"] in {"known", "unknown", "not_applicable"}, "invalid feature status")
        check(feature["origin"] in RANK, "invalid feature origin")
        text(feature["method"])
        validate_scope(feature["scope"])
        refs(feature["evidence_ids"], evidence, nonempty=feature["status"] == "known")
        if feature["confidence"] is not None:
            number(feature["confidence"], 0, 1)
        if feature["origin"] == "inferred" and feature["status"] == "known":
            check(feature["confidence"] is not None, "inferred feature requires confidence")
        for ref in feature["evidence_ids"]:
            check(RANK[feature["origin"]] >= RANK[evidence[ref]["kind"]], "cannot promote inference to observation/measurement")
            check(feature["scope"] == evidence[ref]["scope"], "feature/evidence scope mismatch")
            if evidence[ref]["kind"] == "inferred" and feature["status"] == "known":
                check(feature["confidence"] <= evidence[ref]["confidence"], "feature confidence exceeds supporting inference")
        if feature["status"] == "known":
            validate_value(feature["name"], feature["value"], feature["unit"])
            if feature["origin"] == "measured" and FEATURES[feature["name"]][1] != "color":
                number(feature["value"])
        else:
            check(feature["value"] is None, "unknown/not-applicable value must be null")
            validate_unit(feature["name"], feature["unit"])
    for principle in principles.values():
        shape(principle, {"id", "statement", "evidence_ids", "confidence", "strength", "scope", "basis"})
        text(principle["statement"])
        refs(principle["evidence_ids"], evidence)
        validate_scope(principle["scope"])
        if principle["confidence"] is not None:
            number(principle["confidence"], 0, 1)
        check(principle["strength"] in {"SHOULD", "MAY", "MUST", "NEVER"}, "invalid constraint strength")
        check(principle["basis"] in {"inferred", "explicit_policy"}, "invalid principle basis")
        if principle["strength"] in {"MUST", "NEVER"}:
            check(principle["basis"] == "explicit_policy", "hard constraints require explicit policy")
        for ref in principle["evidence_ids"]:
            check(principle["scope"] == evidence[ref]["scope"], "principle/evidence scope mismatch")
            if principle["basis"] == "inferred" and evidence[ref]["kind"] == "inferred":
                check(principle["confidence"] is None or principle["confidence"] <= evidence[ref]["confidence"], "principle confidence exceeds supporting inference")
    for gap in items(dna["gaps"]):
        text(gap)
    shape(dna["provenance"], {"created_by", "inputs"})
    text(dna["provenance"]["created_by"])
    refs(dna["provenance"]["inputs"], sources, nonempty=False)
    check(set(dna["provenance"]["inputs"]) == set(sources), "provenance must cover sources")
    return dna


def load_dna(payload: bytes | str) -> dict:
    return validate_dna(load_json(payload))


def normalize_dna(dna: dict) -> str:
    return canonical(validate_dna(dna))


def feature_groups(dna: dict) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for feature in dna["features"]:
        groups[feature_key(feature)].append(feature)
    return dict(groups)


def group_status(features: list[dict], threshold: float) -> str:
    if not features:
        return "missing"
    statuses = {f["status"] for f in features}
    if len(statuses) > 1:
        return "conflict"
    if statuses != {"known"}:
        return features[0]["status"]
    if len({canonical([f["value"], f["unit"]]) for f in features}) > 1:
        return "conflict"
    if any(f["origin"] == "inferred" and f["confidence"] < threshold for f in features):
        return "low_confidence"
    return "known"


def _project_visual_detail(dna: dict, kind: str, detail: dict, evidence: dict) -> None:
    """Project validated estimates without asking a second model to reinterpret them."""
    def emit(name, estimate, source=evidence, relative_to=None):
        spec = FEATURES[name]
        unit = None if spec[1] in {"text", "enum", "number", "color", "count"} else spec[1]
        feature = {
            "id": f"feature:{len(dna['features']) + 1}", "name": name,
            "value": estimate["value"], "unit": unit,
            "status": "unknown" if estimate["value"] is None else "known", "origin": "inferred",
            "confidence": source["confidence"], "scope": copy.deepcopy(source["scope"]),
            "evidence_ids": [source["id"]],
            "method": "Direct projection of a qualified visual estimate; not a mechanical measurement.",
            "uncertainty": estimate["uncertainty"] + " " + source["details"]["confidence_assessment"]["uncertainty"],
        }
        if relative_to is not None:
            feature["relative_to"] = relative_to
        dna["features"].append(feature)

    if kind == "geometry":
        for field, prefix in (("bounds", "geometry.viewport_"), ("full_bounds", "geometry.full_viewport_")):
            for axis, bound in detail.get(field, {}).items():
                emit(f"{prefix}{axis}_ratio", bound)
        if "visibility" in detail:
            emit("geometry.visibility", detail["visibility"])
    elif kind == "appearance":
        for field, estimate in detail["properties"].items():
            emit(APPEARANCE[field][0], estimate)
    else:
        emit("imagery.composition_coverage", detail["coverage"])
        for subject in detail["subjects"]:
            child = copy.deepcopy(evidence)
            child["id"] = evidence["id"] + ":subject:" + subject["region"]
            child["scope"]["subject"] = "media/" + detail["region"] + "/" + subject["region"]
            child["statement"] = "Qualified media-local composition for " + subject["region"]
            child["details"] = {"parent_evidence_id": evidence["id"], "coordinate_space": "media-ratio",
                                "media_region": detail["region"], "subject": copy.deepcopy(subject),
                                "confidence_assessment": copy.deepcopy(evidence["details"]["confidence_assessment"])}
            dna["evidence"].append(child)
            for axis, bound in subject["bounds"].items():
                emit(f"imagery.subject_{axis}_ratio", bound, child, detail["region"])
            emit("imagery.subject_visibility", subject["visibility"], child, detail["region"])
            emit("imagery.subject_crop", subject["crop"], child, detail["region"])
            emit("imagery.subject_kind", subject["kind"], child, detail["region"])


def build_dna(profile: dict | None = None, *, inspection: dict | None = None,
              annotations: dict | None = None, contexts: dict | None = None) -> dict:
    """Project known measurements; preserve prose; apply explicitly inferred annotations.

    Context keys are namespaced source/evidence IDs (``profile:ID``). Collector
    evidence provides its own context. Annotations never become measurements.
    """
    contexts = contexts or {}
    bounded(contexts)
    check(isinstance(contexts, dict), "contexts must be an object")
    for scope in contexts.values():
        validate_scope(scope)
    dna = {"schema_version": DNA_VERSION, "vocabulary_version": VOCABULARY_VERSION,
           "sources": [], "evidence": [], "features": [], "principles": [], "gaps": [],
           "provenance": {"created_by": "visparse-design-normalize/0.1", "inputs": []}}

    def add_feature(name, value, unit, origin, eid, scope, method, confidence=None):
        dna["features"].append({"id": f"feature:{len(dna['features']) + 1}", "name": name,
                                "value": value, "unit": unit, "status": "known", "origin": origin,
                                "confidence": confidence, "scope": copy.deepcopy(scope),
                                "evidence_ids": [eid], "method": method})

    if profile is not None:
        validate_design_profile(profile)
        context_ids = {"profile:" + item["id"] for field in ("sources", "measurements", "observations", "interpretations") for item in profile[field]}
        check(contexts.keys() <= context_ids, "unknown profile context ID")
        source_map = {s["id"]: s for s in profile["sources"]}
        allowed = {sid for sid, s in source_map.items() if s["role"] == "reference"}
        dna["sources"].extend({**s, "id": "profile:" + s["id"]} for s in profile["sources"] if s["id"] in allowed)
        confidence_records = {c["id"]: c for c in profile["confidence"]}
        confidence = {cid: c["level"] for cid, c in confidence_records.items()}
        observations = {o["id"]: o for o in profile["observations"]}
        interpretations = {i["id"]: i for i in profile["interpretations"]}
        eligible = {}
        for kind, records in (("measured", profile["measurements"]), ("observed", profile["observations"]), ("inferred", profile["interpretations"])):
            for record in records:
                if kind == "measured":
                    source_ids = [record["source_id"]]
                elif kind == "observed":
                    source_ids = record["source_ids"]
                else:
                    source_ids = sorted({s for oid in record["observation_ids"] for s in observations[oid]["source_ids"]})
                if not set(source_ids) <= allowed:
                    dna["gaps"].append(f"Excluded target or mixed-source claim: {record['id']}")
                    continue
                eid = "profile:" + record["id"]
                source_scopes = [contexts.get("profile:" + sid, DEFAULT_SCOPE) for sid in source_ids]
                if eid not in contexts and any(s != source_scopes[0] for s in source_scopes):
                    dna["gaps"].append(f"Cross-context claim needs explicit scope mapping: {eid}")
                    continue
                scope = contexts.get(eid, source_scopes[0])
                detail_kind = next((k for k in ("geometry", "appearance", "media") if k in record), None) if kind == "inferred" else None
                if detail_kind is not None:
                    detail = record[detail_kind]
                    check(scope["subject"] in ("page", detail["region"]),
                          f"{detail_kind} region conflicts with supplied context")
                    scope = {**scope, "subject": detail["region"]}
                level = confidence[record["confidence_id"]] if kind == "inferred" else None
                details = copy.deepcopy(record)
                if kind == "inferred":
                    # Confidence IDs alone do not resolve in DNA. Keep the source
                    # qualification available to downstream semantic extraction.
                    details["confidence_assessment"] = copy.deepcopy(confidence_records[record["confidence_id"]])
                dna["evidence"].append({"id": eid, "source_ids": ["profile:" + sid for sid in source_ids],
                                        "kind": kind, "statement": record.get("statement", record.get("name")),
                                        "confidence": level, "scope": copy.deepcopy(scope), "details": details})
                eligible[record["id"]] = eid
                if detail_kind is not None:
                    _project_visual_detail(dna, detail_kind, detail, dna["evidence"][-1])
                elif kind == "measured" and record["name"] in FEATURES:
                    validate_value(record["name"], record["value"], record.get("unit"))
                    add_feature(record["name"], record["value"], record.get("unit"), kind, eid, scope, record["method"])
                else:
                    dna["gaps"].append(f"Retained without semantic mapping: {eid}")
        for principle in profile["principles"]:
            ids = principle["observation_ids"] + principle["interpretation_ids"]
            if not set(ids) <= eligible.keys():
                dna["gaps"].append(f"Excluded target or mixed-source principle: {principle['id']}")
                continue
            levels = [confidence[interpretations[i]["confidence_id"]] for i in principle["interpretation_ids"]]
            scopes = [e["scope"] for e in dna["evidence"] if e["id"] in [eligible[i] for i in ids]]
            if any(s != scopes[0] for s in scopes):
                dna["gaps"].append(f"Unmapped cross-context principle: {principle['id']}")
                continue
            dna["principles"].append({"id": "principle:" + principle["id"], "statement": principle["statement"],
                                      "evidence_ids": [eligible[i] for i in ids], "confidence": min(levels) if levels else None,
                                      "strength": "SHOULD", "scope": scopes[0], "basis": "inferred"})
    if inspection is not None:
        check(profile is not None or not contexts, "collector scopes cannot be overridden by profile contexts")
        validate_inspection(inspection)
        from .collector_contract import project_collector
        projected = project_collector(inspection)
        if profile is not None:
            def artifact_identity(locator):
                return locator.split(":sha256:", 1)[1] if ":sha256:" in locator else locator
            reference_artifacts = {artifact_identity(s["locator"]) for s in dna["sources"]}
            for source in projected["sources"]:
                if source["kind"] == "screenshot":
                    check(artifact_identity(source["locator"]) in reference_artifacts,
                          "inspection screenshot does not match a supplied reference artifact")
        for field in ("sources", "evidence", "features", "gaps"):
            dna[field].extend(projected[field])
    if annotations is not None:
        bounded(annotations)
        shape(annotations, {"schema_version", "features", "constraints"})
        check(annotations["schema_version"] == "0.1", "unsupported annotation schema")
        evidence = unique(dna["evidence"])
        for annotation in items(annotations["features"]):
            shape(annotation, {"name", "value", "unit", "status", "scope", "evidence_ids", "confidence", "method"})
            refs(annotation["evidence_ids"], evidence, nonempty=annotation["status"] == "known")
            dna["features"].append({**copy.deepcopy(annotation), "id": f"annotation:{len(dna['features']) + 1}", "origin": "inferred"})
        for constraint in items(annotations["constraints"]):
            shape(constraint, {"statement", "scope", "evidence_ids", "confidence", "strength", "author"})
            text(constraint["author"])
            dna["principles"].append({"id": f"policy:{len(dna['principles']) + 1}",
                **{k: copy.deepcopy(v) for k, v in constraint.items() if k != "author"}, "basis": "explicit_policy"})
            dna["gaps"].append(f"Explicit transfer policy supplied by {constraint['author']}; not a measured source rule.")
    check(profile is not None or inspection is not None, "supply a profile or inspection")
    dna["provenance"]["inputs"] = sorted(s["id"] for s in dna["sources"])
    for field in ("sources", "evidence", "features", "principles"):
        dna[field].sort(key=lambda item: item["id"])
    dna["gaps"] = sorted(set(dna["gaps"]))
    return validate_dna(dna)

"""Versioned collector payload validation and deterministic feature projection."""

from __future__ import annotations

import re
import statistics

from .contracts import bounded, check, items, number, shape, text, unique
from .dna import validate_scope

CSS_FEATURES = {
    "font-size": ("typography.font_size", "px"),
    "font-family": ("typography.font_family", None),
    "font-weight": ("typography.font_weight", None),
    "line-height": ("typography.line_height", "px"),
    "letter-spacing": ("typography.letter_spacing", "px"),
    "color": ("color.foreground", None), "background-color": ("color.background", None),
    "border-top-left-radius": ("geometry.radius", "px"),
    "gap": ("spacing.gap", "px"), "display": ("layout.display", None),
}
TEXT_CSS = {"font-family", "color", "background-color", "display"}


def validate_capture_payload(payload: dict) -> dict:
    bounded(payload)
    shape(payload, {"collector_schema_version", "context", "nodes", "coverage", "metadata", "css_variables"})
    check(payload["collector_schema_version"] == "0.1", "unsupported collector payload version")
    shape(payload["context"], {"session_id", "viewport", "state", "scroll_x", "scroll_y", "device_pixel_ratio", "screenshot_id"})
    for key in ("session_id", "viewport", "state", "screenshot_id"):
        text(payload["context"][key])
    for key in ("scroll_x", "scroll_y", "device_pixel_ratio"):
        number(payload["context"][key])
    nodes = unique(payload["nodes"])
    for node in nodes.values():
        shape(node, {"id", "parent_id", "tag", "text", "attributes", "box", "styles"})
        text(node["tag"])
        check(isinstance(node["text"], str), "invalid text summary")
        check(node["parent_id"] is None or node["parent_id"] in nodes, "unknown parent node")
        shape(node["box"], {"x", "y", "width", "height"})
        for key, value in node["box"].items():
            number(value, 0 if key in {"width", "height"} else None)
        for key in ("attributes", "styles"):
            check(isinstance(node[key], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in node[key].items()), "invalid node strings")
    shape(payload["coverage"], {"scanned", "captured", "truncated", "omissions"})
    number(payload["coverage"]["scanned"], 0)
    check(payload["coverage"]["captured"] == len(nodes), "capture count mismatch")
    check(isinstance(payload["coverage"]["truncated"], bool), "invalid truncation flag")
    for omission in items(payload["coverage"]["omissions"]):
        text(omission)
    check(isinstance(payload["metadata"], dict), "invalid capture metadata")
    check(isinstance(payload["css_variables"], dict), "invalid CSS variables")
    return payload


def _numeric_css(value: str, unit: str | None) -> float | None:
    pattern = r"(-?(?:\d+(?:\.\d*)?|\.\d+))" + ("px" if unit == "px" else "")
    match = re.fullmatch(pattern, value)
    return float(match[1]) if match else None


def project_collector(bundle: dict) -> dict:
    result = {"sources": [], "evidence": [], "features": [], "gaps": []}
    captures = unique(bundle["captures"])
    for capture in bundle["captures"]:
        if capture["kind"] != "dom" or not isinstance(capture["payload"], dict) or "collector_schema_version" not in capture["payload"]:
            continue
        payload = validate_capture_payload(capture["payload"])
        context = payload["context"]
        shot = captures.get(context["screenshot_id"])
        check(shot is not None and shot["kind"] == "screenshot", "collector screenshot link missing")
        check(shot["payload"].get("session_id") == context["session_id"] and shot["payload"].get("viewport") == context["viewport"], "collector artifact context mismatch")
        sid = "capture:" + capture["id"]
        shot_sid = "capture:" + shot["id"]
        for source, source_id in ((capture, sid), (shot, shot_sid)):
            if not any(s["id"] == source_id for s in result["sources"]):
                result["sources"].append({"id": source_id, "kind": source["kind"], "locator": source["locator"], "role": "reference"})
        coverage = payload["coverage"]
        for omission in coverage["omissions"]:
            result["gaps"].append(f"{sid}: {omission}")
        if coverage["truncated"]:
            result["gaps"].append(f"{sid}: truncated visible-node sample; {coverage['captured']} captured of {coverage['scanned']} scanned")

        def add(name, value, unit, scope, details, method):
            eid = f"{sid}:e{len(result['evidence']) + 1}"
            origin = "observed" if isinstance(value, str) else "measured"
            result["evidence"].append({"id": eid, "source_ids": [sid, shot_sid], "kind": origin,
                "statement": f"{name} = {value}", "confidence": None, "scope": scope,
                "details": {"method": method, "value": value, "unit": unit, **details}})
            result["features"].append({"id": eid + ":feature", "name": name, "value": value, "unit": unit,
                "status": "known", "origin": origin, "confidence": None, "scope": scope,
                "evidence_ids": [eid], "method": method})

        # Tag aggregates are explicitly scoped to the captured sample, never to
        # the whole site. This makes cross-site comparison independent of node IDs.
        tags = sorted({n["tag"] for n in payload["nodes"]})
        for tag in tags:
            nodes = [n for n in payload["nodes"] if n["tag"] == tag]
            scope = {"viewport": context["viewport"], "state": context["state"], "subject": f"visible-sample:tag={tag}"}
            validate_scope(scope)
            details = {"node_ids": [n["id"] for n in nodes], "sample_count": len(nodes), "coverage": coverage}
            for css, (name, unit) in CSS_FEATURES.items():
                values = [n["styles"].get(css) for n in nodes]
                if any(v is None for v in values):
                    continue
                if css in TEXT_CSS:
                    if len(set(values)) == 1:
                        add(name, values[0], unit, scope, details, "unanimous computed CSS in captured tag sample")
                    else:
                        result["gaps"].append(f"{sid}: heterogeneous {css} for tag {tag}; no single value projected")
                else:
                    parsed = [_numeric_css(v, unit) for v in values]
                    if all(v is not None for v in parsed):
                        add(name, statistics.median(parsed), unit, scope, details, "median computed CSS in captured tag sample")
            for axis in ("width", "height"):
                add("geometry." + axis, statistics.median(n["box"][axis] for n in nodes), "px", scope, details,
                    "median getBoundingClientRect CSS pixels in captured tag sample")
            shadows = [n["styles"].get("box-shadow") for n in nodes]
            if all(s is not None for s in shadows):
                add("surface.shadow_usage", sum(s != "none" for s in shadows) / len(nodes), "ratio", scope, details,
                    "fraction of captured tag sample with computed box-shadow other than none")
            borders = [[_numeric_css(n["styles"].get("border-" + edge + "-width", ""), "px") for edge in ("top", "right", "bottom", "left")] for n in nodes]
            if all(all(v is not None for v in row) for row in borders):
                add("surface.border_usage", sum(any(v > 0 for v in row) for row in borders) / len(nodes), "ratio", scope, details,
                    "fraction of captured tag sample with any positive computed border width")
    if not result["sources"]:
        result["gaps"].append("No supported collector payloads; generic inspection evidence was not semantically guessed.")
    return result

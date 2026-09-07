"""Synthetic, redistribution-safe evidence for the design workflow tests."""

import copy

from visparse.dna import DEFAULT_SCOPE, validate_dna


def dna():
    scope = dict(DEFAULT_SCOPE)
    return validate_dna({
        "schema_version": "0.1", "vocabulary_version": "0.1",
        "sources": [{"id": "source", "kind": "css", "locator": "synthetic:reference", "role": "reference"}],
        "evidence": [
            {"id": "font", "source_ids": ["source"], "kind": "measured", "statement": "font size is 32 CSS px", "confidence": None,
             "scope": scope, "details": {"method": "synthetic CSS fixture", "value": 32, "unit": "px"}},
            {"id": "layout", "source_ids": ["source"], "kind": "inferred", "statement": "hero appears asymmetric", "confidence": 0.8,
             "scope": scope, "details": {"basis": "synthetic expert interpretation"}},
        ],
        "features": [
            {"id": "font-feature", "name": "typography.font_size", "value": 32, "unit": "px", "status": "known", "origin": "measured",
             "confidence": None, "scope": scope, "evidence_ids": ["font"], "method": "synthetic CSS fixture"},
            {"id": "layout-feature", "name": "layout.hero_pattern", "value": "asymmetric", "unit": None, "status": "known", "origin": "inferred",
             "confidence": 0.8, "scope": scope, "evidence_ids": ["layout"], "method": "explicit synthetic annotation"},
        ],
        "principles": [{"id": "principle", "statement": "Use asymmetric balance around the main content.", "evidence_ids": ["layout"],
            "confidence": 0.8, "strength": "SHOULD", "scope": scope, "basis": "inferred"}],
        "gaps": ["Synthetic fixture; not a live model benchmark."],
        "provenance": {"created_by": "synthetic-fixture", "inputs": ["source"]},
    })


def analysis_fixture():
    value = dna()
    expected = [
        {"id": "font", "name": "typography.font_size", "scope": dict(DEFAULT_SCOPE), "unit": "px", "kind": "grounding", "tolerance": 1, "annotations": []},
        {"id": "hero", "name": "layout.hero_pattern", "scope": dict(DEFAULT_SCOPE), "unit": None, "kind": "interpretive", "tolerance": 0,
            "annotations": [{"annotator": "synthetic-designer-a", "value": "asymmetric"}, {"annotator": "synthetic-designer-b", "value": "split"}]},
    ]
    claims = [{"expected_id": "font", "name": "typography.font_size", "scope": dict(DEFAULT_SCOPE), "value": 32, "unit": "px", "confidence": 0.9, "evidence_ids": ["font"]},
              {"expected_id": "hero", "name": "layout.hero_pattern", "scope": dict(DEFAULT_SCOPE), "value": "asymmetric", "unit": None, "confidence": 0.6, "evidence_ids": ["layout"]}]
    config = {"model_version": "synthetic-1", "prompt_version": "fixture-1", "input_protocol": "same synthetic evidence", "parameters": {}}
    bad = copy.deepcopy(claims)
    bad[0]["value"] = 64
    bad[0]["confidence"] = 0.9
    return {"schema_version": "0.1", "items": [{"id": "synthetic-page", "evidence": value, "expected": expected,
        "provenance": "Hand-authored synthetic evidence and labels; no live provider or expert study."}],
        "predictions": [{"model": "synthetic-supported", "configuration": config, "cases": [{"item_id": "synthetic-page", "claims": claims}]},
                        {"model": "synthetic-contradicted", "configuration": config, "cases": [{"item_id": "synthetic-page", "claims": bad}]}]}


def collector_bundle():
    return {"schema_version": "0.1", "captures": [
        {"id": "shot", "kind": "screenshot", "locator": "synthetic:shot", "payload": {"session_id": "session", "viewport": "1440x900"}},
        {"id": "dom", "kind": "dom", "locator": "synthetic:dom", "payload": {
            "collector_schema_version": "0.1", "context": {"session_id": "session", "viewport": "1440x900", "state": "default", "scroll_x": 0,
                "scroll_y": 0, "device_pixel_ratio": 1, "screenshot_id": "shot"},
            "nodes": [{"id": "h1", "parent_id": None, "tag": "h1", "text": "Synthetic title", "attributes": {},
                "box": {"x": 20, "y": 30, "width": 640, "height": 70}, "styles": {"font-family": "sans-serif", "font-size": "32px",
                    "font-weight": "700", "line-height": "40px", "letter-spacing": "-0.5px", "gap": "normal", "box-shadow": "none",
                    "border-top-width": "1px", "border-bottom-width": "0px", "border-left-width": "0px", "border-right-width": "0px"}}],
            "coverage": {"scanned": 1, "captured": 1, "truncated": False, "omissions": ["Synthetic visible sample."]}, "metadata": {}, "css_variables": {}}}],
        "measurements": [], "runtime_observations": [], "visual_observations": [], "interpretations": [], "confidence": [],
        "provenance": {"created_by": "synthetic-collector", "inputs": ["shot", "dom"]}}

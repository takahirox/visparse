from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse import (  # noqa: E402
    CAPTURE_KINDS,
    ValidationError,
    inspect_snapshot,
    inspection_capabilities,
    load_inspection,
    normalize_inspection,
    summarize_inspection,
    validate_inspection,
)
from visparse.cli import main  # noqa: E402


def bundle() -> dict:
    captures = [
        {"id": "dom", "kind": "dom", "locator": "document",
         "payload": {"node_count": 12, "html": "<main>...</main>"}},
        {"id": "css", "kind": "css", "locator": "computed:#hero",
         "payload": {"display": "grid", "gap": "16px"}},
        {"id": "a11y", "kind": "accessibility", "locator": "accessibility-tree",
         "payload": {"role": "main", "children": []}},
        {"id": "runtime", "kind": "runtime", "locator": "performance",
         "payload": {"console": [], "duration_ms": 18.2}},
        {"id": "shot", "kind": "screenshot", "locator": "capture://frame-1",
         "payload": {"sha256": "abc", "width": 800, "height": 600}},
        {"id": "video", "kind": "video", "locator": "capture://interaction-1",
         "payload": {"sha256": "def", "duration_ms": 1200, "frames": 36}},
        {"id": "canvas", "kind": "canvas", "locator": "canvas#scene",
         "payload": {"width": 800, "height": 600}},
        {"id": "webgl", "kind": "webgl", "locator": "canvas#scene:webgl2",
         "payload": {"renderer": "example", "draw_calls": 4}},
        {"id": "scene", "kind": "threejs", "locator": "scene:root",
         "payload": {"objects": 7, "cameras": 1, "lights": 2}},
    ]
    return {
        "schema_version": "0.1",
        "captures": captures,
        "measurements": [{
            "id": "m-width", "source_id": "canvas", "name": "drawing buffer width",
            "value": 800, "unit": "px", "method": "canvas.width property read",
        }],
        "runtime_observations": [{
            "id": "r-grid", "source_ids": ["dom", "css"],
            "statement": "The inspected main element has computed display grid.",
        }, {
            "id": "r-scene", "source_ids": ["scene"],
            "statement": "The supplied scene snapshot reports seven objects.",
        }],
        "visual_observations": [{
            "id": "v-frame", "source_ids": ["shot"],
            "statement": "The captured frame visibly contains a centered panel.",
        }],
        "interpretations": [{
            "id": "i-focus", "evidence_ids": ["r-grid", "v-frame", "m-width"],
            "statement": "The layout may be intended to focus attention on the panel.",
            "confidence_id": "c-focus",
        }],
        "confidence": [{
            "id": "c-focus", "level": 0.7,
            "uncertainty": "Intent cannot be established from captures.",
            "basis": "The interpretation combines runtime, visual, and exact evidence.",
        }],
        "provenance": {
            "created_by": "test-agent",
            "inputs": [item["id"] for item in captures],
        },
    }


class InspectionTests(unittest.TestCase):
    def test_valid_bundle_keeps_layers_distinct_and_reports_threejs(self) -> None:
        value = bundle()
        self.assertIs(validate_inspection(value), value)
        self.assertIs(inspect_snapshot(value), value)
        summary = summarize_inspection(value)
        self.assertEqual(summary["counts"]["measurements"], 1)
        self.assertEqual(summary["counts"]["runtime_observations"], 2)
        self.assertEqual(summary["counts"]["visual_observations"], 1)
        self.assertEqual(
            summary["threejs_evidence"],
            {"status": "high_level", "source_ids": ["scene"]},
        )
        self.assertEqual(set(summary["capture_kinds"]), CAPTURE_KINDS)

    def test_canonical_loader_and_duplicate_key_rejection(self) -> None:
        canonical = normalize_inspection(bundle())
        self.assertEqual(normalize_inspection(load_inspection(canonical)), canonical)
        self.assertTrue(canonical.endswith("\n"))
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            load_inspection('{"schema_version":"0.1","schema_version":"0.1"}')

    def test_threejs_detection_requires_explicit_runtime_metadata(self) -> None:
        value = bundle()
        value["captures"] = [{
            "id": "gl", "kind": "webgl", "locator": "canvas:webgl",
            "payload": {"renderer": {"library": "Three.js"}},
        }]
        value["measurements"] = []
        value["runtime_observations"] = []
        value["visual_observations"] = []
        value["interpretations"] = []
        value["confidence"] = []
        value["provenance"]["inputs"] = ["gl"]
        self.assertEqual(
            summarize_inspection(value)["threejs_evidence"],
            {"status": "detected", "source_ids": ["gl"]},
        )
        value["captures"][0]["payload"] = {"page_text": "three.js"}
        self.assertEqual(
            summarize_inspection(value)["threejs_evidence"],
            {"status": "not_available", "source_ids": []},
        )

    def test_observation_layers_require_compatible_capture_evidence(self) -> None:
        runtime_from_image = bundle()
        runtime_from_image["runtime_observations"][0]["source_ids"] = ["shot"]
        with self.assertRaisesRegex(ValidationError, "runtime capture"):
            validate_inspection(runtime_from_image)

        visual_from_dom = bundle()
        visual_from_dom["visual_observations"][0]["source_ids"] = ["dom"]
        with self.assertRaisesRegex(ValidationError, "visual capture"):
            validate_inspection(visual_from_dom)

    def test_measurements_must_be_exact_finite_numbers(self) -> None:
        for value in ("about 800", True):
            invalid = bundle()
            invalid["measurements"][0]["value"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "finite numeric exact"):
                    validate_inspection(invalid)

        invalid = bundle()
        invalid["measurements"][0]["value"] = float("inf")
        with self.assertRaisesRegex(ValidationError, "non-finite numbers are not JSON"):
            validate_inspection(invalid)

    def test_interpretations_cite_evidence_not_raw_captures(self) -> None:
        invalid = bundle()
        invalid["interpretations"][0]["evidence_ids"] = ["shot"]
        with self.assertRaisesRegex(ValidationError, "unknown reference"):
            validate_inspection(invalid)

    def test_strict_shapes_references_and_provenance(self) -> None:
        extra = bundle()
        extra["captures"][0]["browser_handle"] = "not accepted"
        with self.assertRaisesRegex(ValidationError, "unknown fields"):
            validate_inspection(extra)

        duplicate = bundle()
        duplicate["visual_observations"][0]["id"] = "m-width"
        with self.assertRaisesRegex(ValidationError, "duplicate id"):
            validate_inspection(duplicate)

        missing_input = bundle()
        missing_input["provenance"]["inputs"].pop()
        with self.assertRaisesRegex(ValidationError, "every supplied capture"):
            validate_inspection(missing_input)

    def test_capabilities_are_model_independent_and_disclaim_automation(self) -> None:
        capabilities = inspection_capabilities()
        self.assertFalse(capabilities["browser_automation"])
        self.assertEqual(capabilities["input_mode"], "supplied_capture_bundle")
        self.assertTrue(capabilities["threejs"]["progressive"])
        self.assertEqual(set(capabilities["capture_kinds"]), CAPTURE_KINDS)
        self.assertIn("video", capabilities["capture_kinds"])
        self.assertEqual(
            capabilities["operations"],
            ["inspect_snapshot", "summarize_inspection", "inspection_capabilities"],
        )

    def test_cli_inspect_summary_and_capabilities(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inspection.json"
            path.write_text(json.dumps(bundle()), encoding="utf-8")

            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["inspect", str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(stdout.getvalue(), normalize_inspection(bundle()))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["inspect-summary", str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(stdout.getvalue())["threejs_evidence"]["status"],
                "high_level",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["inspect-capabilities"])
            self.assertEqual(status, 0)
            self.assertFalse(json.loads(stdout.getvalue())["browser_automation"])


if __name__ == "__main__":
    unittest.main()

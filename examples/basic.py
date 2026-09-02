"""Create and validate a minimal Visparse record."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse import normalize_record

record = {
    "schema_version": "0.1",
    "sources": [{
        "id": "source-1", "kind": "image", "locator": "file:example.png",
        "content_hash": "sha256:replace-with-capture-hash",
    }],
    "measurements": [{
        "id": "measurement-1", "source_id": "source-1", "name": "width",
        "value": 1280, "unit": "px", "method": "decoded pixel dimensions",
    }],
    "observations": [{
        "id": "observation-1", "source_ids": ["source-1"],
        "statement": "A rectangular region is visible.",
    }],
    "interpretations": [{
        "id": "interpretation-1", "observation_ids": ["observation-1"],
        "statement": "The region may be an interactive control.", "confidence_id": "confidence-1",
    }],
    "confidence": [{
        "id": "confidence-1", "level": 0.4,
        "uncertainty": "No pointer or keyboard interaction was performed.",
        "basis": "The interpretation uses appearance only.",
    }],
    "interactions": [{
        "id": "interaction-1", "kind": "temporal", "source_id": "source-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "details": {"event": "capture", "sequence": 1},
    }],
    "provenance": {
        "created_by": "examples/basic.py", "created_at": "2026-01-01T00:00:00Z",
        "inputs": ["source-1"],
    },
}

print(normalize_record(record), end="")

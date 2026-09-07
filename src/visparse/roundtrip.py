"""Provider-neutral round-trip export and evaluation of stored generation runs."""

from __future__ import annotations

import statistics
import hashlib
from collections import defaultdict

from .compare import compare_design
from .contracts import bounded, canonical, check, items, number, shape, text, unique
from .dna import DIMENSIONS, validate_dna
from .render import render_design, export_policy

BASELINES = {"no_guidance", "profile", "design_md"}
CONDITIONS = BASELINES | {"profile_and_design_md"}


def prepare_roundtrip(reference: dict, brief: str, *, intent: str = "adapt") -> dict:
    """Export only derived controlled guidance and a separately supplied brief."""
    validate_dna(reference)
    text(brief)
    return bounded({"schema_version": "0.1", "brief": brief,
        "design_md": render_design(reference, generation_safe=True, intent=intent),
        "export_policy": export_policy(intent),
        "protocol": {"version": "0.1", "allowed_inputs": ["brief", "design_md"],
            "workspace": "Use a fresh workspace containing only the allowed inputs and neutral tooling.",
            "prohibitions": ["Do not fetch the reference site or original artifacts.",
                "Do not copy reference logos, branding, text, assets, DOM/CSS, or information architecture."]}})


def evaluate_roundtrip(fixture: dict) -> dict:
    """Compare stored runs and baselines without executing arbitrary generators."""
    bounded(fixture)
    shape(fixture, {"schema_version", "reference", "briefs", "runs"})
    check(fixture["schema_version"] == "0.1", "unsupported roundtrip fixture version")
    validate_dna(fixture["reference"])
    briefs = unique(fixture["briefs"])
    for brief in briefs.values():
        shape(brief, {"id", "text"})
        text(brief["text"])
    runs = unique(fixture["runs"])
    results = []
    groups = defaultdict(list)
    repetitions = set()
    for run in runs.values():
        shape(run, {"id", "brief_id", "condition", "generator", "configuration", "replicate", "generated", "human_reviews", "input_manifest"})
        check(run["brief_id"] in briefs, "unknown brief")
        check(run["condition"] in CONDITIONS, "unknown baseline condition")
        text(run["generator"])
        check(type(run["replicate"]) is int and run["replicate"] >= 1, "replicate must be positive integer")
        shape(run["configuration"], {"model_version", "prompt_version", "generation_budget", "parameters"}, {"export_policy"})
        if "export_policy" in run["configuration"]:
            policy = run["configuration"]["export_policy"]
            check(isinstance(policy, dict), "invalid export policy")
            check(policy == export_policy(policy.get("intent")), "invalid export policy")
        text(run["configuration"]["model_version"])
        text(run["configuration"]["prompt_version"])
        text(run["configuration"]["generation_budget"])
        check(isinstance(run["configuration"]["parameters"], dict), "invalid generator parameters")
        shape(run["input_manifest"], {"brief_sha256", "guidance_sha256", "workspace_isolated", "original_artifacts_available"})
        manifest = run["input_manifest"]
        for key in ("brief_sha256", "guidance_sha256"):
            value = manifest[key]
            check(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), "invalid input digest")
        check(manifest["brief_sha256"] == hashlib.sha256(briefs[run["brief_id"]]["text"].encode("utf-8")).hexdigest(), "brief digest mismatch")
        check(manifest["workspace_isolated"] is True and manifest["original_artifacts_available"] is False,
              "roundtrip requires declared isolated generation inputs")
        group_key = canonical([run["brief_id"], run["generator"], run["configuration"]])
        replicate_key = (group_key, run["condition"], run["replicate"])
        check(replicate_key not in repetitions, "duplicate benchmark replicate")
        repetitions.add(replicate_key)
        comparison = compare_design(fixture["reference"], run["generated"])
        reviews = unique(run["human_reviews"], "reviewer")
        for review in reviews.values():
            shape(review, {"reviewer", "score", "blinded", "basis"})
            number(review["score"], 0, 1)
            check(isinstance(review["blinded"], bool), "invalid blind-review flag")
            text(review["basis"])
        result = {"id": run["id"], "condition": run["condition"], "comparison": comparison,
                  "human_review": {"count": len(reviews), "mean": statistics.mean(r["score"] for r in reviews.values()) if reviews else None,
                    "reviews": list(reviews.values())}}
        results.append(result)
        groups[group_key].append(result)
    summaries = []
    for key, group in groups.items():
        conditions = {}
        for condition in sorted(CONDITIONS):
            selected = [r for r in group if r["condition"] == condition]
            per_dimension = {}
            for dimension in DIMENSIONS:
                values = [r["comparison"]["dimensions"][dimension]["score"] for r in selected]
                scores = [v for v in values if v is not None]
                per_dimension[dimension] = {"scored_runs": len(scores), "mean": statistics.mean(scores) if scores else None,
                    "stddev": statistics.stdev(scores) if len(scores) > 1 else None,
                    "coverage": [r["comparison"]["dimensions"][dimension]["coverage"] for r in selected]}
            conditions[condition] = {"runs": len(selected), "dimensions": per_dimension}
        summaries.append({"group": key.strip(), "conditions": conditions,
            "complete_baselines": all(conditions[c]["runs"] for c in BASELINES),
            "independent_review_available": any(r["human_review"]["count"] for r in group)})
    return {"schema_version": "0.1", "runs": results, "groups": summaries,
        "limitations": ["Generation is external; input manifests are declarations, not proof of sandbox execution.",
            "Comparison scores do not prove visual preservation; inspect coverage, baselines, repetitions, and blinded review separately."]}

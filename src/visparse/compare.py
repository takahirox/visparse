"""Inspectable DNA comparison; missing evidence never earns a similarity score."""

from __future__ import annotations

import statistics

from .contracts import check, number
from .dna import DIMENSIONS, FEATURES, feature_groups, group_status, validate_dna


def value_similarity(name, left, right, *, tolerance=None):
    spec = FEATURES[name]
    if spec[1] in {"enum", "text", "color"}:
        return float(left == right)
    absolute = spec[3] if tolerance is None else tolerance
    delta = abs(left - right)
    # Full credit within the declared absolute tolerance; outside it decay
    # by the larger magnitude. Every raw difference remains in the report.
    if delta <= absolute:
        return 1.0
    return max(0.0, 1 - (delta - absolute) / max(abs(left), abs(right), absolute, 1e-12))


def compare_design(reference: dict, generated: dict, *, min_confidence=0.6, tolerances=None) -> dict:
    validate_dna(reference)
    validate_dna(generated)
    number(min_confidence, 0, 1)
    tolerances = tolerances or {}
    check(isinstance(tolerances, dict), "tolerances must be an object")
    for key, value in tolerances.items():
        check(key in FEATURES and FEATURES[key][1] not in {"enum", "text", "color"}, "invalid tolerance feature")
        number(value, 0)
    left, right = feature_groups(reference), feature_groups(generated)
    def evidence_summary(dna, group):
        ids = sorted({eid for f in group for eid in f["evidence_ids"]})
        samples = [{"evidence_id": e["id"], "sample_count": e["details"].get("sample_count"), "coverage": e["details"]["coverage"]}
                   for e in dna["evidence"] if e["id"] in ids and "coverage" in e["details"]]
        return {"ids": ids, "samples": samples}
    dimensions = {d: {"score": None, "eligible": 0, "compared": 0, "coverage": None, "skipped": {}, "features": []} for d in DIMENSIONS}
    for key in sorted(left.keys() | right.keys()):
        lgroup, rgroup = left.get(key, []), right.get(key, [])
        feature = (lgroup or rgroup)[0]
        name = feature["name"]
        dimension = dimensions[FEATURES[name][0]]
        ls, rs = group_status(lgroup, min_confidence), group_status(rgroup, min_confidence)
        row = {"name": name, "scope": feature["scope"], "reference_status": ls, "generated_status": rs,
               "reference": lgroup[0]["value"] if lgroup else None, "generated": rgroup[0]["value"] if rgroup else None,
               "score": None, "difference": None}
        if "relative_to" in feature:
            row["relative_to"] = feature["relative_to"]
        row["evidence"] = {"reference": evidence_summary(reference, lgroup), "generated": evidence_summary(generated, rgroup)}
        if ls == rs == "not_applicable":
            reason = "not_applicable"
        else:
            dimension["eligible"] += 1
            reason = f"reference:{ls},generated:{rs}"
        if ls == rs == "known":
            dimension["compared"] += 1
            row["score"] = value_similarity(name, row["reference"], row["generated"], tolerance=tolerances.get(name))
            if isinstance(row["reference"], (int, float)):
                row["difference"] = row["generated"] - row["reference"]
                row["tolerance"] = tolerances.get(name, FEATURES[name][3])
            elif row["reference"] != row["generated"]:
                row["difference"] = "category/value differs"
            row["reason"] = "compared"
        else:
            dimension["skipped"][reason] = dimension["skipped"].get(reason, 0) + 1
            row["reason"] = reason
        dimension["features"].append(row)
    for dimension in dimensions.values():
        scores = [r["score"] for r in dimension["features"] if r["score"] is not None]
        dimension["score"] = statistics.mean(scores) if scores else None
        dimension["coverage"] = dimension["compared"] / dimension["eligible"] if dimension["eligible"] else None
    return {"schema_version": "0.1", "comparison_policy": "0.1", "min_confidence": min_confidence,
            "dimensions": dimensions, "limitations": ["Agreement measures represented features only; use independent review and analysis evaluation.",
                "Text features compare exact normalized strings; no embedding or semantic equivalence is inferred."]}

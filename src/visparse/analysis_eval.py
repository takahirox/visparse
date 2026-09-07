"""Stored-prediction evaluation of scoped claims, human labels, and calibration."""

from __future__ import annotations

import itertools
import statistics
from collections import Counter

from .contracts import bounded, check, items, number, refs, shape, text, unique
from .dna import DIMENSIONS, FEATURES, feature_groups, feature_key, group_status, validate_dna, validate_scope, validate_value
from .model import ValidationError


def calibration(pairs: list[tuple[float, float]]) -> dict:
    buckets = []
    for index in range(10):
        values = [(p, y) for p, y in pairs if min(int(p * 10), 9) == index]
        buckets.append({"lower": index / 10, "upper": (index + 1) / 10, "count": len(values),
            "mean_confidence": statistics.mean(p for p, y in values) if values else None,
            "observed_correctness": statistics.mean(y for p, y in values) if values else None})
    return {"count": len(pairs), "brier": statistics.mean((p - y) ** 2 for p, y in pairs) if pairs else None,
        "ece": sum(b["count"] * abs(b["mean_confidence"] - b["observed_correctness"]) for b in buckets if b["count"]) / len(pairs) if pairs else None,
        "buckets": buckets}


def _matches(name, value, expected, tolerance):
    if FEATURES[name][1] in {"text", "enum"}:
        return value == expected
    return abs(value - expected) <= tolerance


def _validate_fixture(fixture):
    bounded(fixture)
    shape(fixture, {"schema_version", "items", "predictions"})
    check(fixture["schema_version"] == "0.1", "unsupported analysis fixture version")
    samples = unique(fixture["items"])
    check(bool(samples), "evaluation needs at least one item")
    for sample in samples.values():
        shape(sample, {"id", "evidence", "expected", "provenance"})
        validate_dna(sample["evidence"])
        text(sample["provenance"])
        expected = unique(sample["expected"])
        for claim in expected.values():
            shape(claim, {"id", "name", "scope", "unit", "kind", "tolerance", "annotations"})
            check(claim["name"] in FEATURES, "unsupported expected feature")
            spec = FEATURES[claim["name"]]
            validate_value(claim["name"], spec[2][0] if spec[2] else ("value" if spec[1] == "text" else 0), claim["unit"])
            validate_scope(claim["scope"])
            check(claim["kind"] in {"grounding", "interpretive"}, "invalid evaluation kind")
            number(claim["tolerance"], 0)
            annotators = unique(claim["annotations"], "annotator")
            for annotation in annotators.values():
                shape(annotation, {"annotator", "value"})
                validate_value(claim["name"], annotation["value"], claim["unit"])
            check(claim["kind"] != "interpretive" or bool(annotators), "interpretive evaluation requires annotations")
    models = unique(fixture["predictions"], "model")
    for model in models.values():
        shape(model, {"model", "configuration", "cases"})
        shape(model["configuration"], {"model_version", "prompt_version", "input_protocol", "parameters"})
        for key in ("model_version", "prompt_version", "input_protocol"):
            text(model["configuration"][key])
        check(isinstance(model["configuration"]["parameters"], dict), "invalid inference parameters")
        cases = unique(model["cases"], "item_id")
        check(cases.keys() <= samples.keys(), "unknown prediction item")
    return samples, models


def evaluate_analysis(fixture: dict) -> dict:
    """No calls to live providers. Confidence means probability this claim is correct.

    Grounded correctness uses a scoped mechanical/observed fact. Interpretive
    correctness means agreement with a randomly selected supplied annotator.
    """
    samples, models = _validate_fixture(fixture)
    reports = []
    for model in models.values():
        dimensions = {d: {"expected": 0, "predicted": 0, "supported": 0, "contradicted": 0,
            "grounding_expected": 0, "grounding_predicted": 0, "interpretive_expected": 0, "interpretive_predicted": 0,
            "insufficient_evidence": 0, "missing": 0, "invalid": 0, "human_agreements": [], "human_pairs": [],
            "grounding_pairs": [], "interpretive_pairs": [], "rows": []} for d in DIMENSIONS}
        cases = {c["item_id"]: c for c in model["cases"]}
        invalid_cases = []
        for sample_id, sample in samples.items():
            expected = unique(sample["expected"])
            facts = feature_groups(sample["evidence"])
            evidence = unique(sample["evidence"]["evidence"])
            case = cases.get(sample_id, {"item_id": sample_id, "claims": []})
            valid_case = True
            try:
                shape(case, {"item_id", "claims"})
                claims = unique(case["claims"], "expected_id")
                check(claims.keys() <= expected.keys(), "unknown expected claim")
                for claim in claims.values():
                    shape(claim, {"expected_id", "name", "scope", "value", "unit", "confidence", "evidence_ids"})
                    validate_scope(claim["scope"])
                    validate_value(claim["name"], claim["value"], claim["unit"])
                    number(claim["confidence"], 0, 1)
                    refs(claim["evidence_ids"], evidence, nonempty=False)
            except (ValidationError, TypeError, KeyError) as error:
                invalid_cases.append({"item_id": sample_id, "error": str(error)})
                claims = {}
                valid_case = False
            for expected_id, target in expected.items():
                dim = dimensions[FEATURES[target["name"]][0]]
                dim["expected"] += 1
                dim[target["kind"] + "_expected"] += 1
                if target["kind"] == "interpretive":
                    labels = [a["value"] for a in target["annotations"]]
                    human_pairs = [_matches(target["name"], a, b, target["tolerance"]) for a, b in itertools.combinations(labels, 2)]
                    dim["human_pairs"].extend(human_pairs)
                row = {"item_id": sample_id, "expected_id": expected_id, "name": target["name"], "kind": target["kind"]}
                claim = claims.get(expected_id)
                if claim is None:
                    status = "missing" if valid_case else "invalid"
                    dim[status] += 1
                    dim["rows"].append({**row, "status": status})
                    continue
                dim["predicted"] += 1
                dim[target["kind"] + "_predicted"] += 1
                if claim["name"] != target["name"] or claim["scope"] != target["scope"] or claim["unit"] != target["unit"]:
                    dim["insufficient_evidence"] += 1
                    dim["rows"].append({**row, "status": "insufficient_evidence", "reason": "claim subject/viewport/state/property/unit mismatch"})
                    continue
                if target["kind"] == "grounding":
                    group = facts.get(feature_key(target), [])
                    status = group_status(group, 0)
                    cited = set(claim["evidence_ids"])
                    grounded = [f for f in group if f["origin"] != "inferred" and cited.intersection(f["evidence_ids"])]
                    if status != "known" or not grounded:
                        dim["insufficient_evidence"] += 1
                        dim["rows"].append({**row, "status": "insufficient_evidence", "reason": f"fact status={status}; requires cited measured/observed evidence"})
                        continue
                    correct = _matches(target["name"], claim["value"], grounded[0]["value"], target["tolerance"])
                    result = "supported" if correct else "contradicted"
                    dim[result] += 1
                    dim["grounding_pairs"].append((claim["confidence"], float(correct)))
                    dim["rows"].append({**row, "status": result, "prediction": claim["value"], "evidence_value": grounded[0]["value"], "tolerance": target["tolerance"]})
                else:
                    labels = [a["value"] for a in target["annotations"]]
                    agreement = statistics.mean(_matches(target["name"], claim["value"], label, target["tolerance"]) for label in labels)
                    dim["human_agreements"].append(agreement)
                    # Expected Brier against the actual annotation distribution,
                    # not merely squared error to its mean.
                    dim["interpretive_pairs"].extend((claim["confidence"], float(_matches(target["name"], claim["value"], label, target["tolerance"]))) for label in labels)
                    dim["rows"].append({**row, "status": "human_scored", "agreement": agreement,
                        "annotations": target["annotations"], "annotation_distribution": dict(Counter(str(x) for x in labels)),
                        "human_pairwise_agreement": statistics.mean(human_pairs) if human_pairs else None})
        for dimension in dimensions.values():
            dimension["coverage"] = dimension["predicted"] / dimension["expected"] if dimension["expected"] else None
            decidable = dimension["supported"] + dimension["contradicted"]
            dimension["supported_claim_rate"] = dimension["supported"] / decidable if decidable else None
            dimension["contradiction_rate"] = dimension["contradicted"] / decidable if decidable else None
            dimension["grounding_coverage"] = decidable / dimension["grounding_predicted"] if dimension["grounding_predicted"] else None
            agreement = dimension.pop("human_agreements")
            pairs = dimension.pop("human_pairs")
            dimension["human_agreement"] = statistics.mean(agreement) if agreement else None
            dimension["human_pairwise_agreement"] = statistics.mean(pairs) if pairs else None
            dimension["human_scored_claims"] = len(agreement)
            dimension["human_pair_count"] = len(pairs)
            dimension["calibration"] = {"grounding": calibration(dimension.pop("grounding_pairs")),
                "interpretive": calibration(dimension.pop("interpretive_pairs"))}
        reports.append({"model": model["model"], "configuration": model["configuration"], "dimensions": dimensions,
            "invalid_cases": invalid_cases, "invalid_case_rate": len(invalid_cases) / len(samples),
            "missing_case_count": len(samples.keys() - cases.keys())})
    return {"schema_version": "0.1", "evaluation_policy": "0.1", "models": reports,
        "confidence_targets": {"grounding": "probability that the scoped claim matches the cited fact within tolerance",
            "interpretive": "probability that the scoped claim agrees with a randomly selected supplied annotator"},
        "limitations": ["Human pairwise agreement is descriptive, not chance-corrected reliability; no unstable normalization by human agreement is applied.",
            "Calibration is empirical on supplied labels; synthetic fixtures do not establish live model quality."]}

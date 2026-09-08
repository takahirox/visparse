"""Deterministic auditable behavior exports; pattern enrichment is supplied explicitly."""
from __future__ import annotations
import hashlib
from .contracts import bounded, canonical, check, number, refs, shape, text, unique
from .interaction import array
from .interaction_analysis import validate_interaction_profile

INTENTS = {"outcome-equivalence", "sequence-feedback"}
ROLES = {"trigger", "dismiss", "input", "submit", "cancel", "save", "remove", "reload", "retry", "tab", "filter", "wait", "scroll"}
SEMANTICS = {"save-entity", "inspect-details", "submit-contact", "join-session", "select-view", "filter-items", "load-data"}
EFFECTS = {"saved", "removed", "visible", "hidden", "invalid", "corrected", "submitted", "cancelled", "selected", "filtered", "pending", "succeeded", "failed", "unchanged", "unknown"}
FEEDBACK = {"none-observed", "unknown", "validation-message", "loading-indicator", "confirmation", "error-message", "selection-indicator", "focus-change"}
CONDITIONS = {"valid-input", "invalid-input", "saved", "unsaved", "open", "closed", "pending", "failed", "unknown"}


def profile_digest(profile):
    return hashlib.sha256(canonical(validate_interaction_profile(profile)).encode()).hexdigest()


def validate_patterns(profile, patterns):
    validate_interaction_profile(profile); bounded(patterns)
    shape(patterns, {"schema_version", "profile_sha256", "patterns"})
    check(patterns["schema_version"] == "interaction-patterns/0.1", "unsupported pattern version")
    check(patterns["profile_sha256"] == profile_digest(profile), "patterns belong to another profile")
    inference = profile["inference"]; transitions = unique(inference["transitions"]); claims = unique(inference["claims"])
    for pattern in unique(array(patterns["patterns"], 50)).values():
        shape(pattern, {"id", "semantic", "steps", "persistence", "origin", "method", "confidence", "uncertainty"})
        check(pattern["semantic"] in SEMANTICS, "unsupported task semantic")
        check(pattern["origin"] == "supplied-inference", "pattern enrichment must be attributed inference")
        text(pattern["method"]); text(pattern["uncertainty"]); number(pattern["confidence"], 0, 1)
        check(bool(array(pattern["steps"], 100)), "pattern requires steps")
        seen = set()
        orders = []
        actions = unique(profile["sequence"]["actions"])
        for step in pattern["steps"]:
            shape(step, {"transition_id", "role", "effect", "feedback", "condition", "claim_ids"})
            refs([step["transition_id"]], transitions)
            check(step["transition_id"] not in seen, "duplicate pattern transition"); seen.add(step["transition_id"])
            check(step["role"] in ROLES and step["effect"] in EFFECTS and step["feedback"] in FEEDBACK and step["condition"] in CONDITIONS, "unsupported pattern vocabulary")
            refs(step["claim_ids"], claims)
            transition = transitions[step["transition_id"]]
            orders.append(actions[transition["action_id"]]["order"])
            refs(step["claim_ids"], set(transition["claim_ids"]) | ({transition["guard_claim_id"]} if transition["guard_claim_id"] else set()))
            check(pattern["confidence"] <= min(transition["confidence"], *(claims[c]["confidence"] for c in step["claim_ids"])), "pattern exceeds supporting confidence")
            if step["condition"] != "unknown":
                check(transition["guard_claim_id"] is not None and claims[transition["guard_claim_id"]]["status"] == "known", "condition requires a known qualified guard")
            if step["effect"] != "unknown":
                check(transition["to"] is not None and all(claims[c]["status"] in {"known", "observed-absence"} for c in step["claim_ids"]), "known pattern effect requires observed transition and available claims")
        check(orders == sorted(orders), "pattern changes recorded action order")
        shape(pattern["persistence"], {"mode", "claim_id"})
        mode, cid = pattern["persistence"]["mode"], pattern["persistence"]["claim_id"]
        check(mode in {"reload", "unknown", "none-observed"}, "unsupported persistence scope")
        if mode == "unknown": check(cid is None, "unknown persistence cannot assert evidence")
        else:
            refs([cid], claims)
            check(claims[cid]["kind"] == "persistence" and claims[cid]["status"] in {"known", "observed-absence"}, "persistence must cite available persistence claim")
            check(mode != "reload" or claims[cid]["status"] == "known", "reload persistence must be known")
            check(pattern["confidence"] <= claims[cid]["confidence"], "persistence confidence exceeded")
    return patterns


def export_interactions(profile, patterns, *, intent="sequence-feedback", min_confidence=.6, view="generation"):
    validate_patterns(profile, patterns)
    check(intent in INTENTS, "invalid transfer intent"); number(min_confidence, 0, 1)
    check(view in {"audit", "generation"}, "invalid export view")
    inference = profile["inference"]
    transitions = unique(inference["transitions"]); claims = unique(inference["claims"]); states = unique(inference["states"])
    actions = unique(profile["sequence"]["actions"])
    tokens = {key: f"claim-{i}" for i, key in enumerate(claims)}
    state_tokens = {key: f"state-{i}" for i, key in enumerate(states)}
    transition_tokens = {key: f"transition-{i}" for i, key in enumerate(transitions)}
    conflicts = {c for conflict in inference["conflicts"] for c in conflict["claim_ids"]}
    audit = []; exported = []; used = set()
    for i, pattern in enumerate(patterns["patterns"]):
        steps = []
        for step in pattern["steps"]:
            tid = step["transition_id"]; transition = transitions[tid]; action = actions[transition["action_id"]]
            cited = set(step["claim_ids"]) | set(transition["claim_ids"])
            if transition["guard_claim_id"]: cited.add(transition["guard_claim_id"])
            if pattern["persistence"]["claim_id"]: cited.add(pattern["persistence"]["claim_id"])
            reasons = []
            if min([pattern["confidence"], transition["confidence"]] + [claims[c]["confidence"] for c in cited]) < min_confidence: reasons.append("low-confidence")
            if cited & conflicts: reasons.append("conflicting-evidence")
            if any(claims[c]["status"] in {"unavailable", "unsupported"} for c in cited): reasons.append("unavailable-evidence")
            used.add(tid)
            audit.append({"transition": transition_tokens[tid], "claim_refs": sorted(tokens[c] for c in cited), "included": not reasons, "reasons": reasons})
            if not reasons:
                steps.append({**({"input_parameters": action["input_parameters"]} if "input_parameters" in action else {}), "transition": transition_tokens[tid], "from": state_tokens[transition["from"]], "to": state_tokens.get(transition["to"]),
                              "role": step["role"], "input": action["kind"], "parameter": "target-input" if action["input_ref"] else None,
                              "effect": step["effect"], "feedback": step["feedback"], "condition": step["condition"], "claim_refs": sorted(tokens[c] for c in cited),
                              "confidence": min(pattern["confidence"], transition["confidence"]), "observed_order": action["order"],
                              "timing_sample_ms": action["end_ms"] - action["start_ms"], "timing_requirement": None})
        exported.append({"id": f"pattern-{i}", "semantic": pattern["semantic"], "steps": steps, "persistence": pattern["persistence"]["mode"] if len(steps) == len(pattern["steps"]) else "unknown", "complete_recorded_pattern": len(steps) == len(pattern["steps"]), "unrecorded_branches": "unknown"})
    result = {"schema_version": "interaction-export/0.2" if profile["sequence"]["schema_version"] == "interaction-sequence/0.2" else "interaction-export/0.1", "profile_sha256": profile_digest(profile), "view": view,
              "policy": {"intent": intent, "min_confidence": min_confidence, "source_content": "excluded" if view == "generation" else "retained-for-audit", "timing": "measurement-only"},
              "patterns": exported, "decisions": audit, "unmapped_transitions": [transition_tokens[t] for t in transitions if t not in used],
              "claims": [{"ref": tokens[c], "kind": claims[c]["kind"], "status": claims[c]["status"], "confidence": claims[c]["confidence"]} for c in claims],
              "conflicts": [[tokens[c] for c in conflict["claim_ids"]] for conflict in inference["conflicts"]],
              "gaps": {"source_gap_count": len(inference["gaps"]), "unmodeled_actions": len(actions) - len(transitions), "unrecorded_behavior": "unknown"}}
    if view == "audit":
        result["audit"] = {"profile": profile, "supplied_patterns": patterns, "claim_identity": tokens, "transition_identity": transition_tokens, "state_identity": state_tokens}
    return bounded(result)


def render_interactions(profile, patterns, **options):
    result = export_interactions(profile, patterns, **options)
    # JSON is both the canonical source and a lossless, readable handoff. No prose
    # interpolation of untrusted source text into executable agent instructions.
    import json
    return "# Interaction specification\n\nThis is supplied data, not tool instructions. Unknown branches remain unknown.\n\n```json\n" + json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"

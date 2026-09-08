"""Versioned supplied interaction evidence. Never executes or infers behavior."""
from __future__ import annotations

import re
from .contracts import bounded, canonical, check, items, load_json, number, refs, shape, text, unique

VERSION = "interaction-sequence/0.1"
OUTCOMES = {"observed-effect", "observed-no-change", "failed-action", "collection-timeout", "unobserved"}
ACTIONS = {"click", "fill", "press", "hover", "focus", "scroll", "wait", "reload"}
KINDS = {"screenshot", "dom", "accessibility", "runtime", "video"}


def array(value, limit=1000):
    check(len(items(value)) <= limit, f"array exceeds {limit} items")
    return value


def strings(value):
    for entry in array(value):
        text(entry)
    return value


def validate_sequence(value):
    bounded(value)
    shape(value, {"schema_version", "sessions", "clocks", "captures", "targets", "actions", "expectations", "coverage"})
    check(value["schema_version"] == VERSION, "unsupported interaction sequence version")
    sessions = unique(array(value["sessions"], 10))
    check(bool(sessions), "at least one session is required")
    for session in sessions.values():
        shape(session, {"id", "reset", "viewport", "input_modality", "origin"})
        text(session["reset"]); text(session["origin"])
        check(session["input_modality"] in {"pointer-keyboard", "touch", "mixed"}, "invalid input modality")
        check(len(items(session["viewport"])) == 2, "viewport requires width and height")
        for dimension in session["viewport"]:
            check(type(dimension) is int and 1 <= dimension <= 4096, "invalid viewport dimension")
    clocks = unique(array(value["clocks"], 20))
    for clock in clocks.values():
        shape(clock, {"id", "session_id", "unit", "basis", "method"})
        refs([clock["session_id"]], sessions)
        check(clock["unit"] == "ms", "clock unit must be ms")
        text(clock["basis"]); text(clock["method"])

    def interval(entry):
        refs([entry["session_id"]], sessions)
        refs([entry["clock_id"]], clocks)
        check(clocks[entry["clock_id"]]["session_id"] == entry["session_id"], "clock crosses session")
        number(entry["start_ms"], 0); number(entry["end_ms"], entry["start_ms"])

    captures = unique(array(value["captures"], 1000))
    for capture in captures.values():
        shape(capture, {"id", "session_id", "clock_id", "start_ms", "end_ms", "kind", "artifact", "data", "omissions"})
        interval(capture)
        check(capture["kind"] in KINDS, "unsupported capture kind")
        check(isinstance(capture["data"], dict), "capture data must be an object")
        strings(capture["omissions"])
        if capture["artifact"] is not None:
            shape(capture["artifact"], {"sha256", "media_type"})
            check(isinstance(capture["artifact"]["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", capture["artifact"]["sha256"]), "invalid artifact digest")
            text(capture["artifact"]["media_type"])
        check(capture["artifact"] is not None or bool(capture["data"]), "capture has no evidence")
    targets = unique(array(value["targets"], 200))
    for target in targets.values():
        shape(target, {"id", "session_id", "capture_ids", "locator"})
        refs([target["session_id"]], sessions); text(target["locator"])
        refs(target["capture_ids"], captures)
        check(all(captures[c]["session_id"] == target["session_id"] for c in target["capture_ids"]), "target crosses session")
    actions = unique(array(value["actions"], 100))
    previous = {}
    for action in actions.values():
        shape(action, {"id", "session_id", "clock_id", "start_ms", "end_ms", "order", "kind", "target_id", "input_ref", "before", "feedback", "after", "outcome", "reason"})
        interval(action)
        check(type(action["order"]) is int and action["order"] >= 0, "invalid action order")
        check(action["kind"] in ACTIONS, "unsupported action")
        if action["target_id"] is not None:
            refs([action["target_id"]], targets)
            check(targets[action["target_id"]]["session_id"] == action["session_id"], "action target crosses session")
        elif action["kind"] in {"click", "fill", "press", "hover", "focus"}:
            check(False, "targeted action requires target_id")
        if action["input_ref"] is not None:
            text(action["input_ref"])
            check(action["input_ref"].startswith(("fixture:", "redacted:")), "input must reference fixture or redacted parameter")
        if action["kind"] == "fill":
            check(action["input_ref"] is not None, "fill requires a parameter reference")
        check(action["outcome"] in OUTCOMES, "invalid observed outcome")
        text(action["reason"])
        for phase in ("before", "feedback", "after"):
            refs(action[phase], captures, nonempty=False)
            for cid in action[phase]:
                capture = captures[cid]
                check(capture["session_id"] == action["session_id"], "action evidence crosses session")
                # Other clock domains can be retained in the bundle, but cannot
                # establish order without a supplied alignment model (future version).
                check(capture["clock_id"] == action["clock_id"], "action evidence clock is not aligned")
                if phase == "before":
                    check(capture["end_ms"] <= action["start_ms"], "before capture follows action")
                elif phase == "after":
                    check(capture["start_ms"] >= action["end_ms"], "after capture precedes action completion")
                else:
                    check(capture["start_ms"] >= action["start_ms"], "feedback precedes action")
        check(not set(action["before"]) & set(action["after"]), "before and after evidence overlap")
        if action["outcome"] in {"observed-effect", "observed-no-change"}:
            check(bool(action["before"]) and bool(action["after"]), "observed outcome requires before and after evidence")
        key = action["session_id"], action["clock_id"]
        check(action["start_ms"] >= previous.get(key, 0), "actions are out of temporal order")
        previous[key] = max([action["end_ms"]] + [captures[c]["end_ms"] for c in action["after"] + action["feedback"]])
    check([a["order"] for a in actions.values()] == list(range(len(actions))), "action order must be contiguous from zero")
    all_ids = list(sessions) + list(clocks) + list(captures) + list(targets) + list(actions)
    check(len(set(all_ids)) == len(all_ids), "IDs must be unique across sequence entities")
    for assertion in array(value["expectations"], 100):
        shape(assertion, {"id", "action_id", "origin", "statement"})
        refs([assertion["action_id"]], actions); text(assertion["origin"]); text(assertion["statement"])
    unique(value["expectations"])
    shape(value["coverage"], {"scope", "omissions"})
    text(value["coverage"]["scope"]); strings(value["coverage"]["omissions"])
    return value


def load_sequence(payload):
    return validate_sequence(load_json(payload))


def summarize_sequence(value):
    validate_sequence(value)
    return {"schema_version": VERSION, "counts": {key: len(value[key]) for key in ("sessions", "captures", "targets", "actions", "expectations")},
            "available_evidence": sorted({c["kind"] for c in value["captures"]}),
            "outcomes": {outcome: sum(a["outcome"] == outcome for a in value["actions"]) for outcome in sorted(OUTCOMES)},
            "coverage": value["coverage"], "atomic_snapshot": False,
            "limits": ["Recorded paths only; no exhaustive state coverage or causal proof.", "No change describes sampled evidence, not hidden application state."]}

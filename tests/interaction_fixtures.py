"""Synthetic observations, independent of any live application's behavior."""
from copy import deepcopy


def sequence(outcome="observed-effect", kind="click"):
    value = {"schema_version": "interaction-sequence/0.1",
        "sessions": [{"id": "session", "reset": "fresh context, empty storage", "viewport": [800, 600], "input_modality": "pointer-keyboard", "origin": "synthetic fixture"}],
        "clocks": [{"id": "clock", "session_id": "session", "unit": "ms", "basis": "collector monotonic", "method": "perf_counter"}],
        "captures": [], "targets": [{"id": "target", "session_id": "session", "capture_ids": ["before"], "locator": "#save"}],
        "actions": [{"id": "action", "session_id": "session", "clock_id": "clock", "start_ms": 2, "end_ms": 3, "order": 0,
                     "kind": kind, "target_id": "target", "input_ref": None, "before": ["before"], "feedback": [], "after": ["after"], "outcome": outcome,
                     "reason": "Fixture reports sampled UI state, not backend success."}],
        "expectations": [{"id": "expected", "action_id": "action", "origin": "independent fixture oracle", "statement": "Saved state should be visible"}],
        "coverage": {"scope": "one synthetic action", "omissions": ["Unrecorded branches unknown"]}}
    for cid, start, state in [("before", 0, "unsaved"), ("after", 4, "saved" if outcome == "observed-effect" else "unsaved")]:
        value["captures"].append({"id": cid, "session_id": "session", "clock_id": "clock", "start_ms": start, "end_ms": start + 1,
                                  "kind": "dom", "artifact": None, "data": {"state": state}, "omissions": []})
    if outcome in {"unobserved", "collection-timeout"}:
        value["actions"][0]["after"] = []
        value["captures"].pop()
    return deepcopy(value)

"""Caller-supplied semantic mappings with explicit target preservation contracts."""
from __future__ import annotations
import hashlib
from .contracts import bounded, canonical, check, items, number, refs, shape, text, unique
from .interaction import array, strings
from .interaction_export import EFFECTS, ROLES, SEMANTICS, export_interactions

STATUSES = {"compatible", "qualified-partial", "conflict", "unsupported-capability", "insufficient-evidence"}
CAPABILITIES = {"dom", "keyboard", "form-validation", "local-storage", "async-feedback", "filtering"}


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_target_inventory(target):
    bounded(target)
    shape(target, {"schema_version", "id", "origin", "entities", "tasks", "capabilities", "invariants", "requirements"})
    check(target["schema_version"] == "interaction-target/0.1", "unsupported target version")
    text(target["id"]); text(target["origin"])
    entities = unique(array(target["entities"], 100)); tasks = unique(array(target["tasks"], 100))
    refs(target["capabilities"], CAPABILITIES, nonempty=False)
    for entity in entities.values():
        shape(entity, {"id", "fields", "records"})
        check(bool(items(entity["fields"])), "entity fields required"); strings(entity["fields"])
        check(len(set(entity["fields"])) == len(entity["fields"]), "duplicate data field")
        for record in array(entity["records"], 100):
            check(isinstance(record, dict) and record.keys() == set(entity["fields"]), "record must preserve declared data fields")
    for task in tasks.values():
        shape(task, {"id", "semantic", "entity_id", "roles", "effects", "persistence", "cancellation", "recovery", "capabilities"})
        check(task["semantic"] in SEMANTICS, "unsupported target semantic")
        refs([task["entity_id"]], entities); refs(task["roles"], ROLES); refs(task["effects"], EFFECTS)
        check(task["persistence"] in {"reload", "none-observed", "unknown"}, "invalid target persistence")
        for key in ("cancellation", "recovery"):
            check(task[key] in {"supported", "unsupported", "unknown"}, "invalid target behavior availability")
        refs(task["capabilities"], CAPABILITIES, nonempty=False)
    invariants = unique(array(target["invariants"], 200)); requirements = unique(array(target["requirements"], 100))
    for invariant in invariants.values():
        shape(invariant, {"id", "task_id", "kind", "expected", "origin"})
        refs([invariant["task_id"]], tasks); text(invariant["origin"])
        check(invariant["kind"] in {"data", "outcome", "cancellation", "recovery", "persistence"}, "invalid preservation invariant")
        check(invariant["expected"] is not None, "invariant must declare expected result")
    for requirement in requirements.values():
        shape(requirement, {"id", "task_id", "change", "value", "origin"})
        refs([requirement["task_id"]], tasks); text(requirement["origin"])
        check(requirement["change"] in {"add-capability", "persistence", "cancellation", "recovery"}, "unsupported target requirement change")
        if requirement["change"] == "add-capability": check(requirement["value"] in CAPABILITIES, "invalid required capability")
        elif requirement["change"] == "persistence": check(requirement["value"] in {"reload", "none-observed"}, "invalid required persistence")
        else: check(requirement["value"] == "supported", "invalid required behavior")
    ids=list(entities)+list(tasks)+list(invariants)+list(requirements)
    check(len(ids)==len(set(ids)), "duplicate target entity ID")
    return target


def prepare_mapping(profile, patterns, target, proposal, *, intent="sequence-feedback", view="generation"):
    source=export_interactions(profile,patterns,intent=intent)
    validate_target_inventory(target); bounded(proposal)
    shape(proposal, {"schema_version", "source_sha256", "target_sha256", "intent", "bindings", "origin", "method", "uncertainty"})
    check(proposal["schema_version"] == "interaction-mapping/0.1", "unsupported mapping version")
    check(proposal["source_sha256"] == digest(source) and proposal["target_sha256"] == digest(target), "mapping evidence hash mismatch")
    check(proposal["intent"] == intent, "mapping intent mismatch")
    check(proposal["origin"] == "supplied-inference", "mapping must retain inference origin")
    text(proposal["method"]); text(proposal["uncertainty"])
    check(view in {"generation","audit"}, "invalid mapping view")
    source_patterns=unique(source["patterns"]); tasks=unique(target["tasks"]); requirements=unique(target["requirements"])
    bindings=unique(array(proposal["bindings"],50),key="pattern_id")
    check(set(bindings)==set(source_patterns), "every source pattern needs an explicit mapping status")
    results=[]; scenarios=[]
    for pid,binding in bindings.items():
        shape(binding, {"pattern_id", "task_id", "status", "roles", "adaptations", "requirement_ids", "reason", "confidence", "uncertainty"})
        check(binding["status"] in STATUSES,"invalid mapping status"); text(binding["reason"]); text(binding["uncertainty"]);number(binding["confidence"],0,1)
        refs(binding["requirement_ids"], requirements, nonempty=False)
        pattern=source_patterns[pid]; role_map=binding["roles"]
        check(isinstance(role_map,dict),"roles must be a mapping")
        source_roles={s["role"] for s in pattern["steps"]}
        check(set(role_map)<=source_roles,"unknown source role")
        for role in role_map.values(): check(role in ROLES,"invalid target role")
        refs(binding["adaptations"], {"omit-source-role", "change-sequence", "change-feedback", "explicit-target-requirement"}, nonempty=False)
        issues=[]; task=None
        if binding["task_id"] is None: issues.append("target-task-unknown")
        else:
            refs([binding["task_id"]],tasks);task=tasks[binding["task_id"]]
            if task["semantic"] != pattern["semantic"]: issues.append("task-semantic-conflict")
            check(set(role_map.values())<=set(task["roles"]),"mapping names a role absent from target")
            # This bounded version validates exact semantic roles; aliases need a
            # future attributed vocabulary extension, not a label heuristic.
            if any(a != b for a,b in role_map.items()): issues.append("role-semantic-conflict")
            if not set(task["capabilities"])<=set(target["capabilities"]): issues.append("unsupported-capability")
            if pattern["persistence"] == "unknown": issues.append("persistence-evidence-unknown")
            elif task["persistence"] != pattern["persistence"]: issues.append("persistence-conflict")
            if not {s["effect"] for s in pattern["steps"] if s["effect"]!='unknown'}<=set(task["effects"]): issues.append("outcome-conflict")
            for role, field in (("cancel","cancellation"),("dismiss","cancellation"),("retry","recovery")):
                if role in source_roles and task[field]!="supported": issues.append(field+"-conflict")
        if set(role_map)!=source_roles: issues.append("unmapped-source-roles")
        if not pattern["complete_recorded_pattern"]: issues.append("incomplete-source-pattern")
        if any(s["input"] in {"press", "scroll", "wait"} and "input_parameters" not in s for s in pattern["steps"]): issues.append("input-parameters-unavailable")
        if any(s["effect"] == "unknown" or s["to"] is None for s in pattern["steps"]): issues.append("source-outcome-unknown")
        if binding["confidence"] < .6: issues.append("low-confidence")
        if task:
            for rid in binding["requirement_ids"]:
                check(requirements[rid]["task_id"]==task["id"],"requirement belongs to another task")
        else: check(not binding["requirement_ids"],"requirement requires target task")
        if binding["requirement_ids"]: check("explicit-target-requirement" in binding["adaptations"],"target changes must remain explicit adaptations")
        if intent=="sequence-feedback":
            check(not set(binding["adaptations"]) & {"change-sequence","change-feedback"},"intent requires order and feedback preservation")
        status=binding["status"]
        if status=="compatible":
            check(not issues and not binding["adaptations"] and not binding["requirement_ids"],"compatible mapping has conflicts, gaps or target changes: "+','.join(issues))
        elif status=="qualified-partial":
            check(task is not None and bool(binding["adaptations"]),"partial mapping requires task and explicit adaptation")
            check(not set(issues)&{"task-semantic-conflict","role-semantic-conflict","outcome-conflict"},"partial adaptation cannot change task meaning")
            check("unmapped-source-roles" not in issues or "omit-source-role" in binding["adaptations"],"omitted roles need explicit adaptation")
            for issue, change, desired in [("unsupported-capability","add-capability",None),("persistence-conflict","persistence",pattern["persistence"]),("cancellation-conflict","cancellation","supported"),("recovery-conflict","recovery","supported")]:
                if issue in issues:
                    approved=[requirements[r] for r in binding["requirement_ids"] if requirements[r]["change"]==change]
                    if change=="add-capability": check(set(task['capabilities'])-set(target['capabilities']) <= {r['value'] for r in approved},"missing explicit capability requirement")
                    else: check(any(r['value']==desired for r in approved),"target behavior change requires explicit requirement")
        elif status=="conflict": check(any('conflict' in i for i in issues),"conflict status lacks declared semantic mismatch")
        elif status=="unsupported-capability": check("unsupported-capability" in issues,"unsupported status lacks capability gap")
        else: check(bool(issues),"insufficient evidence status lacks a gap")
        executable=status=="compatible" # partial proposals always require external resolution
        results.append({"pattern_id":pid,"task_id":binding['task_id'],"status":status,"roles":role_map,"adaptations":binding['adaptations'],"requirement_ids":binding['requirement_ids'],"issues":issues,"confidence":binding['confidence'],"ready":executable,"unmapped_roles":sorted(source_roles-set(role_map))})
        if task:
            scenarios.append({"task_id":task['id'],"pattern_id":pid,"ready":executable,"steps":[{**({"input_parameters": s["input_parameters"]} if "input_parameters" in s else {}), "role":role_map.get(s['role']),"input":s['input'],"expected_effect":s['effect'],"condition":s['condition'],"feedback":s['feedback'],"source_transition":s['transition']} for s in pattern['steps']],"persistence":task['persistence'],"cancellation":task['cancellation'],"recovery":task['recovery']})
    result={"schema_version":"interaction-handoff/0.1","intent":intent,"source_export":source,"target_inventory":target,"bindings":results,"verification_scenarios":scenarios,
            "preservation":{"task_ids":list(tasks),"entity_sha256":{e['id']:digest(e) for e in target['entities']},"invariant_ids":[v['id'] for v in target['invariants']]},
            "unmapped_target_tasks":sorted(set(tasks)-{r['task_id'] for r in results if r['task_id']}),"new_capabilities_implemented":False}
    if view=="audit":result['audit']={"source":export_interactions(profile,patterns,intent=intent,view='audit'),"proposal":proposal}
    return bounded(result)

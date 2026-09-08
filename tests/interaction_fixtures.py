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


def prediction(value=None):
    from visparse.interaction_analysis import sequence_digest
    value = value or sequence()
    state = dict(component="saved-item", method="fixture annotation", confidence=.8, uncertainty="only recorded path")
    return {"schema_version": "interaction-prediction/0.1", "sequence_sha256": sequence_digest(value),
            "states": [dict(state, id="unsaved", label="Unsaved", capture_ids=["before"]), dict(state, id="saved", label="Saved", capture_ids=["after"])],
            "claims": [{"id":"result", "kind":"outcome", "subject":"saved-item", "status":"known", "value":"Saved marker visible", "evidence_ids":["action","after"], "method":"fixture annotation", "confidence":.8, "uncertainty":"backend and persistence unknown"}],
            "transitions": [{"id":"save-transition", "from":"unsaved", "to":"saved", "action_id":"action", "guard_claim_id":None, "claim_ids":["result"], "method":"fixture annotation", "confidence":.8, "uncertainty":"other paths unknown"}],
            "conflicts":[], "gaps":["Persistence and unrecorded branches unknown"]}


def patterns(profile):
    from visparse.interaction_export import profile_digest
    return {"schema_version":"interaction-patterns/0.1", "profile_sha256":profile_digest(profile), "patterns":[{
        "id":"source-save", "semantic":"save-entity", "steps":[{"transition_id":"save-transition","role":"save","effect":"saved","feedback":"confirmation","condition":"unknown","claim_ids":["result"]}],
        "persistence":{"mode":"unknown","claim_id":None},"origin":"supplied-inference","method":"explicit fixture annotation","confidence":.8,"uncertainty":"Only recorded path"}]}


def flow_fixture():
    """Explicit synthetic save/reload/remove and form correction/cancel annotations."""
    from visparse.interaction_analysis import sequence_digest, apply_interaction_analysis
    from visparse.interaction_export import profile_digest
    value=sequence();value.update(captures=[], targets=[], actions=[], expectations=[])
    inferred={"schema_version":"interaction-prediction/0.1","sequence_sha256":"", "states":[], "claims":[],"transitions":[],"conflicts":[],"gaps":["Synthetic paths only; other branches unknown"]}
    flow=[('click','save','saved','save-entity'),('reload','reload','saved','save-entity'),('click','remove','removed','save-entity'),
          ('click','submit','invalid','submit-contact'),('fill','input','corrected','submit-contact'),('click','submit','submitted','submit-contact'),('click','cancel','cancelled','submit-contact')]
    groups={}
    for i,(kind,role,effect,semantic) in enumerate(flow):
        before,after=f'before-{i}',f'after-{i}'; aid=f'action-{i}'; tid=f'transition-{i}';cid=f'claim-{i}'
        for capture_id,offset,label in [(before,0,'before'),(after,6,effect)]:
            value['captures'].append({'id':capture_id,'session_id':'session','clock_id':'clock','start_ms':i*10+offset,'end_ms':i*10+offset+1,'kind':'dom','artifact':None,'data':{'fixture_effect':label},'omissions':[]})
            inferred['states'].append({'id':'state-'+capture_id,'component':semantic,'label':label,'capture_ids':[capture_id],'method':'synthetic annotation','confidence':.8,'uncertainty':'Not a real website observation'})
        target=None if kind=='reload' else f'target-{i}'
        if target:value['targets'].append({'id':target,'session_id':'session','capture_ids':[before],'locator':'#source-'+role})
        value['actions'].append({'id':aid,'session_id':'session','clock_id':'clock','start_ms':i*10+2,'end_ms':i*10+3,'order':i,'kind':kind,'target_id':target,'input_ref':'fixture:email' if kind=='fill' else None,'before':[before],'feedback':[],'after':[after],'outcome':'observed-effect','reason':'Synthetic fixture effect'})
        inferred['claims'].append({'id':cid,'kind':'outcome','subject':semantic,'status':'known','value':effect,'evidence_ids':[aid,after],'method':'synthetic annotation','confidence':.8,'uncertainty':'Only supplied path'})
        inferred['transitions'].append({'id':tid,'from':'state-'+before,'to':'state-'+after,'action_id':aid,'guard_claim_id':None,'claim_ids':[cid],'method':'synthetic annotation','confidence':.8,'uncertainty':'Unrecorded branches unknown'})
        groups.setdefault(semantic,[]).append({'transition_id':tid,'role':role,'effect':effect,'feedback':'validation-message' if effect=='invalid' else 'unknown','condition':'unknown','claim_ids':[cid]})
    inferred['claims'].append({'id':'persist','kind':'persistence','subject':'save-entity','status':'known','value':'Saved marker survives same-context reload','evidence_ids':['action-1','before-1','after-1'],'method':'synthetic reload annotation','confidence':.8,'uncertainty':'Cross-session persistence unknown'})
    inferred['sequence_sha256']=sequence_digest(value)
    profile=apply_interaction_analysis(value,inferred)
    enriched={'schema_version':'interaction-patterns/0.1','profile_sha256':profile_digest(profile),'patterns':[
        {'id':semantic,'semantic':semantic,'steps':steps,'persistence':{'mode':'reload','claim_id':'persist'} if semantic=='save-entity' else {'mode':'unknown','claim_id':None},'origin':'supplied-inference','method':'explicit synthetic annotation','confidence':.8,'uncertainty':'No real-model accuracy claim'} for semantic,steps in groups.items()]}
    return profile,enriched


def target_inventory():
    return {'schema_version':'interaction-target/0.1','id':'reading-list','origin':'Independent target fixture specification',
        'entities':[{'id':'article','fields':['id','title'],'records':[{'id':'a1','title':'Growing a city garden'},{'id':'a2','title':'A guide to bicycles'}]}],
        'tasks':[{'id':'bookmark','semantic':'save-entity','entity_id':'article','roles':['save','reload','remove'],'effects':['saved','removed'],
                  'persistence':'reload','cancellation':'unsupported','recovery':'unsupported','capabilities':['dom','local-storage']}],
        'capabilities':['dom','local-storage'],
        'invariants':[{'id':'keep-data','task_id':'bookmark','kind':'data','expected':'All article IDs and titles preserved','origin':'target author'},
                      {'id':'keep-storage','task_id':'bookmark','kind':'persistence','expected':'Saved set survives reload; removing one article preserves other articles','origin':'target author'}],
        'requirements':[]}


def mapping_fixture():
    from visparse.interaction_export import export_interactions
    from visparse.interaction_mapping import digest
    profile,p=flow_fixture();p['patterns']=p['patterns'][:1]
    target=target_inventory();source=export_interactions(profile,p)
    proposal={'schema_version':'interaction-mapping/0.1','source_sha256':digest(source),'target_sha256':digest(target),'intent':'sequence-feedback',
        'origin':'supplied-inference','method':'Caller maps saved entity to target bookmark','uncertainty':'Controlled fixture only',
        'bindings':[{'pattern_id':'pattern-0','task_id':'bookmark','status':'compatible','roles':{'save':'save','reload':'reload','remove':'remove'},'adaptations':[],
                     'requirement_ids':[],'reason':'Same save/remove semantics and same-context reload persistence','confidence':.8,'uncertainty':'Other storage lifetimes unknown'}]}
    return profile,p,target,proposal

"""Independent supplied-oracle evaluation, separate from capture and inference."""
from __future__ import annotations
from .contracts import bounded, canonical, check, refs, shape, text, unique
from .interaction import array

DIMENSIONS = {"capture", "analysis", "export", "behavior", "preservation", "appearance"}
CONDITIONS = {"screenshots-only", "video-actions", "screenshots-actions-dom-ax"}


def validate_ux_dataset(dataset):
    bounded(dataset)
    shape(dataset, {"schema_version", "id", "version", "author", "reset", "scope", "cases"})
    check(dataset["schema_version"] == "interaction-dataset/0.1", "unsupported UX dataset version")
    for key in ("id","version","author","reset","scope"):text(dataset[key])
    for case in unique(array(dataset["cases"],500)).values():
        shape(case, {"id", "partition", "dimension", "expected", "availability", "origin"})
        check(case["partition"] in {"recorded","held-out"},"invalid dataset partition")
        check(case["dimension"] in DIMENSIONS,"invalid evaluation dimension")
        check(case["availability"] in {"known","unknown"},"invalid expected availability");text(case["origin"])
        check((case["expected"] is None) == (case["availability"] == "unknown"),"unknown oracle requires null expectation")
    return dataset


def evaluate_interactions(dataset, run):
    validate_ux_dataset(dataset);bounded(run)
    shape(run, {"schema_version", "id", "dataset_id", "dataset_version", "origin", "condition", "adapter_status", "configuration", "inputs", "analysis_input_ids", "generator_input_ids", "results"})
    check(run["schema_version"] == "interaction-evaluation-run/0.1","unsupported UX run version")
    text(run['id']);check(run['dataset_id']==dataset['id'] and run['dataset_version']==dataset['version'],'dataset identity mismatch')
    check(run['origin'] in {'stored-synthetic','deterministic-adapter','live-model'},'invalid run origin')
    check(run['condition'] in CONDITIONS,'invalid evidence condition')
    check(run['adapter_status'] in {'available','unsupported'},'invalid adapter availability')
    check(isinstance(run['configuration'],dict),'configuration must be recorded')
    inputs=unique(array(run['inputs'],500));cases=unique(dataset['cases']);results=unique(array(run['results'],1000),key='case_id')
    for evidence in inputs.values():
        shape(evidence, {'id','kind','scope','partition','sha256'})
        check(evidence['kind'] in {'screenshot','video','action-log','dom','accessibility','export','target-context','code','execution'},'invalid evaluation input kind')
        check(evidence['scope'] in {'source','target','oracle'},'invalid evidence scope')
        check(evidence['partition'] in {'recorded','held-out'},'invalid input partition')
        import re
        check(isinstance(evidence['sha256'],str) and re.fullmatch('[0-9a-f]{64}',evidence['sha256']),'invalid input digest')
    refs(run['analysis_input_ids'],inputs,nonempty=False);refs(run['generator_input_ids'],inputs,nonempty=False)
    for eid in run['analysis_input_ids']+run['generator_input_ids']:
        check(inputs[eid]['partition']=='recorded' and inputs[eid]['scope']!='oracle','held-out/oracle evidence leaked into analysis or generation')
    for eid in run['generator_input_ids']:
        evidence=inputs[eid]
        check(evidence['kind']=='export' or evidence['scope']=='target' and evidence['kind'] in {'target-context','code'},'generator received forbidden source evidence')
    expected_kinds={'screenshots-only':{'screenshot'},'video-actions':{'video','action-log'},'screenshots-actions-dom-ax':{'screenshot','action-log','dom','accessibility'}}[run['condition']]
    if run['adapter_status']=='available':
        kinds={inputs[eid]['kind'] for eid in run['analysis_input_ids']}
        check(kinds==expected_kinds,'declared ablation condition does not match supplied analysis inputs')
    else:check(not results,'unsupported adapter cannot have scored results')
    for result in results.values():
        shape(result,{'case_id','status','actual','evidence_ids'})
        check(result['status'] in {'observed','unknown','harness-error'},'invalid result status')
        refs(result['evidence_ids'],inputs,nonempty=result['status']=='observed')
        if result['status']!='observed':check(result['actual'] is None,'unavailable result must be null')
    dimensions={}
    for dimension in sorted(DIMENSIONS):
        dimensions[dimension]={}
        for partition in ('recorded','held-out'):
            selected={k:v for k,v in cases.items() if v['dimension']==dimension and v['partition']==partition}
            metrics={'expected':len(selected),'matched':0,'missing':[],'wrong':[],'unsupported_claims':[],'unknown_correct':0,'harness_errors':[], 'scored':0}
            if run['adapter_status']=='available':
                for cid,case in selected.items():
                    result=results.get(cid)
                    if result and result['status']=='harness-error':metrics['harness_errors'].append(cid);continue
                    metrics['scored']+=1
                    if result is None:metrics['missing'].append(cid)
                    elif case['availability']=='unknown':
                        if result['status']=='unknown':metrics['unknown_correct']+=1;metrics['matched']+=1
                        else:metrics['unsupported_claims'].append(cid)
                    elif result['status']=='unknown':metrics['missing'].append(cid)
                    elif canonical(case['expected'])==canonical(result['actual']):metrics['matched']+=1
                    else:metrics['wrong'].append({'case_id':cid,'expected':case['expected'],'actual':result['actual']})
            metrics['score']=metrics['matched']/metrics['scored'] if metrics['scored'] else None
            dimensions[dimension][partition]=metrics
    return bounded({'schema_version':'interaction-evaluation/0.1','dataset':{'id':dataset['id'],'version':dataset['version'],'scope':dataset['scope']},
        'run_id':run['id'],'origin':run['origin'],'condition':run['condition'],'adapter_status':run['adapter_status'],'configuration':run['configuration'],
        'dimensions':dimensions,'invented_behavior_ids':sorted(set(results)-set(cases)),
        'limits':['Coverage denominator is this independent fixture only, not all states of a real website.',
                  'Structural citation validity is separate from semantic analysis accuracy.',
                  'Stored/deterministic results do not measure live-model quality; manifest integrity needs external byte verification.']})


def summarize_ux_runs(dataset, runs):
    reports=[evaluate_interactions(dataset,run) for run in array(runs,30)]
    check(bool(reports),'at least one run required')
    check(len({r['run_id'] for r in reports})==len(reports),'duplicate evaluation run ID')
    check(len({canonical(r['configuration']) for r in reports})==1,'ablation configuration differs beyond evidence condition')
    summary=[]
    for condition in sorted(CONDITIONS):
        selected=[r for r in reports if r['condition']==condition]
        summary.append({'condition':condition,'runs':len(selected),'available_runs':sum(r['adapter_status']=='available' for r in selected),
                        'scores':{d:{p:[r['dimensions'][d][p]['score'] for r in selected] for p in ('recorded','held-out')} for d in sorted(DIMENSIONS)}})
    return bounded({'schema_version':'interaction-ablation/0.1','reports':reports,'conditions':summary,'live_model_quality_measured':any(r['origin']=='live-model' and r['adapter_status']=='available' for r in reports)})

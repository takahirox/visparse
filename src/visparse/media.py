"""Offline, declaration-based media compatibility. No assets or providers run."""
from __future__ import annotations

import copy
from .contracts import bounded, canonical, check, number, shape
from .dna import feature_groups, group_status, validate_dna
from .render import export_policy

KINDS = {'photography', 'illustration', 'product-ui'}
CAPABILITY_STATES = {'available', 'unavailable', 'unknown'}


def validate_capabilities(value: dict) -> dict:
    bounded(value)
    shape(value, {'schema_version','kinds'})
    check(value['schema_version']=='0.1','unsupported capability version')
    shape(value['kinds'],set(),KINDS)
    check(all(isinstance(v,str) and v in CAPABILITY_STATES for v in value['kinds'].values()),'invalid capability state')
    return value


def _property(group, threshold, safe):
    status=group_status(group,threshold) if group else 'missing'
    result={'status':status,'value':group[0]['value'] if status=='known' else None,
            'origins':sorted({f['origin'] for f in group}),
            'confidence':min((f['confidence'] for f in group if f['confidence'] is not None),default=None)}
    if not safe:
        result.update(evidence_ids=sorted({eid for f in group for eid in f['evidence_ids']}),
                      methods=sorted({f['method'] for f in group}),
                      uncertainty=sorted({f['uncertainty'] for f in group if 'uncertainty' in f}))
    return result


def media_requirements(dna: dict, *, intent='preserve', min_confidence=0.6, generation_safe=False) -> dict:
    validate_dna(dna)
    policy=export_policy(intent)
    number(min_confidence,0,1)
    scopes={}
    for group in feature_groups(dna).values():
        f=group[0]
        if f['name'].startswith('imagery.'):
            key=canonical(f['scope'])
            scopes.setdefault(key,{'scope':f['scope'],'groups':{}})['groups'][f['name']]=group
    rows=[]
    aliases={s:f'role-{i}' for i,s in enumerate(sorted({v['scope']['subject'] for v in scopes.values()}),1)}
    for index,key in enumerate(sorted(scopes),1):
        entry=scopes[key];scope=copy.deepcopy(entry['scope'])
        if generation_safe:
            # Only neutral role aliases and mechanically bounded viewport labels leave this export.
            import re
            scope['subject']=aliases[scope['subject']]
            if not re.fullmatch(r'[0-9]{1,4}x[0-9]{1,4}',scope['viewport']):scope['viewport']='unspecified'
            if scope['state'] not in {'default','hover','focus','active','disabled'}:scope['state']='supplied-state'
        properties={name:_property(entry['groups'].get(name,[]),min_confidence,generation_safe)
                    for name in ('imagery.kind','imagery.prominence','imagery.treatment','imagery.framing','imagery.text_space','imagery.subject_arrangement')}
        rows.append({'id':f'media-{index}','scope':scope,'properties':properties,
                     'preservation':{'basis':'export_policy','level':'preserve-kind' if intent=='preserve' else 'adaptable',
                         'importance_basis':'scoped feature when supplied; never inferred from media kind alone'}})
    return bounded({'schema_version':'0.1','export_policy':policy,'requirements':rows,
        'gaps':[] if rows else ['No typed media characteristics supplied; analysis or export coverage is unknown.']})


def assess_media(dna: dict, capabilities: dict, *, intent='preserve', min_confidence=0.6,
                 generation_safe=False, generated: dict | None = None) -> dict:
    validate_capabilities(capabilities)
    report=media_requirements(dna,intent=intent,min_confidence=min_confidence,generation_safe=False)
    generated_rows={}
    if generated is not None:
        for row in media_requirements(generated,intent=intent,min_confidence=min_confidence)['requirements']:
            generated_rows[canonical(row['scope'])]=row
    results=[]
    for row in report['requirements']:
        kind=row['properties']['imagery.kind'];value=kind['value'];findings=[]
        declared=capabilities['kinds'].get(value,'unknown') if value else 'unknown'
        if kind['status']=='not_applicable' or value=='absent':
            status='not_applicable';reason='No media-kind requirement for this scope.'
        elif kind['status']!='known' or value=='mixed':
            status='unknown';reason='Media kind needs supported region-level evidence; mixed media is not a single capability.'
            findings.append({'category':'analysis_or_guidance_gap','certainty':'undetermined',
                             'possible_causes':['analysis_omission','guidance_omission']})
        elif declared=='unavailable':
            status='mismatch' if intent=='preserve' else 'tradeoff'
            reason='Declared capabilities cannot preserve the supported media kind.'
            findings.append({'category':'generator_capability','certainty':'declared'})
        elif declared=='available':
            status='compatible_declared';reason='Capability is declared, but asset suitability and reproduction are unverified.'
        else:
            status='unknown';reason='No definite capability declaration; absence is not failure.'
        if generated is not None:
            actual=generated_rows.get(canonical(row['scope']),{}).get('properties',{}).get('imagery.kind',{})
            if kind['status']=='known' and actual.get('status')=='known' and value!=actual['value']:
                findings.append({'category':'generation_deviation','certainty':'represented_difference',
                                 'reference_kind':value,'generated_kind':actual['value']})
            elif actual.get('status')!='known':
                findings.append({'category':'generation_evidence_gap','certainty':'undetermined'})
        results.append({'id':row['id'],'status':status,'declared_capability':declared,'reason':reason,
                        'findings':findings,'fallback':{'compromise':True,
                        'guidance':'A replacement media kind changes appearance; the caller must choose and record that tradeoff.'} if status in {'mismatch','tradeoff'} else None})
    if generation_safe:
        report=media_requirements(dna,intent=intent,min_confidence=min_confidence,generation_safe=True)
    report['assessment']=results
    report['limitations']=['Declarations do not verify available assets or visual fidelity.',
        'Compatible media kind does not establish matching framing, quality, or composition.',
        'Cause categories are not exclusive; omissions cannot be attributed from missing data alone.',
        'No assets are selected, fetched, generated, or substituted by this checker.']
    return bounded(report)

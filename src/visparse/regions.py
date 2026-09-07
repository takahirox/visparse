"""Ground explicit inferred regions in existing evidence; never guess CSS geometry."""
import copy
import re
from .contracts import check, items, number, refs, shape, text, unique
from .dna import validate_dna


def scope_regions(dna: dict, regions: list) -> dict:
    validate_dna(dna)
    result = copy.deepcopy(dna)
    anchors = {e['id']: e for e in dna['evidence']}
    occupied = {v['id'] for key in ('sources','evidence','features','principles') for v in dna[key]}
    for region in unique(regions).values():
        shape(region, {'id','viewport','state','evidence_ids','confidence','method','uncertainty'})
        check(re.fullmatch(r'[a-z][a-z0-9-]{0,63}',region['id']) is not None,'invalid region ID')
        refs(region['evidence_ids'],anchors)
        number(region['confidence'],0,1)
        for name in ('method','uncertainty','viewport','state'): text(region[name])
        support=[anchors[eid] for eid in region['evidence_ids']]
        for evidence in support:
            check(all(evidence['scope'][k]==region[k] for k in ('viewport','state')),'region cannot invent viewport/state')
            if evidence['kind']=='inferred':
                check(region['confidence']<=evidence['confidence'],'region confidence exceeds evidence')
        eid='region:'+region['id']
        check(eid not in occupied,'region evidence ID collision')
        occupied.add(eid)
        result['evidence'].append({'id':eid,'source_ids':sorted({s for e in support for s in e['source_ids']}),
            'kind':'inferred','confidence':region['confidence'],
            'scope':{'subject':region['id'],'viewport':region['viewport'],'state':region['state']},
            'statement':'Inferred region grounded in supplied evidence.',
            'details':{'supporting_evidence_ids':region['evidence_ids'],'method':region['method'],'uncertainty':region['uncertainty']}})
    return validate_dna(result)

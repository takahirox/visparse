"""Diagnostic retention trace using the renderer's actual selection rules."""
from __future__ import annotations

from collections import Counter

from .contracts import bounded, number
from .dna import feature_groups, group_status, validate_dna
from .render import export_policy, feature_export_status, principle_export_status


def _ancestry(evidence: dict, roots: list[str]) -> tuple[list[str], list[str]]:
    visited, issues = set(), set()
    active = set()
    stack = [(root, False) for root in roots]
    while stack:
        eid, leaving = stack.pop()
        if leaving:
            active.discard(eid)
            continue
        if eid in active:
            issues.add('cyclic_support_metadata')
            continue
        if eid in visited:
            continue
        if eid not in evidence:
            issues.add('unresolved_support_metadata')
            continue
        visited.add(eid)
        active.add(eid)
        stack.append((eid, True))
        links = evidence[eid]['details'].get('supporting_evidence_ids', [])
        if not isinstance(links, list) or any(not isinstance(ref, str) for ref in links):
            issues.add('malformed_support_metadata')
            continue
        stack.extend((ref, False) for ref in links)
    return sorted(visited), sorted(issues)


def trace_guidance(dna: dict, *, min_confidence: float = 0.6, generation_safe: bool = False,
                   intent: str = 'adapt') -> dict:
    """Diagnostic IDs/scopes are retained even when tracing safe export decisions."""
    validate_dna(dna)
    number(min_confidence, 0, 1)
    policy = export_policy(intent)
    evidence = {e['id']: e for e in dna['evidence']}
    groups, used = [], set()
    for key, group in sorted(feature_groups(dna).items()):
        first = group[0]
        direct = sorted({eid for f in group for eid in f['evidence_ids']})
        ancestors, issues = _ancestry(evidence, direct)
        used.update(ancestors)
        groups.append({'name': first['name'], 'scope': first['scope'],
            **({'relative_to': first['relative_to']} if 'relative_to' in first else {}),
            'feature_ids': sorted(f['id'] for f in group), 'evidence_ids': direct,
            'ancestry_evidence_ids': ancestors, 'ancestry_issues': issues,
            'source_ids': sorted({s for eid in ancestors for s in evidence[eid]['source_ids']}),
            'group_status': group_status(group, min_confidence),
            'export_status': feature_export_status(group, min_confidence, generation_safe),
            'features': [{'id': f['id'], 'status': f['status'], 'origin': f['origin'],
                          'confidence': f['confidence']} for f in sorted(group, key=lambda f: f['id'])]})
    principles = [{'id': p['id'], 'evidence_ids': p['evidence_ids'],
                   'export_status': principle_export_status(p, min_confidence, generation_safe, intent)}
                  for p in sorted(dna['principles'], key=lambda p: p['id'])]
    counts = Counter(g['export_status'] for g in groups)
    return bounded({'schema_version': '0.1', 'export_policy': policy,
        'target_export': {'generation_safe': generation_safe, 'min_confidence': min_confidence},
        'counts': {'raw_features': len(dna['features']), 'feature_groups': len(groups),
                   'retained_groups': counts['retained'], 'excluded_groups': len(groups) - counts['retained'],
                   'group_export_statuses': dict(sorted(counts.items()))},
        'groups': groups, 'principles': principles,
        'evidence_without_feature_lineage': sorted(set(evidence) - used),
        'limitations': ['This diagnostic includes original IDs and scopes; it is not a generation-safe artifact.',
                       'Evidence need not yield a feature. Retention does not establish correctness or visual fidelity.',
                       'Supporting-evidence metadata is traversed as declared; ancestry issues are reported, not repaired.']})

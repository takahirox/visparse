"""Audit extraction coverage against explicit, evidence-linked expectations."""
from __future__ import annotations

from collections import Counter

from .contracts import bounded, check, number, refs, shape, text, unique
from .dna import FEATURES, feature_key, group_status, validate_dna, validate_scope


def audit_coverage(dna: dict, expectations: dict, *, min_confidence: float = 0.6) -> dict:
    """Source availability is a caller declaration, never guessed from prose."""
    validate_dna(dna)
    bounded(expectations)
    number(min_confidence, 0, 1)
    shape(expectations, {'schema_version', 'items'})
    check(expectations['schema_version'] == '0.1', 'unsupported coverage version')
    evidence = unique(dna['evidence'])
    rows = []
    keys = set()
    for item in unique(expectations['items']).values():
        shape(item, {'id', 'name', 'scope', 'source_status', 'evidence_ids'}, {'relative_to'})
        text(item['name'])
        check(item['name'] in FEATURES, 'unsupported expected feature')
        validate_scope(item['scope'])
        text(item['source_status'])
        check(item['source_status'] in {'supported', 'absent', 'unknown'}, 'invalid source status')
        refs(item['evidence_ids'], evidence, nonempty=True)
        check(all(evidence[eid]['scope'] == item['scope'] for eid in item['evidence_ids']),
              'expectation/evidence scope mismatch')
        target = item.get('relative_to')
        if item['name'] == 'layout.relative_position':
            check(isinstance(target, str) and target != item['scope']['subject'], 'invalid relationship target')
            check(any(e['scope'] == {**item['scope'], 'subject': target} for e in evidence.values()),
                  'relationship target missing in same viewport/state')
        else:
            check(target is None and 'relative_to' not in item, 'relative_to requires relationship')
        key = (item['name'], tuple(sorted(item['scope'].items())), target)
        check(key not in keys, 'duplicate scoped expectation')
        keys.add(key)
        features = [f for f in dna['features'] if f['name'] == item['name'] and f['scope'] == item['scope']
                    and f.get('relative_to') == target]
        # Relationships can legitimately occupy separate axes; do not merge them.
        groups = {}
        for feature in features:
            groups.setdefault(feature_key(feature), []).append(feature)
        statuses = sorted({group_status(g, min_confidence) for g in groups.values()})
        if not features:
            status = {'supported': 'extraction_gap', 'absent': 'source_absent',
                      'unknown': 'source_unknown'}[item['source_status']]
        elif item['source_status'] == 'absent':
            status = 'declaration_conflict' if any(f['status'] == 'known' for f in features) else 'source_absent'
        elif 'conflict' in statuses:
            status = 'conflict'
        elif 'low_confidence' in statuses:
            status = 'low_confidence'
        elif 'unknown' in statuses:
            status = 'explicit_unknown'
        elif all(s == 'not_applicable' for s in statuses):
            status = 'not_applicable'
        elif 'not_applicable' in statuses:
            status = 'partial'
        else:
            status = 'covered' if item['source_status'] == 'supported' else 'source_unknown'
        rows.append({**item, 'status': status, 'feature_ids': sorted(f['id'] for f in features),
                     'group_statuses': statuses})
    return bounded({'schema_version': '0.1', 'min_confidence': min_confidence,
                    'counts': dict(sorted(Counter(r['status'] for r in rows).items())), 'items': rows,
                    'limitations': ['Source availability is declared by the caller, not verified from prose.',
                                    'Coverage does not establish correctness or visual fidelity.']})

"""Stable neutral labels shared by generation-facing exports."""
import re

STATES = {'default', 'hover', 'focus', 'active', 'disabled'}


def scope_labels(dna: dict) -> dict:
    scopes = [item['scope'] for key in ('evidence', 'features') for item in dna[key]]
    return {key: {value: f'{prefix}-{i}' for i, value in
                  enumerate(sorted({scope[key] for scope in scopes}), 1)}
            for key, prefix in [('subject', 'role'), ('viewport', 'viewport'), ('state', 'state')]}


def safe_subject(subject: str, labels: dict) -> str:
    return subject if re.fullmatch(r'(?:page|visible-sample:tag=[a-z][a-z0-9]*)', subject) else labels['subject'][subject]


def safe_scope(scope: dict, labels: dict) -> dict:
    return {'subject': safe_subject(scope['subject'], labels),
            'viewport': scope['viewport'] if re.fullmatch(r'[0-9]{1,4}x[0-9]{1,4}', scope['viewport']) else labels['viewport'][scope['viewport']],
            'state': scope['state'] if scope['state'] in STATES else labels['state'][scope['state']]}

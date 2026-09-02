# Visparse

Visparse 0.1 is a small, dependency-free Python library for recording visual analysis without blurring evidence and inference. It validates schema-versioned JSON, emits canonical JSON, exposes a provider-neutral analyzer boundary, and includes deterministic evaluation tools.

A record keeps these layers distinct:

- `sources`: captured evidence and stable locators
- `measurements`: deterministic values, methods, and units
- `observations`: statements directly supported by named sources
- `interpretations`: explicitly inferred meaning linked to observations
- `confidence`: bounded confidence plus uncertainty and basis
- `interactions`: web, UI, or temporal events
- `provenance`: who or what created the record and its inputs

No interpretation is promoted to a measurement. Validation rejects broken references, malformed confidence, unsafe JSON shapes, duplicate keys, and oversized input.

## Quick start

```sh
PYTHONPATH=src python examples/basic.py
PYTHONPATH=src python -m visparse validate examples/evaluation_fixture.json
```

The second command intentionally fails because an evaluation fixture is not itself a record. Evaluate it with:

```sh
PYTHONPATH=src python -m visparse evaluate examples/evaluation_fixture.json
```

Other commands are `normalize` and `summarize`; each accepts a path or `-` for standard input. Normalization writes UTF-8 canonical JSON with sorted keys and no insignificant whitespace.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests examples
```

See `docs/architecture.md` for scope and trust boundaries and `docs/evaluation.md` for the inspectable evaluation method.

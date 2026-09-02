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

The CLI commands are `analyze`, `validate`, `normalize`, `summarize`, and `evaluate`. Commands that consume JSON accept a path or `-` for standard input. Normalization writes UTF-8 canonical JSON with sorted keys and no insignificant whitespace.

## Analyze an image end to end

Image analysis uses an installed and authenticated local Codex CLI with its saved ChatGPT/Codex login. This adapter does not require an OpenAI API key.

```sh
PYTHONPATH=src python -m visparse analyze screenshot.png > analysis.json
PYTHONPATH=src python -m visparse validate analysis.json
PYTHONPATH=src python -m visparse summarize analysis.json
```

Use a common image input such as PNG or JPEG. Input reading is bounded by `MAX_INPUT_BYTES`, and an oversized file is rejected before analysis; support for every image format is not claimed.

Successful commands write canonical JSON only to standard output. Diagnostics and errors go to standard error, and failures return a nonzero status. Analyzer errors are not hidden or repaired, and model accuracy is not guaranteed.

For an optional manual live test, check the local CLI and authenticate if needed:

```sh
codex --version
codex login
```

Run `codex login` only when authentication is needed, then run the three-command workflow above.

Automated tests mock the runner and require neither a live Codex session nor network access.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests examples
```

See `docs/architecture.md` for scope and trust boundaries and `docs/evaluation.md` for the inspectable evaluation method.

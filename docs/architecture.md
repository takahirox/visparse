# Architecture and scope

Visparse 0.1 has four deliberately small layers.

1. `model.py` defines the schema contract, including file-backed `SourceEvidence`, bounded JSON and source reads, reference checks, canonical serialization, and structural summaries.
2. `analyzer.py` defines the provider-neutral `Analyzer` boundary and `run_analyzer`; `codex.py` supplies the first concrete adapter and a mockable `ProcessRunner`.
3. `evaluation.py` runs inspectable JSON cases with exact validity and summary expectations, plus analyzer cases that can run offline with a fake process runner.
4. `cli.py` constructs file-backed source evidence; the `analyze` command currently selects `CodexAnalyzer` and emits adapter output as canonical JSON for scripts after its `run_analyzer` validation.

Providers remain outside the schema:

```text
Analyzer
├── CodexAnalyzer (optional, current)
├── future API adapter
└── future local adapter
```

Adding an API or local adapter does not require a core schema change; every adapter returns the same validated canonical record.

## Trust boundaries

Source files, source payloads, and analyzer JSON are untrusted. Byte size, nesting, container size, string length, numeric finiteness, duplicate keys, required fields, and cross-references are checked before use.

The analyzer trust flow is:

```text
bounded image bytes -> Codex untrusted JSON -> validate_record/run_analyzer source identity -> canonical record
```

`SourceEvidence` reads only a bounded number of bytes from a file and identifies those exact bytes with a SHA-256 locator. The digest is a privacy-safe locator: it binds the record to content without placing the local path in the record.

`CodexAnalyzer` writes the bounded bytes to a private `0600` temporary image and removes it in `finally`. Its `ProcessRunner` starts Codex as a shell-free subprocess, so source names and paths are never interpreted by a shell.

The adapter relies on the user's locally saved Codex authentication; it requires no API key. Each invocation is ephemeral and read-only. The final JSON record is read from stdout, while stderr is retained for diagnostics. Timeouts and failures are mapped to stable error families rather than leaking provider-specific process behavior into the core.

Codex output is never trusted merely because the process succeeded. `validate_record` checks the complete record, and `run_analyzer` checks that its source identity matches the supplied `SourceEvidence` before canonicalization. Neither layer repairs semantic categories: an observation, interpretation, interaction, or measurement must already be represented as such by the analyzer.

The schema separates captured evidence from claims:

```text
source -> measurement (method + scalar value)
source -> observation (direct statement)
observation -> interpretation -> confidence (uncertainty + basis)
source -> interaction (web, UI, or temporal event)
```

A summary reports only counts and declared kinds. It does not decide what an image means. In particular, interpretations remain interpretations even at confidence 1.0.

## Evaluation

Evaluation keeps deterministic schema cases and exercises the Codex adapter offline through a fake `ProcessRunner`. Tests cover successful stdout JSON, stderr diagnostics, timeouts, stable error families, source-identity rejection, temporary-file permissions, and cleanup without requiring Codex, network access, or credentials.

## Non-goals

The core does not decode images, perform computer vision, fetch URLs, drive browsers, or embed provider behavior. The optional first adapter invokes Codex, but Codex itself—not the core—interprets image bytes.

Codex uses existing local authentication, so Visparse imposes no mandatory API billing. Version 0.1 ships no additional API or local providers; the provider-neutral boundary only keeps those future adapters from forcing schema changes.

Model judgments are never deterministic measurements, regardless of confidence. Visparse has no Refloom coupling or third-party runtime dependencies, and persistence, media decoding, and richer domain vocabularies remain outside this core.

Schema changes require a new `schema_version`; consumers should reject unknown versions rather than guess.

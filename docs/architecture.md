# Architecture and scope

Visparse 0.1 has four deliberately small layers.

1. `model.py` defines the schema contract, bounded JSON decoding, reference checks, canonical serialization, and structural summaries.
2. `analyzer.py` defines a provider-neutral boundary. Implementations receive opaque source evidence and must return a complete validated record.
3. `evaluation.py` runs inspectable JSON cases with exact validity and summary expectations.
4. `cli.py` exposes the same deterministic operations to scripts.

## Trust boundaries

Source payloads and JSON are untrusted. Byte size, nesting, container size, string length, numeric finiteness, duplicate keys, required fields, and cross-references are checked before use. Analyzer output is also untrusted and is validated, including the identity of the supplied source.

The schema separates captured evidence from claims:

```text
source -> measurement (method + scalar value)
source -> observation (direct statement)
observation -> interpretation -> confidence (uncertainty + basis)
source -> interaction (web, UI, or temporal event)
```

A summary reports only counts and declared kinds. It does not decide what an image means. In particular, interpretations remain interpretations even at confidence 1.0.

## Non-goals

Version 0.1 does not fetch URLs, decode images, drive browsers, call models, choose a provider, or claim that inferred semantics are measured facts. It has no Refloom coupling and no third-party runtime dependencies. Persistence, media processing, model adapters, and richer domain vocabularies belong outside this core until concrete compatibility requirements exist.

Schema changes require a new `schema_version`; consumers should reject unknown versions rather than guess.

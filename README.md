# Visparse

Visparse 0.1 is a small, dependency-free Python library for recording visual and interactive-experience analysis without blurring evidence and inference. It validates schema-versioned JSON, emits canonical JSON, exposes provider-neutral boundaries, and includes deterministic evaluation tools.

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

The evidence CLI commands include `analyze`, `analyze-design`, `inspect`, `inspect-summary`, `inspect-capabilities`, `validate`, `normalize`, `summarize`, and `evaluate`; the design workflow commands are described below. Commands that consume JSON accept a path or `-` for standard input. Normalization writes UTF-8 canonical JSON with sorted keys and no insignificant whitespace.

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

## Transfer design language between sites

`analyze-design` turns one or more reference-site screenshots into a provider-neutral design profile. It records directly visible observations separately from interpretations, then links transferable principles and recommendations back to that evidence.

```sh
# One reference viewport, with general improvement recommendations
PYTHONPATH=src python -m visparse analyze-design reference-desktop.png > design-profile.json

# Infer cross-viewport consistency and adapt principles to a separate target site
PYTHONPATH=src python -m visparse analyze-design \
  reference-desktop.png reference-tablet.png reference-mobile.png \
  --target target-desktop.png --target target-mobile.png \
  > design-profile.json
```

The profile vocabulary covers layout, visual hierarchy, spacing and density, typography, color usage, component styling, UI patterns, section rhythm, navigation, imagery, design tone, strengths, and weaknesses. Recommendations must declare `transfer_mode: "principle"` and an explicit guard against copying assets, branding, content, or implementation. They are improvement guidance—not clone instructions or reconstructed CSS/DOM.

The public API exposes `DesignAnalyzer`, `run_design_analyzer`, `CodexDesignAnalyzer`, `validate_design_profile`, `normalize_design_profile`, and `summarize_design_profile`. This permits future API-backed or local VLM adapters to reuse the same output contract.

Screenshot input is intentionally sufficient for this first design-analysis milestone. Multiple viewports can reveal visual consistency and responsive tendencies, but cannot establish hidden states, exact breakpoints, semantic DOM structure, computed CSS, or accessibility metadata. Those signals may be added later as optional evidence rather than prerequisites.

## Inspect supplied web and interactive evidence

External agents and collectors can submit bounded JSON captures for DOM, computed CSS, accessibility, runtime, screenshots, video, canvas, WebGL, and high-level Three.js state. Visparse validates grounding and keeps exact measurements, runtime observations, visual observations, and interpretations in separate arrays.

```sh
PYTHONPATH=src python -m visparse inspect capture-bundle.json
PYTHONPATH=src python -m visparse inspect-summary capture-bundle.json
PYTHONPATH=src python -m visparse inspect-capabilities
```

These commands consume already collected evidence. They do not fetch a URL, launch or automate a browser, execute page code, or pretend that unavailable signals were observed. The public `inspect_snapshot` and `inspection_capabilities` functions form a deterministic, model-independent boundary suitable for a later MCP wrapper.

Three.js support is progressive: generic canvas and WebGL evidence remains useful, explicit runtime metadata can report Three.js as detected, and a supplied `threejs` capture can carry high-level scene, camera, light, material, and object inventories. Detection never fabricates a scene graph.

See `docs/inspection.md` for the bundle contract, grounding rules, and tool-wrapping guidance.

## Normalize and evaluate reusable design knowledge

Design DNA preserves typed features, evidence, scope, uncertainty, and transferable
principles. The optional browser collector supplies exact CSS and geometry alongside
screenshots and accessibility evidence. Core commands remain dependency-free.

```sh
visparse design-normalize design-profile.json > design-dna.json
visparse design-render design-dna.json > DESIGN.md
visparse design-compare reference-dna.json generated-dna.json
visparse eval-analysis examples/design/analysis-fixture.json
visparse design-roundtrip examples/design/roundtrip-fixture.json
```

Install `.[collector]` and Chromium to use `visparse-collector capture URL`.
See [the design workflow](docs/design-workflow.md) for installation, complete
contracts, generation exports, neutral briefs, and evaluation methodology. The
checked-in benchmark predictions and annotations are synthetic regression fixtures.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests examples
```

See `docs/architecture.md` for scope and trust boundaries and `docs/evaluation.md` for the inspectable evaluation method.

### Extraction confidence

Semantic confidence estimates whether a scoped claim is correct given the supplied
content. Missing (`null`) confidence on observed or measured evidence is unspecified,
not zero and not certainty. The extractor must assign its own justified confidence.
Only inferred supporting evidence imposes a numeric ceiling, including an inferred
region used as a feature's anchor. A real zero remains zero; unknown properties use
`status: unknown` and a null value. Validation never repairs or raises predictions.
The extraction prompt follows this contract. Offline regressions verify the contract
and retained guidance; they do not prove calibration or guarantee live model behavior.

### Scoped coverage audit

`visparse design-coverage dna.json --expectations expectations.json` audits an
explicit checklist without a model call. An expectations file has
`{"schema_version":"0.1","items":[{"id":"hero-kind","name":"imagery.kind","scope":{"subject":"hero","viewport":"1440x900","state":"default"},"source_status":"supported","evidence_ids":["region:hero"]}]}`.
Each item must cite existing evidence in exactly the same scope; relationships also
supply `relative_to`. Use `supported` when the cited content supplies the property,
`absent` when the inspected evidence lacks it, or `unknown` when availability is
undetermined. These are caller declarations, not automatic judgments about prose.

The report separates `extraction_gap`, `source_absent`, `source_unknown`,
`explicit_unknown`, `low_confidence`, `conflict`, `not_applicable` and `covered`.
A known prediction against declared absence is a `declaration_conflict`. Relationship
axes are audited separately before summarizing the expectation; mixed applicability
is `partial`. Counts measure extraction coverage, not correctness or export retention.
Empty checklists do not establish completeness. Screenshot instructions now request
visible line/element counts and region relationships; precise numeric geometry still
requires a measurement channel and is never invented by the semantic extractor.

### Region boundaries

Extraction prefers existing specific evidence scopes. Page-level observations may
still ground several separately named regions, but combining distinct named subjects
into one inferred region or collapsing a named subject to `page` is rejected. A
single-subject alias is allowed unless it collides with a different existing subject
in the same viewport/state. Region errors are validation failures, not feature
conflicts; different regions may legitimately use different emphasis values. Actual
same-region contradictions remain visible. These checks protect explicit boundaries;
they cannot verify a model's interpretation of regions described only in prose.

### Guidance retention trace

`visparse design-trace dna.json --intent preserve --generation-safe` explains the
renderer selection at the same confidence threshold. It reports raw feature counts,
feature-group counts, retained/excluded groups, per-feature status/confidence, direct
and ancestral evidence IDs, source IDs, and exclusion reasons. It also traces
principle filtering. `--generation-safe` selects the target renderer behavior; the
**trace itself is diagnostic and still contains original IDs and scopes**. Do not
provide it as a sanitized generator input.

Supporting-evidence metadata is followed without interpreting source prose. Missing,
malformed or cyclic links are reported rather than repaired. Evidence outside feature
lineage is listed separately; observations and policies need not yield features.
Grouping precedes safe-label projection so redaction cannot manufacture conflicts.
Coverage and retention are separate: a supported free-text feature can be covered but
filtered from safe guidance. Neither establishes visual fidelity.
Distinct nonstandard states and viewports receive distinct neutral labels, rather than
being collapsed into one unspecified label. Original labels do not leave safe guidance.

### Media limitations in generation input

Pass `--capabilities capabilities.json` to `design-render` to include declared media
compatibility in DESIGN.md. `design-export --capabilities ...` now includes the same
findings inside `design_md`, which is an allowed generator input, as well as its
structured diagnostic report. Without this option, rendering is unchanged.

For example, `{"schema_version":"0.1","kinds":{"photography":"unavailable","illustration":"available"}}`
produces a preservation `mismatch` for supported photographic media, or an adaptation
`tradeoff`. Guidance requires any chosen substitution and its expected appearance
change to be recorded; it does not select assets or a substitute automatically.
Unknown results distinguish missing, low-confidence, conflicting, explicitly unknown
and mixed media kinds from missing capability declarations. They do not turn rejected
features into requirements. Safe Markdown and media reports share neutral scope labels,
so a role refers to the same subject in both. Declared availability does not verify
suitable assets, composition or visual fidelity. `design-trace` covers feature and
principle selection; these optional capability notes are reported by `design-media-check`.

Live `design-extract` calls default to a 300-second timeout. Use
`--timeout-seconds 450` to choose a finite limit from 1 through 900 seconds; the
Python `CodexSemanticExtractor(timeout_seconds=...)` uses the same bounds. Rich
extractions in the two-site regression check took about 241–246 seconds, exceeding
the previous 180-second default. A larger timeout does not guarantee completion.
Timeouts terminate the call and are reported without retry, allowance reset, purchase
or provider/model switch. Stored `--predictions` remain offline and ignore this option.

### Preservation-oriented screenshot observations

Use `visparse analyze-design screenshot.png --intent preserve` when the next step
is visual reconstruction. This mode inventories visible regions, small identity
labels and overlays, repeated control counts, headline line counts, relative
placement/scale, and light/dark color distinctions. It describes roles instead of
transcribing source branding. Unknown geometry is not invented or represented as
mechanical measurement. The profile schema and default `adapt` intent are unchanged.

Analysis uses only supplied images, with apps, plugins, memories, repository
instructions and web search disabled. `--timeout-seconds` defaults to 300 and accepts
finite values from 1 to 900. Invalid API configurations fail before launching the
provider. Screenshot analysis does not automatically retry or spend extra allowance.

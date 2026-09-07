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

# Design evidence, transfer, and evaluation

The design workflow turns supplied evidence into versioned Design DNA, renders
implementation guidance, and evaluates both analysis quality and downstream
transfer. Core operations are deterministic and dependency-free. Browser
execution lives in the optional `visparse_collector` package; generation and
model inference remain external.

```text
reference screenshots ── analyze-design ── Design Profile ─┐
                                                        ├─ design-normalize ─ Design DNA
explicit URL ── optional collector ── inspection bundle ──┘                       │
                                                                    design-render
                                                                               │
                                                                          DESIGN.md
                                                                               │
                                                       external isolated generation
                                                                               │
                                                      collect/analyze generated page
                                                                               │
                                                               design-compare / design-roundtrip

stored analysis predictions + evidence + human labels ── eval-analysis
```

## Commands

```sh
visparse design-normalize design-profile.json > design-dna.json
visparse design-normalize --inspection capture.json > measured-dna.json
visparse design-normalize design-profile.json --inspection capture.json \
  --annotations annotations.json --contexts contexts.json > enriched-dna.json
visparse design-validate design-dna.json
visparse design-render design-dna.json --mode compact > DESIGN.md
visparse design-render design-dna.json --mode full > DESIGN-full.md
visparse design-compare reference-dna.json generated-dna.json
visparse eval-analysis examples/design/analysis-fixture.json
visparse design-roundtrip examples/design/roundtrip-fixture.json
visparse design-export examples/design/reference-dna.json \
  --brief examples/briefs/dashboard.md > generation-input.json
```

JSON commands accept `-` for stdin; at most one input per invocation should use
stdin. Output is JSON except `design-render`, which emits Markdown. Errors go to
stderr with status 2. Quality evaluation commands return 0 for a completed report
even when predictions are incorrect: scores are data, not implicit pass/fail
thresholds. The existing `evaluate` command retains its contract-test exit codes.

## Design DNA 0.1

The independent DNA schema and vocabulary are both versioned `0.1`; existing
Design Profile and inspection schemas are unchanged. Unknown versions and
unknown feature names are rejected. `src/visparse/dna.py:FEATURES` is the normative
vocabulary, including dimensions, units, categorical values, and default
comparison tolerances. Consumers can inspect this registry without a provider.

Top-level fields are `schema_version`, `vocabulary_version`, `sources`, `evidence`,
`features`, `principles`, `gaps`, and `provenance`. See the checked-in
[`reference-dna.json`](../examples/design/reference-dna.json) for a complete example.

Every feature contains:

| Field | Meaning |
| --- | --- |
| `id`, `name` | Unique feature identity and versioned vocabulary key |
| `value`, `unit` | Typed scalar; unit is `px`, `ratio`, or null as defined by the vocabulary |
| `status` | `known`, `unknown`, or `not_applicable`; the latter two require null values |
| `origin` | `measured`, `observed`, or `inferred`, independently of which provider produced it |
| `confidence` | 0–1 for inferred known values; optional for mechanically sourced facts |
| `scope` | Explicit `viewport`, `state`, and `subject` strings |
| `evidence_ids` | References to supporting evidence in this DNA |
| `method` | How the value was derived |

Evidence retains source IDs, origin, statement, confidence, scope, and original
details. Mechanical CSS strings are observations, because the existing numeric
measurement contract does not accept font names or CSS strings. Derived numeric
medians and fractions retain the collector method, denominator, node IDs, and
sampling coverage. Schema validation checks structure and links; it does not
attest that supplied facts are true.

Features with the same name/scope remain separate. Different values or statuses
produce a conflict during rendering/comparison; there is no silent averaging of
contradictory captures. Unknown differs from observed absence: a measured shadow
fraction of zero is known, while an unavailable shadow sample is missing/unknown.
Inferences cannot become measurements or acquire confidence greater than their
supporting inference. Source observations remain observations after normalization.

### Profile projection and explicit annotations

`build_dna(profile, inspection=..., annotations=..., contexts=...)` projects only
recognized numeric measurement names mechanically. It retains reference-only
observations and interpretations as evidence, and preserves reference-only
principles as qualified `SHOULD` guidance. Unmapped prose is reported in `gaps`;
the normalizer never guesses a score or category from wording. Target-specific
recommendations and target/mixed-source claims are excluded from reference DNA.

The optional contexts JSON maps namespaced source or evidence IDs to scopes:

```json
{
  "profile:reference-1": {"viewport":"1440x900","state":"default","subject":"page"},
  "profile:observation-hero": {"viewport":"1440x900","state":"default","subject":"hero"}
}
```

Evidence-specific scopes override source scopes. Unspecified input uses
`unspecified/default/page`, an explicit lack of detailed context. Multi-source
claims with different declared scopes require an explicit evidence scope mapping.
Responsive transformation annotations can use a scoped transition label such as
`1440x900->390x844`; the caller must map the supporting evidence to that transition.

Annotations are a versioned sidecar with `features` and `constraints` arrays:

```json
{
  "schema_version": "0.1",
  "features": [{
    "name": "layout.hero_pattern", "value": "asymmetric", "unit": null,
    "status": "known", "scope": {"viewport":"1440x900","state":"default","subject":"hero"},
    "evidence_ids": ["profile:observation-hero"], "confidence": 0.8,
    "method": "Designer annotation using the 0.1 vocabulary"
  }],
  "constraints": []
}
```

Every sidecar feature is inferred. This supports a human or an external VLM's
structured predictions without disguising semantic enrichment as deterministic
normalization. A constraint has `statement`, `scope`, `evidence_ids`, `confidence`,
`strength`, and `author`. Only such explicit transfer policies may use `MUST` or
`NEVER`; policy attribution is retained in gaps. Policy constraints describe the
caller's requested adaptation, not newly established facts about the source.

### Inspection integration

The normalizer understands the collector payload contract described below;
generic opaque inspection payloads produce an explicit unsupported gap. Profile
IDs are prefixed `profile:` and collector IDs `capture:`. When both inputs are
supplied, every projected collector screenshot must match a reference artifact
locator or SHA-256 identity. `file:sha256:DIGEST` and `artifact:sha256:DIGEST` match
the same content. Unrelated screenshots cannot silently enrich a reference DNA.
The source records remain distinct so their original provenance is inspectable.

## Optional collector 0.1

```sh
python -m pip install '.[collector]'
python -m playwright install chromium
visparse-collector capture https://example.com \
  --viewport 1440x900 --viewport 390x844 --screenshots ./artifacts > capture.json
visparse inspect capture.json
visparse design-normalize --inspection capture.json > design-dna.json
```

The collector uses [Playwright browser contexts](https://playwright.dev/python/docs/api/class-browsercontext)
and [page APIs](https://playwright.dev/python/docs/api/class-page), with a fresh
unauthenticated context per viewport. It captures only the explicitly supplied
HTTP(S) URL; redirected navigation and frame navigation are blocked. Supply the
final URL explicitly if a site redirects. It never follows links or drives
state-changing interactions. Credentials in URLs and local-file schemes are
rejected. HTTP(S) subresources are allowed subject to a request count limit.

Defaults: desktop 1440×900 and mobile 390×844, 30 seconds total timeout, 40 captured
viewport-visible elements, 5,000 scanned elements, 200 requests per viewport, and
5 MB per screenshot. The inspection JSON is bounded by Visparse's 1 MB contract;
an oversized result fails explicitly. `--max-nodes`, `--max-scan`, `--timeout`,
`--wait-until`, and `--full-page` configure collection. Python `CaptureOptions`
also exposes request and artifact limits. These bound retained output and runtime;
they are not a browser-process memory or total network-byte sandbox.

Each viewport emits three linked capture records:

- Screenshot metadata and a content-addressed external PNG, identified by SHA-256.
- A DOM inventory containing selected computed CSS, viewport-relative CSS-pixel
  bounding boxes, raw semantic attributes, direct text summaries, and selected root
  custom properties. Combining related node evidence avoids duplicate fact arrays.
- A depth-limited CDP accessibility inventory with computed roles/names and selected
  states; AX IDs are not asserted to equal collector-local DOM IDs.

DOM payload fields: `collector_schema_version`, `context`, `nodes`, `coverage`,
`metadata`, and `css_variables`. Each node has `id`, `parent_id`, `tag`, `text`,
`attributes`, `box`, and `styles`. Context records session ID, viewport, state,
scroll position, DPR, and screenshot ID. Metadata records URL, time, title, browser
and collector versions, wait strategy, blocked request count, and observed DOM
mutations between inventory and screenshot. The capture is explicitly non-atomic;
CSS animations and canvas changes may occur without DOM mutations.

Coverage records scan/capture counts, truncation, and omissions. Offscreen elements,
shadow DOM, frame contents, and unobserved interaction states are not inferred.
Full-page screenshots may cover more than the viewport DOM sample. Form values
and editable text are omitted from JSON and their controls are masked in PNGs;
visible ordinary page text can still appear in evidence.

Numeric CSS is aggregated as medians by captured tag; unanimous strings are
preserved, heterogeneous strings yield a gap. Shadow/border fractions use only
the captured tag population. The subject is `visible-sample:tag=h1`, for example,
which permits scoped comparisons without treating node IDs as stable across sites.
Different sampling coverage must be considered when interpreting comparisons.

## DESIGN.md rendering

The renderer uses versioned policy `0.1`. A rule identifies its origin, confidence,
and scope. Default minimum inference confidence is 0.6. Compact and full modes
preserve the same effective rules; full adds evidence IDs and methods. Missing,
low-confidence, conflicting, and not-applicable values produce known gaps.

Rendering templates explicitly express transfer policy. Observing sparse shadows
never generates a prohibition, and incomplete motion evidence never invents an
animation rule. Hard rules require explicit supplied policies. Prose is escaped
as Markdown data but remains untrusted content for any receiving host agent.

`design-export` creates the generation input bundle using controlled feature
guidance plus a separately supplied brief. It omits raw source locators, evidence,
free-text feature values, and free-text principles/policies. Free-form scope labels
are aliased. This conservative export intentionally loses some prose nuance; a
host wanting richer guidance must separately curate that input. The host must use
a fresh workspace and avoid exposing original artifacts or reference-site access.
The exporter itself does not execute or sandbox a coding agent.

## DNA comparison and round-trip evaluation

`design-compare` matches exact feature names and scopes. Enum/text values use exact
equality; numeric differences within the vocabulary's absolute tolerance receive
1, otherwise similarity is `max(0, 1 - (difference - tolerance) / max(abs(a), abs(b),
tolerance, 1e-12))`. `--tolerances` accepts a JSON override for numeric features.
Per-dimension results report every value/difference, eligibility, compared count,
coverage, and skipped reasons. No comparable evidence produces a null score.
Both-not-applicable fields are excluded from eligibility; a missing field reduces
coverage. Conflicts and low-confidence inference remain unscored. There is no
opaque aggregate similarity score.

`design-roundtrip` consumes stored reference/generated DNA and run metadata. It
groups runs by brief, generator, and full configuration; records means, sample
standard deviations, coverage, baseline availability, and separate human review.
Conditions are `no_guidance`, `profile`, and `design_md`. The checked-in fixture
shows the complete contract. Input manifests record brief/guidance hashes and
declared isolation; brief hashes are verified. Manifest assertions cannot prove
that an external generator was isolated.

For a real benchmark:

1. Collect/analyze a reference and export transferable guidance.
2. Run each neutral brief under all three conditions, holding generator version,
   prompt policy, budget, and unrelated inputs constant. Curate the existing-profile
   baseline to remove original artifacts/branding before exposing it to generation.
3. Repeat runs, retain actual prompts/configuration and raw outputs, and analyze
   the generated pages under the same evidence/sampling protocol.
4. Store each generated DNA with its condition, replicate, input manifest, and
   independent review. Use a small blinded review to validate that DNA differences
   reflect visible differences; record reviewer disagreement separately.
5. Evaluate the stored fixture and inspect dimension scores together with coverage.

The comparator checks sensitivity with identical, altered, missing, and conflicting
fixtures. A same-analyzer round trip may share blind spots; it does not independently
prove visual fidelity. Live generator invocation is intentionally outside core.
Five original neutral briefs are checked in under `examples/briefs`.

## Analysis evaluation

`eval-analysis` consumes a fixture with `items` and `predictions`. Each item includes
an evidence DNA, provenance, and `expected` claim contracts. Each expected claim
specifies `id`, `name`, `scope`, `unit`, `kind`, `tolerance`, and `annotations`.
Grounding claims use scoped measured/observed DNA facts; interpretive claims use
individual `{annotator, value}` records. Predictions are grouped by model, with
versioned configuration and per-item claims containing `expected_id`, `name`,
`scope`, `value`, `unit`, `confidence`, and `evidence_ids`.

Grounding produces supported, contradicted, or insufficient-evidence outcomes.
Scope mismatch, uncited facts, missing data, and conflicting facts are insufficient
evidence, not contradictions. Supported/contradiction rates divide by decidable
grounding claims; grounding coverage divides decidable claims by grounding
predictions. Overall claim coverage divides predicted by expected claims. Empty
predictions earn zero coverage and no accuracy score. Invalid model cases are
reported separately rather than repaired or silently dropped.

Interpretive scoring reports agreement with individual annotators, label
distributions, and pairwise human agreement by dimension. Human agreement between
annotators is computed independently of whether a model supplied a prediction.
The report does not divide by weak/zero human agreement or claim chance-corrected
reliability. Annotation design should start with a small pilot and a fixed rubric.

Confidence has an explicit target: probability that the scoped claim is correct
within tolerance (grounding), or matches a randomly selected supplied annotator
(interpretive). Each has separate empirical Brier score, ten-bucket ECE, bucket
counts, and observed correctness. Abstentions/unscorable claims are excluded from
calibration and remain visible in coverage. Interpretive Brier averages squared
errors against actual labels; it does not square error only to the mean label.

Cross-model reports retain model/prompt/input protocol/configuration. Supply the
same evidence, preprocessing, and rubric to make comparisons meaningful. Keep
human labels and evaluation-only evidence out of analyzer inputs. Free prose
extraction, if used, must be evaluated as an additional interpretation stage.

This evaluates analysis quality (#9); round-trip evaluation measures downstream
transfer (#8). The existing `evaluate` command measures schema compliance. These
three results answer different questions and remain separate.

## Validation and supported scope

```sh
python -m unittest discover -s tests -v
python -m compileall -q src tests examples
VISPARSE_BROWSER_TESTS=1 python -m unittest discover -s tests -p test_collector.py -v
```

The browser tests serve only the checked-in synthetic page on loopback. CI runs
core tests on Python 3.10/3.14 and Chromium integration separately. Checked-in
analysis predictions, human labels, and round-trip runs are all explicitly
synthetic regression data. They establish evaluator behavior, not live model
quality, a completed expert study, or demonstrated production design transfer.

This version completes the provider-neutral schema, static collector, renderer,
and stored evaluation workflows. Rich interaction capture, automatic free-text
semantic extraction, provider-specific live orchestration, and expanded real-world
expert datasets remain optional external/future extensions of these contracts.

### Explicit semantic extraction (vocabulary 0.2)

Screenshot prose remains evidence, not automatic mechanical features. To extract
supported features without hand-writing annotations, explicitly invoke:

```sh
visparse design-normalize profile.json --contexts contexts.json > base-dna.json
visparse design-extract base-dna.json > enriched-dna.json
visparse design-render enriched-dna.json --generation-safe > DESIGN.md
```

Only `design-extract` without `--predictions` invokes the authenticated Codex CLI.
`design-extract base-dna.json --predictions predictions.json` validates a stored,
provider-neutral prediction offline. API callers can implement `SemanticExtractor`
and use `extract_design`, or use deterministic `apply_semantics`. Output features
are always inferred, carry uncertainty/method/evidence/scope, and cannot exceed
supporting inference confidence. Scopes come from evidence; optional contexts can
identify known regions. Unknown and conflicting values are retained, not filled in.
No retries, purchases, or provider switches are performed after a provider error.

Predictions have `schema_version: "0.1"` and `features`; each feature contains
`name,value,unit,status,confidence,scope,evidence_ids,method,uncertainty`. Examples
`semantic-lobby.json` and `semantic-corporate.json` contain synthetic base DNA and
stored predictions. No policy constraints or measured origins are accepted.

Vocabulary 0.2 adds controlled text-treatment, color-family and saturation fields.
Existing 0.1 DNA remains readable; enriched/new normalization output uses 0.2.
Generation-safe exports retain controlled features but omit arbitrary free text,
source labels and evidence IDs. Unsupported dimensions remain explicit gaps.

Evaluate raw-profile, DESIGN.md-only and combined-input runs separately. Preserve
input hashes, prompt versions, repetitions, coverage, and independent per-dimension
review (#8/#9); a nonempty feature list alone does not demonstrate fidelity.

Stored round-trip runs accept `profile_and_design_md` as a separate condition;
legacy baseline completeness still requires no_guidance/profile/design_md.

### Export intent (render policy 0.2)

`design-render` and `design-export` accept `--intent preserve|adapt`; the API
`render_design` / `prepare_roundtrip` accepts the same keyword. `adapt` remains the
backward-compatible default: inferred recommendations are qualified suggestions.
`preserve` exports supported visual features, suppresses inferred principles that
could prescribe redesign, and retains attributed explicit caller policy in the
normal export. Safe exports omit all free-form policy text: supply trusted caller
constraints in the separate brief. No evidence is rewritten when switching modes.

Caller constraints take precedence over supported observations; recommendations
never become newly observed facts. Unknowns and conflicts do not become mandatory
properties. Original content and assets remain distinct from appearance intent.
`design-export` records `export_policy` (version, intent, precedence); stored
round-trip configuration may include the same object so modes cannot be pooled
accidentally. Old runs without policy metadata remain valid.

For comparisons, hold the analysis fixed, record input hashes and policy/prompt
versions, use multiple fresh generations per intent, and review color, typography,
geometry and imagery separately. A single improved run is not a causal estimate.

### Region-aware features (vocabulary 0.3, semantic predictions 0.2)

The extractor can now declare `regions` alongside `features`. A region contains
`id,viewport,state,evidence_ids,confidence,method,uncertainty`; its ID is a neutral
lowercase role identifier. It creates `region:<id>` inferred evidence, retaining
original supporting IDs and source provenance. Its viewport/state must match every
anchor; mobile evidence cannot be invented from desktop. Features cite that new
ID and use the region ID as their scope subject. Confidence cannot exceed support.
Legacy 0.1 predictions and DNA vocabularies 0.1/0.2 remain readable.

Vocabulary 0.3 adds visible line/repetition counts, condensed/normal/wide type,
parent-fill width, viewport-relative x/y/width/height fractions (0..1), and explicit
`image.width`/`image.height` in `image-px`. Existing collector `geometry.width` and
`geometry.height` in `px` remain CSS geometry; image pixels are never converted to
CSS pixels implicitly. Pixel measurements supplied by a trusted image pipeline
must retain measured evidence and sampling method; VLM predictions remain inferred.
The built-in semantic extractor does not itself sample pixels or infer exact colors
from words like blue. The existing browser collector remains an optional source of
measured geometry; no URL access is necessary for screenshot-only estimates.

`layout.relative_position` additionally requires `relative_to`: a subject with
evidence in the same viewport/state. Relations participate in comparison keys and
safe-export role aliases, so distinct anchors do not collapse into conflicts.
`color.foreground_hex`, `color.background_hex`, and `color.accent_hex` require
canonical six-digit lowercase hex; they survive safe export. Colors compare exact
values, not perceptual similarity. Unknown colors remain null. Visible counts are
positive integers; units are null. Color unit is also null. Ratios retain `ratio`.

See `semantic-spatial.json` for a two-line headline, common left alignment, a subject
relationship, a full-parent button and scoped palette data. Measurements and
inferences are independently comparable with tolerances and coverage; absence is
not agreement. New source/measurement vocabulary is additive and version-gated.

Evaluate target-bearing relationships with `design-compare`; the scalar expected-
claim format in `eval-analysis` rejects relationship claims rather than silently
ignoring the target. Other new scalar/color/count features work in both evaluators.

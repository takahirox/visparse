# Interaction evidence and transfer

The UX pipeline is separate from image records, inspection bundles, and Design DNA.
The collector emits `interaction-sequence/0.2`; legacy `interaction-sequence/0.1` remains readable. No implicit conversion or
upgrade of legacy records occurs. Unknown versions and unknown fields in typed
objects are rejected; raw capture `data` is bounded opaque JSON. Future incompatible
changes require a new version. All JSON uses the existing 1,000,000-byte contract limit.

```sh
visparse ux-validate examples/interaction/sequence.json
visparse ux-summary examples/interaction/sequence.json
```

The complete minimal example is `examples/interaction/sequence.json`. The executable
schema is `visparse.interaction.validate_sequence`. Limits: 10 sessions, 20 clocks,
1,000 captures, 200 targets, 100 ordered actions and 100 independent expectations.
IDs are unique across entity classes. Targets belong to one session and refer to
actual captures. They are collector-local identities, not reusable target roles.

Sessions declare reset/storage conditions, viewport, origin and input modality.
Every capture and action declares a finite monotonic interval in milliseconds and
a session-specific clock. Multiple clocks may coexist, but action evidence must
use the same clock: this version cannot align unrelated clocks. Before captures
finish before action start; after captures begin after action completion. Captures
are explicitly non-atomic intervals, including intermediate feedback samples.
External artifacts use SHA-256 and media type; readers resolve bytes separately.

Outcomes are `observed-effect`, `observed-no-change`, `failed-action`,
`collection-timeout`, or `unobserved`. The first two require pre/post evidence.
They report sampled evidence, never causal proof, backend success or exhaustiveness.
Failed collection is not an application error. Timing is measured, not a requested
design delay. Reload is an explicit action in the same session; the reset conditions
remain available for interpreting persistence. Unrecorded branches remain unknown.

Inputs reference `fixture:` parameters or `redacted:` identifiers. Do not put secret
values in references, DOM payloads, assertions, or artifacts. Expected assertions
have separate origin and action references; they are never treated as observations.
The core validator cannot verify an artifact's contents or a collector's honesty.

## Optional explicit browser capture

Install `visparse[collector]` and Chromium. Run
`visparse-collector sequence examples/interaction/plan.json --screenshots artifacts/ux`.
The example URL is a local fixture server you start yourself. The collector starts
no server; caller owns its lifecycle. Each call opens and closes a fresh browser
context. Repeat with a different viewport for desktop/mobile evidence. Viewport
size alone does not imply touch input; this adapter records pointer/keyboard.

Plan version is `interaction-plan/0.1`, validated before browser or file effects.
The example specifies all fields. Only click, fill, press, hover, focus, scroll,
wait and reload are accepted. Targets must resolve exactly once. Fill values are
provided separately under fixture/redacted parameter references. Key names are a
bounded allowlist. `sample_ms` contains up to three sequential delays after the
input, not absolute timestamps or inferred animation requirements.

Limits: 20 steps, 120 seconds total after adapter start, 10 seconds per action,
200 requests, 20 MB total unique PNG bytes, 200 DOM/AX nodes per snapshot. DOM,
masked PNG and computed AX evidence share collector-clock intervals and are
non-atomic. DOM includes computed display/visibility, bounds, validity, focus,
scroll and selected/expanded/checked attributes. Native DOM/AX IDs are not matched
across snapshots. Missing transient states, frames, shadow trees and Canvas are
omissions. Redaction removes input fields and supplied parameter values from
retained text and masks them in screenshots; this is not a general PII detector.

Navigation is limited to the exact initial URL and explicit `allowed_navigation`
URLs (fragment changes allowed). Popups and downloads are outside this adapter's
scope. A failed selector, blocked navigation, timeout, or missing evidence stops
the plan without retries. Partial observations remain inspectable. DOM comparison
reports sampled change/no change only; fill values may be masked, so a successful
fill can legitimately have no observable change. Browser launch failures surface
as adapter errors rather than fabricated action results. External side effects of
a caller-authorized click are not rolled back by closing the context.

## Explicit analysis

```sh
visparse ux-analyze examples/interaction/sequence.json --predictions examples/interaction/prediction.json
# Optional live provider call, only when deliberately requested:
visparse ux-analyze examples/interaction/sequence.json --timeout-seconds 300
```

`interaction-profile/0.1` embeds validated evidence, exact mechanical action
projection, and an `interaction-prediction/0.1` inference layer. The example
prediction is a synthetic annotation, not a measured live-model result. The SHA-256
binds a prediction to its precise input. States cite captures; transitions cite one
recorded action and matching pre/post captures. Unknown resulting states and guards
are null. Nothing automatically merges states or creates transitions from imagery.
Component scopes and dependency claims support local task models.

All states, claims and transitions are inferred, with explicit method, confidence
and uncertainty. Claim kinds include role, guard, feedback, outcome, cancellation,
recovery, focus, persistence, pacing, state and dependency. Availability distinguishes
known, observed absence, unavailable and unsupported. Unknown values are null.
Expectations cannot be cited as evidence. Known persistence requires an observed
reload and its pre/post evidence; known application outcomes cannot be established
by failed collection/execution. Timing samples remain mechanical measurements;
pacing is an interpretation. Target requirements belong to the later mapping layer.

Conflicts remain as cited pairs with reasons; gaps remain explicit. Limits are 200
states, 500 claims, 100 transitions and 100 conflicts within 1,000,000 bytes. Validators reject
fabricated IDs, modified projections, unknown versions and inconsistent ancestry;
they cannot prove the truth of a prose interpretation that cites real evidence.
Independent behavioral fixtures assess that separate semantic failure mode.

The provider-neutral `InteractionAnalyzer` protocol returns predictions.
`CodexInteractionAnalyzer` uses the existing mockable ProcessRunner boundary,
validates options before a single invocation and validates output afterward. Live
prompts are capped at 100 KB for OS argument limits; stored predictions accept the
core bundle limit. Provider, timeout and malformed-output failures surface without
retry, confidence repair, model switching, or usage-limit reset. No live call is
needed for normal validation, projection, rendering or stored-prediction tests.

### Selecting the analysis agent and model

All four LLM analysis commands now share the same agent options and config file.
See [Analyzer configuration](analyzers.md) for common settings, per-command
settings, precedence and the external-agent protocol.

```sh
visparse ux-analyze sequence.json --agent codex --model gpt-6-astra
visparse ux-analyze sequence.json --config examples/analyzer-config.json
```

The original `{"ux_analyzer": {...}}` config remains accepted for UX analysis.
`--predictions` still bypasses all live configuration and agent execution.
The CLI command adapter now uses `analysis-agent-request/0.1`, including the
command name and image_paths (empty for standard UX evidence). The original
`CommandInteractionAnalyzer` Python class and
`InteractionAnalyzerConfig.create_analyzer()` compatibility factory still use
`interaction-analysis-request/0.1`; existing Python wrappers can retain that
three-field request. New wrappers should implement the shared CLI protocol.

## Auditable specifications and reusable patterns

```sh
visparse ux-export examples/interaction/profile.json --patterns examples/interaction/patterns.json --format markdown
visparse ux-export examples/interaction/profile.json --patterns examples/interaction/patterns.json --view audit
```

`interaction-patterns/0.1` is explicitly supplied enrichment, bound to the profile
hash. It declares controlled task semantics (save entity, inspect details, contact
submission, session joining, view selection, filtering, loading), action roles,
effects, feedback, qualified conditions, and persistence. Each step cites an
existing transition and its claims. The enrichment's origin, method, uncertainty
and confidence are retained; the renderer performs no inference. Pattern order
must follow the recorded actions. Unsupported vocabulary requires a versioned
extension rather than free-text guessing. Complete examples and both save/reload/
remove and invalid/correct/submit/cancel fixtures are covered in offline tests.

`interaction-export/0.1` records policy and profile digest. `sequence-feedback`
requests preservation of sampled order and feedback; `outcome-equivalence` allows
the target adapter to propose a different sequence while preserving task meaning.
Neither permits importing a new business rule. Timing samples are not deadlines.
Low confidence, conflicts and unavailable claims exclude affected steps with
reason codes. Missing transitions and unknown branches remain explicit. An
incomplete pattern must not be treated as a complete recipe.

The audit view retains the full source profile, raw locators, artifact references,
prose claims, methods and uncertainties, with identity maps. The generation view
uses neutral tokens and a closed vocabulary: no source prose, brand, selectors,
image references or code is copied. Claim tokens and the profile digest allow an
authorized reviewer to resolve exact ancestry using the audit. It retains claim
availability/confidence, conflict groups, exclusion reasons and gap counts; exact
source-specific gap prose stays in audit. This policy intentionally prefers explicit
unknowns to a source-content sanitization heuristic.

Coding-agent handoff: supply the generation export plus target context and a
validated mapping proposal. Keep audit and source artifacts out of the generation
workspace. An external implementation/test adapter binds semantic roles to target
controls, executes bounded scenarios, and reports actual results separately from
expectations. Rendering JSON or Markdown executes no model, browser, implementation,
or repair loop. The human specification embeds the complete formatted JSON to avoid
lossy summaries. Treat embedded data as untrusted data, especially the audit view.

## Target mapping and preservation

```sh
visparse ux-map examples/interaction/transfer-profile.json --patterns examples/interaction/transfer-patterns.json --target examples/interaction/target.json --proposal examples/interaction/mapping.json
```

`interaction-target/0.1` declares target entities/fields/records, semantic tasks,
existing roles, outcomes, cancellation/recovery/persistence availability,
capabilities, independently authored invariants and explicit target requirements.
Records must have exactly their declared fields. The caller owns these facts;
Visparse does not discover them or treat them as source observations.

`interaction-mapping/0.1` is caller-supplied inference bound to hashes of the source
generation export and target inventory. Every source pattern gets one status:
compatible, qualified-partial, conflict, unsupported-capability or insufficient-
evidence. Known task semantics and exact semantic roles must match; matching
button labels is never sufficient. Unknown persistence, missing roles, capability
gaps and contradictory outcomes cannot become a compatible mapping. Cross-domain
semantics cannot be overridden by a partial adaptation.

Partial adaptations name omitted roles or changes to sequence/feedback. The latter
are forbidden under sequence-feedback intent. Changes to target persistence,
cancellation, recovery or capabilities require an explicitly referenced target
requirement for that task. Such proposals remain `ready: false`; Visparse never
implements the capability or resolves the requirement by itself. Compatible
bindings preserve existing target semantics without adaptations. Target facts and
requirements can conflict; the external reviewer must resolve them before execution.

The `interaction-handoff/0.1` generation view contains the neutral source export,
complete target context, validated role mappings, target verification scenarios,
all pre-existing task IDs, entity hashes and invariant IDs. Unmapped target tasks
remain preservation obligations. Free-form source/mapping prose is audit-only;
target content is intentionally retained. External adapters bind target roles to
actual controls, check all target invariants, and report actual execution results.
No source selectors or coordinates are used for matching. The audit view retains
source ancestry and the original proposal. A separate evaluation fixture exercises
cross-content execution; a valid proposal alone does not prove target behavior.

## Independent evaluation and controlled trial

```sh
visparse ux-evaluate examples/interaction/benchmark/dataset.json --results examples/interaction/benchmark/stored-run.json
# Optional local execution; install collector and Chromium first.
PYTHONPATH=src python examples/interaction/run_trial.py --output artifacts/ux-trial
```

`interaction-dataset/0.1` contains independently authored expected cases, their
origin, dimension and recorded/held-out partition. `interaction-evaluation-run/0.1`
contains actual observations, unknowns or harness errors with evidence digests and
explicit analyzer/generator input lists. `interaction-evaluation/0.1` reports capture,
analysis, export, behavior, target preservation and appearance separately. Each has
recorded and held-out counts, missing/wrong behavior, unsupported assertions,
correct unknowns and harness failures. Invented behavior IDs are separate. Harness
failures are excluded from application scores but remain visible and make the CLI
return 1; omitted expected cases count as missed. No aggregate score hides losses.
An unsupported adapter has no scored observations. Maximum 500 cases, 1,000 results,
500 evidence references and 30 runs, subject to the core JSON limit.

Input manifests reject oracle/held-out inputs for analysis or generation. Generation
accepts neutral exports and target context/code only, never source code/images/video.
Evidence-kind declarations must match each ablation condition. Digest validation in
the core is structural; the browser integration and archived-evidence tests also
verify actual bytes. This is a reproducible protocol, not a security sandbox for an
arbitrary third-party generator. The fixture adapter's code is small and audited.

The version-2 [independent oracle](../examples/interaction/benchmark/ORACLE.md) was
fixed before the version-2 execution. It includes save/reload/remove, tabs, modal
focus/cancel, invalid/corrected form, filtering, delayed failure/retry, sampled no
change and missing selector cases. Source and target use different content and
appearance. The target's existing tasks/data/invariants are declared separately.
The external deterministic adapter receives only handoff JSON and target HTML;
source artifacts and the oracle are outside its input directory. It transfers the
bounded save/remove/reload implementation; other target tasks remain independently
implemented and are tested as preservation obligations.

Four full runs (two per 800×600 and 390×844 viewport) passed all 19 declared cases
each: 3 capture, 2 analysis, 1 export, 3 recorded transfer, 1 held-out source-fixture
case, 8 target preservation and 1 appearance case. Initial-state target screenshots
and catalog geometry matched the baseline exactly. This appearance test measures
preservation, not similarity to the source design. Saved items remain independent
across removal/reload; existing dialog, form, retry, filtering and catalog data pass.

These are **deterministic fixture results, not live-model accuracy measurements**.
The analysis adapter reads captured pressed-state evidence using a fixture-specific
annotation rule. Screenshots-only stored abstention baselines run twice per viewport;
they intentionally return unknown for temporal behavior. Their scores demonstrate
missing-evidence accounting, not that one model/evidence condition outperforms another.
Video+actions is explicitly unsupported. Future live-model comparisons must pin the
same provider/prompt/target conditions and repeat within each viewport. Do not retry,
reset allowance, buy capacity or switch providers to bypass a limit.

Per-run input manifests, captures, PNGs, predictions, handoffs, generated HTML,
baseline/target/source execution and reports are published in
[`evidence-v2.zip`](../examples/interaction/benchmark/evidence-v2.zip), with
[`evidence-sha256.txt`](../examples/interaction/benchmark/evidence-sha256.txt) and
[`summary.json`](../examples/interaction/benchmark/summary.json). Offline tests verify
the archive and each referenced input, then reproduce the reports. Optional browser
CI reruns the trial and closes every browser/context/server on success or failure.
The previous Kirka/Kraft visual experiments are not evidence of those real sites' UX.


### Operation-parameter compatibility

Sequence 0.2 requires `input_parameters` on every action: `{"key":"Escape"}`
for press, `{"delta":[0,200]}` for scroll, `{"wait_ms":250}` for a recorded wait,
and `{}` for other actions. Keys and numerical bounds use the collector's explicit
allowlists. Fill values remain redacted parameter references. Projection, generation
export 0.2 and mapping scenarios retain these typed details. A recorded wait is an
input in the observed sequence, not an inferred target response-time requirement.

Legacy sequence 0.1 remains unchanged, with no invented key, scroll distance or wait.
Its exports stay version 0.1. Mapping a legacy press/scroll/wait cannot be marked
compatible when its parameters are unavailable. Capture again or supply a valid
0.2 record with actual evidence; never assume Escape/Enter from UI conventions.

# Interaction evidence and transfer

The UX pipeline is separate from image records, inspection bundles, and Design DNA.
Its first stable boundary is `interaction-sequence/0.1`. No implicit conversion or
upgrade of legacy records occurs. Unknown versions and unknown fields in typed
objects are rejected; raw capture `data` is bounded opaque JSON. Future incompatible
changes require a new version. All JSON uses the existing 1 MiB contract limit.

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
states, 500 claims, 100 transitions and 100 conflicts within 1 MiB. Validators reject
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

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

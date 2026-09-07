# Evaluation methodology

The evaluation format is ordinary JSON so results can be reviewed without a service or hidden scorer. A fixture contains a `cases` array. Each case has:

- a unique human-readable `name`
- `expected_valid`, always a boolean
- either a structured `record` or a JSON string `payload`
- optionally, an exact `expected_summary`

The evaluator validates each case using the production schema. Expected-invalid cases pass only when validation rejects them. Expected-valid cases may additionally compare the entire structural summary. Results contain `total`, `passed`, and ordered failure messages; no probabilistic scoring is involved.

Run the checked-in fixture with:

```sh
PYTHONPATH=src python -m visparse evaluate examples/evaluation_fixture.json
```

A successful result is:

```json
{"failures":[],"passed":2,"total":2}
```

The fixture covers a valid record with source, deterministic pixel measurement, and web interaction, plus an observation with a broken evidence reference. Unit tests cover canonicalization, limits, duplicate keys and IDs, confidence ranges, temporal events, analyzer identity, CLI behavior, and summary mismatches.

This methodology evaluates contract compliance, not visual accuracy. Accuracy benchmarks should preserve raw source identities and separately label measured values, direct observations, interpretations, uncertainty, and provenance. Human or model judgments must never be relabeled as deterministic measurements.

The design workflow now provides separate `eval-analysis` (scoped grounding,
human agreement, calibration), `design-compare` (stored DNA differences), and
`design-roundtrip` (stored generation runs and baselines) commands. See
[design-workflow.md](design-workflow.md) for their versioned fixtures, metric
denominators, uncertainty handling, and limitations. The original `evaluate`
contract and behavior remain unchanged.

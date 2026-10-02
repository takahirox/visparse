# Review Guidelines

The purpose of review is not only to check whether a change works. It is also to verify that the change is the right response to the Issue that motivated it.

These guidelines are particularly important when reviewing AI-generated changes.

## Review Against the Issue

Start by reading the source Issue.

Treat the Issue as the reference for the intended problem and expected outcome.

Ask:

> Is the Pull Request a complete and appropriately scoped solution to this Issue?

## Check for Missing Work

Verify that the Pull Request addresses all parts of the Issue that it claims to resolve.

Do not approve a Pull Request as closing an Issue when important requirements remain unimplemented.

If the change is intentionally partial, the Pull Request should say so and the Issue should remain open.

## Check Acceptance and Verification

Follow the [development flow](development-flow.md#1-start-with-an-issue) when distinguishing pre-merge acceptance from required post-merge verification.

Mandatory pre-merge acceptance criteria must be achievable and verifiable before merge. Require all implementation requirements and applicable pre-merge tests to be satisfied. Checks possible only after merge must not be prerequisites for pre-merge PR approval.

For a merge-triggered deployment, review the code/configuration, local build results, and applicable automated test results before merge. Verification that deployment succeeds and the newly published site behaves as expected belongs [after merge](development-flow.md#6-verify-after-merge).

Ensure required post-merge verification is recorded separately with its expected results and reported as pending until performed. Pending post-merge checks alone do not prevent approval when implementation and mandatory pre-merge acceptance are complete. They do not excuse missing implementation, skipped applicable pre-merge tests, or claims that unperformed validation passed.

## Check for Unnecessary Work

Verify that the Pull Request does not go beyond what the Issue requires without a clear reason.

Watch for:

- unnecessary abstractions
- speculative extensibility
- unrelated refactoring
- new frameworks or subsystems that are not required
- additional policies or configuration with no demonstrated need

AI agents can over-engineer solutions. Do not treat additional complexity as automatically beneficial.

Prefer the smallest design that completely solves the stated problem.

## Check the Result

Also verify the ordinary quality of the change:

- behavior matches the expected outcome
- implementation is coherent with the existing architecture
- validation is sufficient for the change
- documentation is updated when the change affects documented behavior

## Review Outcome

A Pull Request is ready to merge when:

- it satisfies all implementation requirements and mandatory pre-merge acceptance criteria of the Issue it claims to resolve
- it does not introduce unjustified scope or complexity
- the implementation is correct and appropriately validated
- required post-merge verification is recorded separately and reported as pending until performed

If any of these conditions are not met, request changes and review again after revision.

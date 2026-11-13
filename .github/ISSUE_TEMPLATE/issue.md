---
name: Issue
about: Report a problem or propose a change
title: ""
labels: ""
assignees: ""
---

## Problem

Describe the problem.

## Expected outcome

Describe what should be true when the issue is resolved.

Default to completion criteria an AI agent can execute and verify. Require human checks only when necessary; explain why and the expected result, and distinguish optional validation from mandatory criteria. See the [development guidance](https://github.com/takahirox/visparse/blob/main/docs/development-flow.md#1-start-with-an-issue).

### Pre-merge acceptance criteria

List mandatory acceptance criteria that can be achieved and verified before merge. Checks possible only after merge must not be prerequisites for pre-merge PR approval.

For a merge-triggered deployment, validate the code/configuration, local builds, and applicable automated tests before merge; verify deployment and the newly published site after merge. This distinction preserves implementation requirements and applicable pre-merge tests.

## Required post-merge verification

Record only checks the actual change requires after merge, including the expected result. If none are required, state that. Report pending or environment-blocked checks honestly. Follow the [merge and closure lifecycle](https://github.com/takahirox/visparse/blob/main/docs/development-flow.md#5-merge): merge and close the completed original Issue, then record verification evidence and track discovered defects in linked Issues.

## Context

Add any relevant context, examples, logs, or related issues.

For a defect found after merge, first check for an equivalent Issue; include reproduction steps, the affected revision, expected/actual behavior, and links to the original Issue and Pull Request. Do not reopen the original Issue solely for this follow-up.

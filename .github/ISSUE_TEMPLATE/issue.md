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

Record required checks possible only after merge separately, including the expected result. Report them as pending until performed; do not claim they passed in pre-merge validation. If none are required, state that. See [post-merge verification](https://github.com/takahirox/visparse/blob/main/docs/development-flow.md#6-verify-after-merge).

## Context

Add any relevant context, examples, logs, or related issues.

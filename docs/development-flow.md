# Development Flow

This document defines the default development flow for Visparse, with particular emphasis on AI-assisted development.

## 1. Start with an Issue

Work should begin with an Issue.

The Issue should clearly state:

- the problem
- the expected outcome
- relevant context

The Issue defines the scope of the work. If the scope is unclear, clarify the Issue before implementation instead of inventing requirements during the change.

By default, completion criteria should be executable and verifiable by an AI agent. Require human checks, such as physical-device testing, subjective evaluation, or external approval, only when there is a necessary reason to do so.

When human work is required, state why it is necessary and what result is expected. Distinguish optional additional validation from mandatory completion criteria.

Mandatory pre-merge acceptance criteria must be achievable and verifiable before merge. Record required checks possible only after merge separately, with their expected results. They must not be prerequisites for pre-merge PR approval and must be reported as pending until performed.

For example, when deployment is triggered by merge, validate the code/configuration, local builds, and applicable automated tests before merge. Verify deployment and the newly published site after merge. This separation preserves implementation requirements and applicable pre-merge tests; it does not justify deferring checks that can be performed before merge.

## 2. Create a Pull Request for the Issue

Implementation should be proposed through a Pull Request associated with the Issue.

The Pull Request should explain:

- what changed
- what outcome the change produces
- how the change was validated
- which Issue it addresses

Use validation appropriate to the change. Report results and limitations accurately; do not claim unperformed checks passed.

Report pre-merge validation results separately from required post-merge verification, which remains pending until performed.

A Pull Request should only claim to close an Issue when it fully addresses that Issue.

If the Pull Request intentionally implements only part of the Issue, it should state that clearly and should not present the Issue as fully resolved.

Required post-merge verification may remain pending at approval when all implementation requirements and mandatory pre-merge acceptance criteria are satisfied and the remaining checks are recorded separately. Do not describe pending verification as completed.

## 3. Review Before Merge

Every Pull Request should be reviewed before merge.

A central review question is:

> Does this Pull Request address the Issue completely, without adding changes that are not justified by the Issue?

Review must check both directions:

- **No missing scope:** the Pull Request should satisfy all implementation requirements and mandatory pre-merge acceptance criteria, and record required post-merge verification as pending until performed.
- **No unnecessary scope:** the Pull Request should not introduce unrelated abstractions, frameworks, policies, or complexity beyond what is needed to solve the Issue.

This is especially important for AI-generated changes. AI agents may produce broader or more elaborate designs than the task requires. Prefer the smallest change that fully satisfies the Issue.

Use the [review guidelines](review-guidelines.md#check-acceptance-and-verification) to assess pre-merge acceptance and pending post-merge verification separately.

## 4. Revise Until Review Passes

If review finds missing requirements, unnecessary scope, correctness problems, or insufficient validation, update the Pull Request and review it again.

The Pull Request should be merged only when the reviewed change is an appropriate and complete response to the Issue.

## 5. Merge

After review passes, merge the Pull Request.

## 6. Verify After Merge

Perform the required post-merge verification recorded in the Issue and Pull Request. For a merge-triggered deployment, verify that deployment succeeds and the newly published site has the expected behavior.

Record the actual results and any failures or limitations. Keep unperformed checks pending; approval or merge alone does not establish that post-merge verification passed.

The normal flow is therefore:

```text
Issue
  ↓
Implementation
  ↓
Pull Request
  ↓
Review
  ↓
Revision if needed
  ↓
Merge
  ↓
Required post-merge verification
```

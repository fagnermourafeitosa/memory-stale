# 25 — Run validation only for code changes

## Problem Statement

The repository instructions require the full Python validation suite before
considering every change complete. This makes documentation, specification,
and repository-instruction changes run unrelated tests, formatting, linting,
and type checking.

## Solution

Limit the required Python validation commands to changes that alter production
or test code. For a change with no code modifications, verify the affected
artifact directly and do not run the Python quality suite solely because of
the change.

## User Stories

1. As a documentation editor, I want a README-only update checked for textual
   accuracy without waiting for unrelated test suites.
2. As a maintainer, I want code changes to retain the existing focused and
   full validation requirements.
3. As a contributor, I want an explicit instruction that avoids ambiguity
   about validation for specifications and repository instructions.

## Observable Test Seam

The public seam is `AGENTS.md`: its validation instructions distinguish code
changes from non-code changes in unambiguous language.

## Expected Behavior

- A change to production or test code still runs the focused test cycle and
  every command in the required-validation block.
- A change with no production or test code modifications does not run that
  block merely as a completion ritual.
- Non-code changes receive direct review appropriate to their changed files.

## Implementation Constraints

- Keep the repository instructions in English.
- Do not change the test suite, runtime, dependencies, or validation commands
  themselves.
- Preserve the mandatory TDD workflow for behavior changes.

## Testing Decisions

- This changes repository instructions only; no automated tests are run.
- Review the changed instruction against the TDD and required-validation
  sections for consistency.

## Out of Scope

- Changing what the Python quality commands check.
- Making validation optional for code changes.
- Adding automation to classify changes.

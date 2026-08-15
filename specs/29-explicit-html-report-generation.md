# 29 — Explicit HTML report generation

## Problem Statement

The `Stop` hook generates an HTML report after every completed turn. This adds
an unsolicited project file even when the user only asked to change code or
maintain memory. The report is useful as an inspection artifact, but its
creation must not be an automatic side effect of ordinary task completion.

## Solution

Remove report generation from the `Stop` lifecycle hook. HTML generation
remains available only through the explicit `memory.report` MCP request, which
continues to write the configured report path atomically.

## User Stories

1. As a developer, I do not want ordinary Codex tasks to create an HTML report
   in my repository.
2. As a developer, I want to generate the memory report deliberately when I
   request it, so that I can inspect memory state on demand.
3. As a maintainer, I want lifecycle reconciliation to remain independent of
   presentation artifacts.

## Observable Test Seam

The highest seam is a real `UserPromptSubmit` and `Stop` hook cycle in a
temporary Git repository followed by a real `memory.report` MCP request. `Stop`
must persist/reconcile memory without creating `memory-report.html`; the MCP
request must then create that report at the configured path.

## Expected Behavior

- `Stop` never creates an HTML report, including when `auto_report = true` is
  present in the existing configuration.
- `memory.report` continues to create a complete report at `report_path` and
  returns its path.
- Memory capture, reconciliation, staleness, retrieval, and task cleanup have
  no behavioral change.
- Existing configuration remains readable; this change does not remove or
  migrate configuration fields.

## Implementation Constraints

- Preserve the local MCP report interface and atomic report writes.
- Keep lifecycle hooks non-blocking and do not introduce another process, LLM,
  or human-facing CLI.
- Do not alter memory storage, evidence resolution, or retrieval policy.

## Testing Decisions

- Confirm the hook-cycle-plus-MCP seam before the first test.
- First red-green slice: set `auto_report = true`, run the real hook cycle, and
  assert that no report file exists. The current implementation must fail
  because `Stop` writes the report.
- Follow with an MCP test proving that an explicit report request still creates
  the configured file.
- Run focused tests during development, then the repository's required format,
  lint, type, and full-suite validation.

## Out of Scope

- Removing the HTML report feature or `memory.report` MCP tool.
- Removing or redesigning report configuration fields.
- Changing report content, layout, memory lifecycle behavior, or retrieval.

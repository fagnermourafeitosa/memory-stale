# 08 — End-to-end test harness

## Problem Statement

The plugin depends on Git, hooks, MCP, files, and tree-sitter; isolated tests are insufficient to establish the lifecycle.

## Solution

Build a harness with temporary Git repositories and simulated Codex events.

## User Stories

1. As a maintainer, I want to test the complete flow without a real Codex session.
2. As a maintainer, I want to reproduce tasks that change many files and languages.
3. As a user, I want confidence that a memory failure does not block work.

## Implementation Decisions

- The harness builds a temporary repository, an optional dirty baseline, hook events, and MCP captures.
- Scenarios cross retrieval, ledger, capture, lifecycle, and persistence.
- Fixtures cover every V1 language.

## Testing Decisions

- Seam confirmed by continuous authorization: the harness starts a temporary Git repository and executes real hooks and MCP over subprocesses, without a Codex session and without calling internal production functions.
- Flow: active context → edit → capture → Stop → correct Markdown and staleness.
- Scenarios: multiple files, multiple refs, comments, removal, invalid language, duplicate capture, indexing failure, and Dream.
- Tests verify observable behavior and persisted content, not internal calls.

## Out of Scope

- Testing the real Codex UI or an external network.

## Further Notes

- This harness is the quality demonstration foundation for the portfolio.

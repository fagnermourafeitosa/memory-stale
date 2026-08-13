# 01 — Project-local runtime and hooks

## Problem Statement

The project-local integration must provide context before a task and finish maintenance afterward without depending on human action.

## Solution

Package a project-local skill and handlers for the `UserPromptSubmit`,
`PostToolUse`, and `Stop` hooks, leaving MCP inclusion to spec 02, when its
server and contract actually exist.

## User Stories

1. As a user, I want to install and trust the local project integration once, so that hooks operate throughout the Codex lifecycle.
2. As Codex, I want to receive context before acting.
3. As a maintainer, I want the task's real changes available at the end of the turn.

## Implementation Decisions

- The source repository provides the skill under `skills/`, hook adapters, and a bootstrap. Its installer places them below the target project's `.agents/skills/memory-stale/` directory and registers hooks below the target's `.codex/hooks.json`.
- Each hook is a JSON command: it receives an object through `stdin`, writes only the JSON accepted by the event to `stdout`, and uses the working directory supplied by Codex as the repository root.
- Hook commands run Python through `uv` in frozen mode without implicit sync; their environment and cache live below the target Git directory, never in the user's global cache.
- `UserPromptSubmit` requests context from the retrieval module.
- `PostToolUse` appends write operations to the task ledger.
- `Stop` combines the ledger with a diff against the initial snapshot and calls the lifecycle engine.
- A working-tree snapshot is created at the beginning of the task; pre-existing changes do not enter the task ledger.
- Hooks are thin, error-tolerant adapters.
- Until the engines from specs 04 and 05 exist, their boundaries return empty results without inventing memory policy; later integration replaces only those boundaries without changing the hook contract.
- Ephemeral state keyed by `turn_id` remains outside the durable store, and its writes are atomic.

## Testing Decisions

- Confirmed seam: install the real commands into temporary Git repositories, send JSON payloads through `stdin`, and verify `stdout`, exit code, and observable local state.
- Coverage instruments the subprocesses for those commands and combines their data, preserving the public seam instead of duplicating tests against internal functions.
- Validate the target-local hook configuration and registered commands through a temporary Git repository.
- Simulate each hook's JSON payload and verify the adapter's public outputs.
- Verify that a dirty workspace that predates the task does not appear as a task change.
- Verify that an internal error does not prevent the hook from returning normally.

## Out of Scope

- MCP tooling and configuration, memory policy, symbol parsing, and persistence.

## Further Notes

- Per-project activation will be defined with configuration in spec 07.

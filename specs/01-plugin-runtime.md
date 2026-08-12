# 01 — Plugin runtime and hooks

## Problem Statement

The plugin must provide context before a task and finish maintenance afterward without depending on human action.

## Solution

Package the manifest, skill, and handlers for the `UserPromptSubmit`,
`PostToolUse`, and `Stop` hooks, leaving MCP inclusion to spec 02, when its
server and contract actually exist.

## User Stories

1. As a user, I want to install and trust the plugin once, so that hooks operate throughout the Codex lifecycle.
2. As Codex, I want to receive context before acting.
3. As a maintainer, I want the task's real changes available at the end of the turn.

## Implementation Decisions

- The repository is the plugin's installable root and contains the `.codex-plugin/plugin.json` manifest, the skill under `skills/`, and configuration discovered by default at `hooks/hooks.json`.
- Each hook is a JSON command: it receives an object through `stdin`, writes only the JSON accepted by the event to `stdout`, and uses the working directory supplied by Codex as the repository root.
- Hook commands run Python through `uv` in frozen mode without implicit sync; the plugin environment and cache live under the writable `PLUGIN_DATA` directory, never in the user's global cache.
- `UserPromptSubmit` requests context from the retrieval module.
- `PostToolUse` appends write operations to the task ledger.
- `Stop` combines the ledger with a diff against the initial snapshot and calls the lifecycle engine.
- A working-tree snapshot is created at the beginning of the task; pre-existing changes do not enter the task ledger.
- Hooks are thin, error-tolerant adapters.
- Until the engines from specs 04 and 05 exist, their boundaries return empty results without inventing memory policy; later integration replaces only those boundaries without changing the hook contract.
- Ephemeral state keyed by `turn_id` remains outside the durable store, and its writes are atomic.

## Testing Decisions

- Confirmed seam: execute the real commands declared in `hooks/hooks.json`, send JSON payloads through `stdin` inside temporary Git repositories, and verify `stdout`, exit code, and observable local state.
- Coverage instruments the subprocesses for those commands and combines their data, preserving the public seam instead of duplicating tests against internal functions.
- Validate the manifest with the plugin validator used by Codex.
- Simulate each hook's JSON payload and verify the adapter's public outputs.
- Verify that a dirty workspace that predates the task does not appear as a task change.
- Verify that an internal error does not prevent the hook from returning normally.

## Out of Scope

- MCP tooling and configuration, memory policy, symbol parsing, and persistence.

## Further Notes

- Per-project activation will be defined with configuration in spec 07.

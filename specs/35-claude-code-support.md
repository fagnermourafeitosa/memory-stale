# 35 — Shared lifecycle support for Claude Code

## Problem Statement

Memory Stale currently exposes its deterministic memory lifecycle through Codex-specific hook payloads. Claude Code offers equivalent lifecycle events, but using them directly would either duplicate the lifecycle implementation or introduce host conditionals throughout the core. Project owners need the same memory store, retrieval, automatic provenance, semantic-capture contract, and staleness reconciliation when working in Claude Code.

## Solution

Refactor the hook runtime into host-agnostic lifecycle operations and thin host adapters. The Codex adapter continues to parse Codex payloads exactly as it does today. A Claude adapter normalizes `UserPromptSubmit`, `PostToolUse`, and `Stop` payloads into the shared task-start, ledger, and reconciliation inputs.

Claude task identities use `claude:<session_id>:<prompt_id>` whenever `prompt_id` is present. When it is absent, Claude lifecycle hooks perform a silent non-blocking no-op rather than fabricating a potentially shared task identity. If an `agent_id` identifies a subagent, it is included in the normalized task identity so it cannot share the main agent's state.

The project installer copies one runtime, merges Codex and Claude hook configuration without replacing unrelated settings, registers the existing MCP server for Codex, and creates a Claude project `.mcp.json` entry pointing to that same copied runtime. Claude receives a project instruction artifact with the same `memory.capture` semantic contract as Codex.

## User Stories

1. As a Claude Code user, I want active memories injected when I submit a prompt, so that I can use relevant project knowledge before editing.
2. As a Claude Code user, I want the injected instruction to require semantic capture for supported-code changes, so that automatic provenance is not mistaken for a semantic memory.
3. As a Claude Code user, I want tool activity recorded during a prompt, so that the task ledger reflects the work actually done.
4. As a Claude Code user, I want Stop to reconcile changed evidence and save memory, so that stale information is excluded from later retrieval.
5. As a project owner, I want Codex behavior unchanged, so that enabling Claude does not regress the existing integration.
6. As a project owner, I want both hosts to use one memory store and one MCP server, so that memories and validation rules remain consistent.
7. As a project owner, I want Claude configuration merged with existing `.claude/settings.json`, so that unrelated hooks and settings are retained.
8. As a project owner, I want repeated installation to be idempotent, so that configuration does not accumulate duplicate hooks or MCP entries.
9. As a multi-agent user, I want a Claude subagent's task state isolated from its main agent, so that one turn cannot reconcile another's changes.
10. As a user whose hook payload lacks `prompt_id`, I want Memory Stale to skip lifecycle work silently, so that normal Claude work is uninterrupted and two active turns never share a task file.
11. As a user outside a Git worktree, I want hooks to report a useful message without blocking normal host operation, so that Memory Stale remains non-blocking.
12. As a maintainer, I want malformed Claude payloads handled through the existing non-blocking failure contract, so that integrations fail safely.
13. As a reviewer, I want equivalent Codex and Claude turns to produce the same lifecycle result, so that host adapters do not change memory logic.
14. As a Claude Code user, I want `memory.capture` to validate exactly as it does in Codex, so that the persisted memory format is host independent.

## Implementation Decisions

### Confirmed observable test seam

The highest practical seam is each host adapter's public stdin/stdout hook entry point against a real temporary Git repository. Tests submit documented host JSON, observe hook output and task/memory artifacts, and run the existing MCP stdio server where capture is required. This is the seam stated in the request through its preference for adapter-level contract tests plus shared lifecycle tests; shared lifecycle operations are covered once rather than duplicating the complete suite per host.

### Shared lifecycle boundary

- Host-independent operations own repository discovery, snapshots, task-state persistence, retrieval, ledger append, automatic provenance, coverage checking, reconciliation, and memory persistence.
- Host adapters only validate and normalize their payloads, render the host-specific non-blocking output envelope, and call shared operations.
- The core contains no host-name branches. Codex parsing remains isolated from Claude parsing.
- Existing task persistence and memory schema remain unchanged. The normalized task identifier is persisted in the existing `turn_id` field.
- Claude context is returned through `hookSpecificOutput.additionalContext`; Codex continues using its existing output shape.
- Claude `PostToolUse` retains the existing ledger fields: tool name, tool-use identifier, and tool input. Tool response is not persisted.
- Claude Stop is ignored when `stop_hook_active` is true, preventing a recursive Stop hook cycle without introducing a Claude stale algorithm.

### Claude identity boundary

- `session_id`, `cwd`, and event-specific required fields are validated as non-empty strings.
- With `prompt_id`, the normalized identity is namespaced by Claude session, prompt, and any supplied `agent_id`.
- Without `prompt_id`, the adapter silently performs no lifecycle work rather than fabricating a potentially shared identity. It does not mention a Claude Code version in hook output.
- An `agent_id` is part of the identity when present; absent `agent_id` denotes the main agent. This keeps simultaneous main-agent and subagent turns isolated.

### Installation and instructions boundary

- The copied runtime remains under the target local skill and its environment and caches remain under `.git/memory-stale/runtime`.
- Claude hook commands invoke the copied runtime and the Claude hook adapter, with project-root-safe command paths and non-blocking timeouts.
- The installer merges only Memory Stale's exact hook records into Claude settings and retains unrelated entries. It writes configuration atomically.
- `.mcp.json` gains or preserves a `memory-stale` stdio entry that invokes the installed bootstrap. Its value must match a pre-existing compatible value; an incompatible collision fails clearly rather than overwriting it.
- The Claude instruction artifact communicates the same capture-once, behavior-or-guarantee claim, relevant evidence, and automatic-provenance requirements as the Codex skill. `.claude/napkin.md` is never modified by installation.

## Testing Decisions

- First red-green slice: a documented Claude `UserPromptSubmit` payload receives `hookSpecificOutput.additionalContext` with the capture protocol and the same retrieval result as the existing task-start lifecycle.
- Subsequent vertical slices cover Claude ledger recording, Stop reconciliation, prompt and agent identity isolation, silent handling of missing prompt identifiers, malformed payloads, non-Git execution, recursive Stop prevention, and parity with a Codex turn.
- Installer integration tests use real temporary Git repositories and existing Claude settings; they assert merge preservation, the installed runtime command, project MCP registration, and repeat installation idempotency.
- Existing Codex lifecycle and installation tests remain in the full suite.
- Expected values use documented JSON and real memory files rather than mocks of project-owned lifecycle modules.
- Run focused tests during every red-green slice; before completion run Ruff format check, Ruff lint, strict mypy, and the default full pytest suite.

## Out of Scope

- Embeddings, another LLM, hosted services, a second MCP server, or a separate Claude memory store.
- Changes to BM25, evidence fingerprints, persisted memory schema, supported grammars, or staleness semantics.
- A generic Claude plugin framework, global Claude installation, or execution without a Git repository.
- Updating `.claude/napkin.md`, publishing, committing, pushing, tagging, or opening a pull request.

## Further Notes

The `to-spec` workflow requests issue-tracker publication with a `ready-for-agent` label. No tracker configuration is available and the user authorized local repository work only, so publication is intentionally deferred.

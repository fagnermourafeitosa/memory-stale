# 42 — Antigravity harness support and mandatory harness CLI selection

## Problem Statement

Memory Stale currently supports Codex and Claude Code lifecycle hooks through dedicated adapters and installer targets. Antigravity IDE and CLI use a distinct lifecycle event protocol (`PreInvocation`, `PostToolUse`, `Stop`) with camelCase JSON payloads over stdin/stdout, and discovers MCP servers via local plugins or configuration. Additionally, the project installer previously defaulted to installing multiple hosts implicitly and used `--host` with ambiguous aliases (`both`). Users require first-class Antigravity support without regressing existing Codex and Claude lifecycles, with explicit, mandatory harness selection (`--harness <codex|claude|antigravity>`) in the installer.

## Solution

1. **Mandatory CLI harness argument**:
   - Refactor `install-project.sh` and `install_project.py` to require `--harness <codex|claude|antigravity>`.
   - Remove legacy `--host`, `all`, and `both` arguments. If `--harness` is missing or invalid, fail immediately with a clear usage error.
   - For `antigravity`, the installer sets up `.agents/hooks.json`, the project skill at `.agents/skills/memory-stale/SKILL.md`, and local plugin configuration at `.agents/plugins/memory-stale/plugin.json` and `.agents/plugins/memory-stale/mcp_config.json`.

2. **Antigravity Adapter (`src/memory_stale/antigravity_adapter.py`)**:
   - `PreInvocation`: Normalizes `conversationId` and `stepIdx` into task identity `antigravity:<conversationId>`, evaluates active memory against the user prompt, and outputs `{ "injectSteps": [ { "ephemeralMessage": "<capture protocol and active memories>" } ] }`.
   - `PostToolUse`: Filters for file-modifying and execution tools (`replace_file_content`, `multi_replace_file_content`, `write_to_file`, `run_command`), records tool executions into the task ledger, and outputs `{}`.
   - `Stop`: Runs deterministic Tree-sitter provenance capture and memory staleness reconciliation, persisting records atomically and returning `{}` in a non-blocking manner.

3. **Core Preservation**:
   - Zero changes to the deterministic core (memory storage format, OKF schema, Tree-sitter AST hashing, BM25S ranking, dependency graph). Codex and Claude adapters remain unchanged.

## User Stories

1. As an Antigravity user, I want active memories injected as ephemeral messages before model invocation, so that I have relevant context without polluting persistent transcript history.
2. As an Antigravity user, I want file modifications made via Antigravity tools recorded in the task ledger, so that automatic provenance accurately detects changed symbols.
3. As an Antigravity user, I want the `Stop` hook to reconcile changed code evidence and persist provenance records non-blockingly, so that outdated memories are marked stale.
4. As a project owner, I want the installer to require `--harness <codex|claude|antigravity>`, so that harness configuration is explicit and deterministic.
5. As a project owner, I want Antigravity MCP registered locally via `.agents/plugins/memory-stale/`, so that global user configuration is not polluted.
6. As a developer, I want existing Codex and Claude integrations to remain fully intact without behavior or performance regressions.
7. As an operator, I want hooks to handle missing identifiers or non-git environments safely with structured, non-blocking errors.

## Implementation Decisions

### Confirmed observable test seam

The highest practical seam is:
1. The public stdin/stdout entry points of `src/memory_stale/antigravity_adapter.py` executing against real temporary Git repositories.
2. The end-to-end installer command `install-project.sh` / `install_project.py` testing configuration generation, idempotency, and argument validation.

### Harness selection contract

- CLI syntax: `install-project.sh <target-git-repository> --harness <codex|claude|antigravity>`
- Missing `--harness`, missing harness value, or unrecognized harness value exits with status code 2 and a usage message on `stderr`.
- Only the specified harness artifacts and configuration files are generated or modified.

### Antigravity payload & lifecycle boundary

- **Identity**: Task identity is `antigravity:<conversationId>`. If `conversationId` is missing or empty, the hook execution performs a non-blocking no-op.
- **`PreInvocation`**: Reads `conversationId`, workspace paths, and prompt context from stdin; retrieves relevant active memories using existing deterministic BM25S retrieval; returns JSON object with `injectSteps` containing an `ephemeralMessage`.
- **`PostToolUse`**: Reads `toolCall.name` and arguments from stdin; appends tool record to the session ledger; returns `{}`.
- **`Stop`**: Reads execution metadata from stdin; reconciles automatic Tree-sitter provenance and stales invalidated memory documents; returns `{}`.
- **Error handling**: Any boundary exception is trapped and outputs a safe non-blocking response.

### Antigravity artifact layout

- `.agents/hooks.json`: Merges `PreInvocation`, `PostToolUse` (with tool matchers), and `Stop` hooks executing via the project runtime bootstrap.
- `.agents/plugins/memory-stale/plugin.json`: Declares the plugin metadata.
- `.agents/plugins/memory-stale/mcp_config.json`: Registers the local `memory-stale` stdio MCP server pointing to the isolated runtime script.
- `.agents/skills/memory-stale/SKILL.md`: Standard capture protocol skill instructions.

## Testing Decisions

- Test `install_project.py` requiring `--harness`, rejecting missing flags, and validating each harness target (`codex`, `claude`, `antigravity`).
- Test Antigravity `PreInvocation` hook output format (`injectSteps` with `ephemeralMessage`).
- Test Antigravity `PostToolUse` ledger logging across supported Antigravity tool names.
- Test Antigravity `Stop` reconciliation lifecycle against real Git workspace changes.
- Verify full regression suite (`ruff`, `mypy --strict`, `pytest`).

## Out of Scope

- Modifying global `~/.gemini/config/` files during installation.
- Changes to OKF schema, Tree-sitter grammars, or retrieval scoring.
- Generic fallback for unsupported hosts.

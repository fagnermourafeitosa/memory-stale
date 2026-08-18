# 43 — Project-local Codex MCP registration

## Problem Statement

The installer previously registered the `memory-stale` MCP server for Codex globally via `codex mcp add`. This mutated global user configuration, required the `codex` CLI binary on the host `PATH` during installation, and differed from Claude Code's project-local `.mcp.json` discovery. Users require strict project-local isolation across all supported harnesses, configuring Codex MCP through `.mcp.json` in the target repository without global side effects.

## Solution

1. **Project-local `.mcp.json` for Codex**:
   - The installer configures `memory-stale` in the target project's root `.mcp.json` for the `codex` harness, identical to `claude`.
   - Remove the `_register_mcp` function that invoked `codex mcp add`.
   - Remove the installation prerequisite requiring the `codex` CLI binary on `PATH`.

2. **Documentation & Contract Updates**:
   - Update `AGENTS.md` and `README.md` to state that Codex discovers the local runtime via the project `.mcp.json`, removing all references to global MCP registration.

## User Stories

1. As a Codex user, I want Memory Stale MCP configured locally in my project's `.mcp.json`, so that my machine's global configuration is never modified.
2. As an operator running in a minimal environment or CI, I want to install Memory Stale for Codex without having the `codex` CLI binary installed on `PATH`.
3. As a project owner, I want Codex and Claude Code to share the same `.mcp.json` declaration pointing to the installed runtime.
4. As a maintainer, I want repository instructions and documentation to accurately describe the project-local MCP discovery mechanism.

## Implementation Decisions

### Confirmed observable test seam

The highest practical seam is `tests/test_installer.py` executing `install(source, repository, "codex")` and `main(...)` against temporary Git repositories without a mocked `codex` executable on `PATH`. The test observes:
1. `.mcp.json` exists in the target repository with the `memory-stale` stdio server entry pointing to the installed bootstrap script.
2. `.codex/hooks.json` is configured with Codex lifecycle hooks.
3. No external process execution of `codex` is attempted.

### Configuration merging & idempotency

- `_mcp_configuration(repository)` reads or creates `.mcp.json`, merges the `memory-stale` server configuration, and checks for incompatible collisions.
- Repeated installations for `codex` are idempotent and preserve pre-existing unrelated `.mcp.json` servers.

## Testing Decisions

- Add/update tests in `tests/test_installer.py` asserting that `install(source, repository, "codex")` writes `.mcp.json` and `.codex/hooks.json` without invoking the `codex` CLI.
- Verify that full regression suite (`ruff format --check`, `ruff check`, `mypy src tests`, `pytest`) passes cleanly.

## Out of Scope

- Removing previously created global registrations from user home directories (`~/.codex/`).
- Changing Codex hook payloads or lifecycle behavior.

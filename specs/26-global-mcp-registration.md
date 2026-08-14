# 26 — Global Codex MCP registration for an installed project

## Problem Statement

The project installer writes a target `.mcp.json`, but the local Codex client
does not automatically load this file. Consequently, the installed
`memory-stale` server is absent from `codex mcp list` and `memory.capture` is
unavailable, even though the target runtime and hooks were copied correctly.

## Solution

After copying the project-local runtime, the installer registers the named
`memory-stale` stdio server through `codex mcp add`. The global Codex entry
uses the absolute path to the target repository's installed bootstrap, so its
code and runtime remain project-local while Codex can discover the server in a
new session.

## User Stories

1. As a Codex user, I want installation to make `memory-stale` appear in
   `codex mcp list` without a separate manual registration step.
2. As a project owner, I want the global registration to point at my project's
   copied runtime rather than the installer source checkout.
3. As a maintainer, I want a failed global registration to report an actionable
   error and not claim installation succeeded.

## Observable Test Seam

The highest seam is `scripts/install-project.sh` run against a temporary Git
repository with a controlled `codex` executable on `PATH`. The test observes
the exact `mcp add memory-stale -- sh <installed-bootstrap> -m
memory_stale.mcp_server` invocation and the copied target files.

## Expected Behavior

- A successful install invokes `codex mcp add memory-stale --` followed by
  `sh`, the absolute installed `run-python.sh` path, `-m`, and
  `memory_stale.mcp_server`.
- The target still receives the local skill and hook configuration.
- The installer no longer treats a target `.mcp.json` as the discovery source
  for the Codex MCP server.
- If `codex mcp add` fails, installation exits nonzero with its error preserved
  in an actionable message and does not report success.
- Public documentation describes that the registration is global but points to
  the installed project runtime, and that a new Codex session is needed.

## Implementation Constraints

- Keep the installed Python runtime and state inside the target repository.
- Use the supported `codex mcp add <name> -- <command>` interface; do not edit
  `~/.codex/config.toml` directly.
- Do not overwrite, remove, or silently replace an existing global
  `memory-stale` registration.
- Keep writes to target configuration atomic and preserve unrelated hook data.
- Update repository instructions and current public documentation to remove
  claims that global Codex configuration is untouched.

## Testing Decisions

- First red-green slice: an installation invokes the expected absolute-path
  `codex mcp add` command through a controlled process boundary.
- Second slice: a registration-process failure causes a nonzero installer exit
  and reports the failure.
- Run focused tests during the red-green cycle, then the full required code
  validation suite.

## Out of Scope

- Managing, removing, or upgrading an existing global registration.
- Registering multiple projects under the same MCP name.
- Changing memory capture, hooks, retrieval, or the deterministic memory
  engine.

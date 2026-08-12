# 10 — Installed runtime bootstrap

## Problem Statement

A newly installed plugin receives an empty `PLUGIN_DATA`. The current hooks use
`uv run --no-sync`, so the isolated environment does not contain runtime
dependencies and memory cannot operate outside the development checkout.

## Solution

Add a deterministic bootstrap shared by hooks and MCP that synchronizes the
isolated environment under `PLUGIN_DATA` from the plugin lockfile before running
the requested module.

## User Stories

1. As a user, I want the first execution to prepare the local runtime, so that the plugin works immediately after installation.
2. As a user, I want the cache and environment under `PLUGIN_DATA`, so that the plugin does not write to the global Python cache.
3. As a maintainer, I want frozen execution, so that installation respects the published lockfile.

## Implementation Decisions

- A single script under `scripts/` is the entry point for hooks and MCP.
- The script defines the environment and cache under `PLUGIN_DATA`, runs `uv sync --frozen`, and then runs `uv run --frozen --no-sync` for the requested module.
- The bootstrap does not use pip, write to the target repository, or require a global Python dependency installation.
- Already synchronized harnesses may set `MEMORY_STALE_SKIP_SYNC=1`; the installed plugin never defines this bypass. They point explicitly to the development `.venv` without reusing the root as `PLUGIN_DATA`.
- Bootstrap failures remain non-blocking for hooks through the existing adapters; MCP exits with an observable process error.

## Testing Decisions

- Seam confirmed by installation requirements: copy the plugin into an isolated directory, provide empty `PLUGIN_DATA`, and execute the real `UserPromptSubmit` command in a temporary Git repository.
- Verify `.venv` and cache creation only within `PLUGIN_DATA`, valid JSON on stdout, and success on a second execution.

## Out of Scope

- Marketplace distribution, public release, automatic updates, and new memory features.

## Further Notes

- This fix is a prerequisite for validating a real local installation.

# 10 — Installed runtime bootstrap

## Problem Statement

A newly installed project-local runtime receives no environment or cache. The current hooks use
`uv run --no-sync`, so the isolated environment does not contain runtime
dependencies and memory cannot operate outside the development checkout.

## Solution

Add a deterministic bootstrap shared by hooks and MCP that synchronizes the
isolated environment under the target Git metadata from the local runtime lockfile before running
the requested module.

## User Stories

1. As a user, I want the first execution to prepare the local runtime, so that the integration works immediately after installation.
2. As a user, I want the cache and environment under the target Git directory, so that the integration does not write to the global Python cache.
3. As a maintainer, I want frozen execution, so that installation respects the published lockfile.

## Implementation Decisions

- A single script under `scripts/` is the entry point for hooks and MCP.
- The script derives the target Git directory from its working directory, defines the environment and cache under `.git/memory-stale/runtime`, runs `uv sync --frozen`, and then runs `uv run --frozen --no-sync` for the requested module.
- The bootstrap does not use pip or require a global Python dependency installation.
- Already synchronized harnesses may set `MEMORY_STALE_SKIP_SYNC=1`; the installed runtime never defines this bypass. They point explicitly to the development `.venv` without reusing the target runtime cache.
- Bootstrap failures remain non-blocking for hooks through the existing adapters; MCP exits with an observable process error.

## Testing Decisions

- Seam confirmed by installation requirements: copy source artifacts into a temporary Git repository and execute the real target-local `UserPromptSubmit` command.
- Verify `.venv` and cache creation only within the target Git metadata, valid JSON on stdout, and success on a second execution.

## Out of Scope

- Marketplace distribution, public release, automatic updates, and new memory features.

## Further Notes

- This fix is a prerequisite for validating a real local installation.

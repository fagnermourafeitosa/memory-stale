# 24 — Runtime isolation in the README

## Problem Statement

The README lists `uv` and Python 3.10+ as requirements but does not explain
what the installed runtime does with them. A reader cannot tell whether
Memory Stale creates an isolated environment, where it lives, when packages
are installed, or whether it modifies the project's own Python environment.

## Solution

Document the installed runtime lifecycle beside the installation requirements.
State that the first hook or MCP invocation uses the installed lockfile to
create or reuse a `uv`-managed environment below the target repository's Git
directory, and that project and global Python environments are not modified.

## User Stories

1. As an adopter, I want to know why `uv` and Python are prerequisites before
   installing Memory Stale.
2. As a project maintainer, I want to know where runtime dependencies and
   caches are stored so that I can review their scope.
3. As a Python user, I want assurance that the integration does not alter my
   project's `.venv` or global site packages.

## Observable Test Seam

The public seam is `README.md`. Its installation section must accurately
describe the behavior of `scripts/run-python.sh` and the installer artifacts.

## Expected Behavior

- The README lists Git, `uv`, and Python 3.10+ as requirements.
- It explains the lockfile-backed `uv sync --frozen --no-dev` flow.
- It names `.git/memory-stale/runtime/.venv` as the isolated environment and
  `.git/memory-stale/runtime/` as the local runtime/cache root.
- It states that neither the target project's `.venv` nor global Python
  packages are modified.

## Implementation Constraints

- Keep the public documentation in English.
- Match the actual `uv` invocation and paths in `scripts/run-python.sh`.

## Testing Decisions

- This is documentation-only; verify the README against the runtime script
  without running the Python quality suite.

## Out of Scope

- Changing runtime synchronization, dependency resolution, or cache policy.
- Installing `uv` or Python for the user.

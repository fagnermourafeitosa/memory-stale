# 09 — Contribution workflow and Python environment

## Problem Statement

The project must prevent contract-free changes, unauthorized commits, unrelated
work mixed on one branch, and Python dependencies installed directly into the
global environment.

## Solution

Define a mandatory contribution workflow: a spec before every feature, bug, or
adjustment; a dedicated branch per unit of work; TDD for behavior; explicit
authorization before a commit; and `uv` as the sole manager for Python,
dependencies, the lockfile, and the virtual environment.

## User Stories

1. As a maintainer, I want every behavior change to have a spec, so that loose requests do not become ambiguous implementations.
2. As a maintainer, I want one branch per spec, feature, bug, or chore, so that independent changes are not mixed.
3. As a user, I want to authorize every commit, so that I retain control over repository history.
4. As a contributor, I want an isolated, reproducible Python environment, so that local tools do not depend on global Python.
5. As a contributor, I want one dependency and command manager, so that installation and CI use the same flow.
6. As a reviewer, I want standardized linting, formatting, typing, tests, and coverage, so that quality does not depend on the author's environment.

## Implementation Decisions

- `to-spec` is mandatory before implementing any feature, bug fix, or behavior adjustment. The spec must exist in the project's numbered spec directory and declare the observable test seam.
- No implementation begins from a loose request. Documentation and governance must also record a spec when they change the workflow.
- Each unit of work uses its own branch, named by category and subject.
- No agent may create a commit without explicit user authorization for that specific commit. Preparing changes does not imply authorization to commit.
- `uv` is the only permitted interface for creating the environment and resolving, installing, adding, removing, or executing Python dependencies.
- The project environment is `.venv`, created and managed by `uv`; `pip`, global Python, and shared environments are not used for project work.
- Development dependencies use the `dev` group; the lockfile is versioned.
- Quality gates remain Ruff, strict mypy, pytest, and branch coverage.

## Testing Decisions

- The seam for this change is a clean repository checkout: `uv sync` must create the isolated environment, and `uv run` commands must locate every quality tool.
- Configuration is validated by the TOML parser and `uv` itself.
- A public smoke test validates that the `src` layout installed by the project environment makes the `memory_stale` package importable.
- No artificial unit test is created for governance files; the test is the external bootstrap and repository validation flow.

## Out of Scope

- Implementing plugin features.
- Creating a commit, publishing a branch, or opening a pull request.
- Defining remote CI in this change.

## Further Notes

- This spec formalizes permanent repository rules and applies to agents and human contributors.

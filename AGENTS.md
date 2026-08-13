# Repository Instructions

## Product boundaries

- Build Memory Stale as a project-local Codex skill with associated local MCP
  registration, lifecycle hooks, and a deterministic local memory engine.
- Do not introduce a human-facing CLI as the primary product surface.
- Do not call another LLM. Semantic claims come from the Codex instance already
  performing the task; hooks and the core remain deterministic.
- Git is required. Never add file-level or unsupported-language fallbacks.
- Treat `README.md` as the public product description and `specs/` as the
  implementation contract. Resolve contradictions before coding.

## Spec-first is mandatory

- Write repository instructions and every numbered spec in English.
- Every feature, bug fix, refactor, behavior adjustment, tooling change, or
  repository workflow change must have a numbered spec created with the
  `to-spec` skill before implementation starts.
- Never implement from a loose request. First synthesize the request and
  settled decisions into `specs/NN-kebab-case.md`.
- The spec must identify the highest observable test seam, expected behavior,
  implementation constraints, testing decisions, and out-of-scope work.
- Confirm the seam before writing the first test. If implementation reveals a
  contract gap, update the spec before expanding scope.
- A request whose sole purpose is creating or refining a spec stops after the
  spec; it does not imply authorization to implement it.

## Git workflow and authorization

- Use one dedicated branch per spec, feature, fix, documentation change, or
  chore. Never mix independent work in one branch.
- Create or switch to the branch before editing. Use descriptive categories,
  such as `spec/03-symbol-indexing`, `feature/context-retrieval`,
  `fix/stale-ref-resolution`, `docs/readme`, or `chore/python-tooling`.
- Inspect the current branch and dirty worktree before starting. Preserve all
  pre-existing user changes and never move them between branches implicitly.
- Never create or amend a commit without explicit user authorization for that
  specific commit. A request to implement, test, stage, or prepare work is not
  permission to commit.
- After an explicitly authorized commit succeeds, integrate its dedicated branch
  into the local `main` branch with a fast-forward merge unless the user says not
  to. If fast-forward is unavailable, stop and ask for direction; commit
  authorization never implies permission to rebase, create a merge commit, or
  resolve conflicts. Remain on `main` after successful integration and do not
  delete the working branch automatically.
- Never push, tag, rebase, squash, or open a pull request unless the user
  explicitly requests that operation.

## TDD is mandatory

All feature work and bug fixes must use test-driven development.

1. Identify the public seam named by the relevant spec. If the seam is missing
   or ambiguous, stop and agree on it before writing tests.
2. Write one behavioral test for one vertical slice.
3. Run that test and observe it fail for the expected reason. A test that passes
   immediately does not establish the red phase.
4. Write only enough production code to make that test pass.
5. Run the focused test, then the relevant suite.
6. Repeat with the next behavioral slice.
7. Refactor only after behavior is green, during review, while keeping the full
   suite passing.

Documentation-only and tooling-only changes do not require a fabricated
failing test. Any production behavior change does.

## Test quality

- Test observable behavior through public interfaces, not private functions or
  implementation details.
- Prefer integration-style tests at the highest practical seam.
- Name tests as capabilities or outcomes, not internal method calls.
- Use independent literals and worked examples as expected values. Never
  recompute expected output with the same algorithm as production code.
- Mock only true system boundaries such as time, randomness, process execution,
  or an external service. Do not mock project-owned modules or assert internal
  call counts/order.
- Use temporary Git repositories and real files for lifecycle integration tests.
- Every supported tree-sitter grammar needs fixtures proving semantic changes
  become stale while comments and formatting do not.
- Every bug fix requires a regression test that fails before the fix.

## Python quality

- Support the Python version declared in `pyproject.toml`.
- Use `uv` exclusively for Python version selection, virtual environments,
  dependency resolution, locking, installation, and command execution.
- Keep the project environment isolated in `.venv`; never install project
  dependencies into the global Python or a shared environment.
- Add runtime dependencies with `uv add`, development dependencies with
  `uv add --dev`, remove them with `uv remove`, and commit the resulting
  `pyproject.toml` and `uv.lock` changes only after explicit authorization.
- Do not use `pip`, `pip-tools`, Poetry, Pipenv, Conda, or ad-hoc environment
  managers for this repository.
- Type all public interfaces and keep mypy strict clean. Avoid `Any`; isolate it
  at unavoidable third-party boundaries and narrow it immediately.
- Prefer small pure functions and immutable data at the core. Keep filesystem,
  Git, hooks, MCP transport, and rendering behind thin adapters.
- Use `pathlib.Path`, explicit encodings, context managers, and specific
  exception types.
- Never swallow exceptions silently. Convert boundary failures into structured,
  actionable errors while preserving the integration's non-blocking behavior.
- Keep writes atomic. Do not leave partially written memories or configuration.
- Avoid hidden global state. Pass clocks, randomness, process runners, and
  filesystem boundaries explicitly when determinism matters.
- Keep modules cohesive; do not create generic `utils.py` dumping grounds.
- Comments explain intent and constraints, not code already obvious from names.

## Required validation

When a change modifies production or test code, run the focused test throughout
the red-green cycle. Before considering that code change complete, run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Coverage is a guardrail, not a substitute for behavioral tests. New production
modules must remain at or above the configured branch-coverage threshold.

For a change with no production or test code modifications—including
documentation, specs, repository instructions, and metadata—do not run the
commands above solely for validation. Review and verify the changed artifact
directly instead.

## Change discipline

- Keep each change scoped to one spec or one coherent vertical slice.
- Do not add speculative abstractions for future grammars or features.
- Add dependencies only through `uv`, with a clear product reason.
- Update public documentation when observable behavior, configuration, or
  limitations change.
- Preserve unrelated user changes and never weaken tests, lint, typing, or
  coverage to make a change pass.

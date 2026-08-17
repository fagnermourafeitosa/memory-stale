# Napkin Runbook

## Curation Rules

- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)

1. **[2026-08-11] Require a spec before every code change**
   Do instead: use `to-spec`, store a numbered spec under `specs/`, confirm the public seam, then implement code on a dedicated branch; edit documentation directly on its own branch.

2. **[2026-08-11] Use uv with an isolated project environment**
   Do instead: manage dependencies and commands only through `uv` and keep them in the project `.venv`.

3. **[2026-08-11] Preserve project ideation in Markdown**
   Do instead: capture agreed product concepts in a clearly named project Markdown file before implementation.

4. **[2026-08-16] Keep repository evaluation intentional**
   Do instead: let the default suite exclude the 100-trial benchmark and run `uv run pytest -m repository_evaluation` only when the task explicitly requires it.

## User Directives

1. **[2026-08-17] Match semantic memory language to the originating prompt**
   Do instead: author claims, durability reasons, and retrieval terms in the user's prompt language; keep the deterministic runtime language-agnostic.

2. **[2026-08-11] Use TDD for all production behavior**
   Do instead: work in one red-green vertical slice at a time, test public behavior, and run full quality gates before completion.

3. **[2026-08-11] Never commit without explicit authorization**
   Do instead: prepare and validate changes, then wait for user approval before creating or amending any commit.

4. **[2026-08-11] Use a dedicated branch for each unit of work**
   Do instead: create a categorized branch for each spec, feature, fix, docs change, or chore before editing.

5. **[2026-08-11] Optimize this project for portfolio quality**
   Do instead: favor technically interesting, polished scope over an overly minimal pragmatic MVP.

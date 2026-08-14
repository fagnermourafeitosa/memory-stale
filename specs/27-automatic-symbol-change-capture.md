# 27 — Automatic source-change capture

This spec supersedes earlier no-file-level restrictions only for automatic
`source` evidence on code parsed by a supported grammar. It does not permit a
fallback for unsupported languages, configuration, Markdown, or arbitrary text.

## Problem Statement

Memory Stale currently records code changes in a turn ledger but persists no
memory unless the agent explicitly calls `memory.capture`. The feature therefore
depends on discretionary tool use instead of delivering automatic memory
maintenance after a code change.

## Solution

At `UserPromptSubmit`, record deterministic semantic signatures for every
supported source file. At `Stop`, compare that snapshot with the current source
files and automatically stage a deterministic `operation` memory for every new
or semantically changed source file before lifecycle reconciliation persists it.
Explicit MCP capture remains available for richer, agent-authored claims.

## User Stories

1. As a user, I want any semantic change to a supported code file to create
   memory without asking the agent to call an MCP tool.
2. As a user, I do not want comment-only, formatting-only, or normalized local
   variable changes to create automatic memory.
3. As a user, I want the automatic memory to remain code-anchored and become
   stale on a later semantic change to the same source file.
4. As a user, I want unsupported languages to remain excluded rather than
   receiving a file-level fallback.

## Observable Test Seam

The highest seam is a real `UserPromptSubmit` and `Stop` hook cycle in a
temporary Git repository. A semantic change anywhere in `service.py` must
persist an active Markdown memory without a `memory.capture` call; a later
semantic change must mark that revision stale and persist the new automatic
revision.

## Expected Behavior

- A current supported source file whose semantic signature differs from the
  turn-start signature receives one automatic `operation` memory.
- A supported source file introduced during the turn also receives automatic
  memory.
- The generated claim identifies the exact source path and says it changed
  during the task; its evidence is that source file as primary evidence.
- Comment-only, formatting-only, and normalized local-variable changes create
  no automatic memory.
- Deleted or unresolvable source files create no new automatic record, while
  existing memory still becomes stale through reconciliation.
- Automatic records and explicit `memory.capture` candidates reconcile in the
  same lifecycle run without duplicate revisions.

## Implementation Constraints

- Use only deterministic parsing and signature logic; do not call another LLM
  or invoke Codex recursively.
- Resolve only source files supported by the existing tree-sitter grammars. Do
  not create configuration, Markdown, or unsupported-language records.
- Store only compact source paths and fingerprints in the task ledger; do not
  snapshot source contents.
- Keep the lifecycle non-blocking and use atomic task/store writes.

## Testing Decisions

- First red-green slice: a changed Python source file persists an active
  automatic memory after `Stop`, with no MCP capture.
- Subsequent slices cover a no-op semantic signature, a newly added source
  file, and a later change that stales the previous automatic record.
- Run focused tests during red-green development, then the complete required
  validation suite.

## Out of Scope

- Natural-language summaries of code changes.
- Automatic dependency inference or automatic supporting evidence.
- Capturing deleted source files as new memories.
- Replacing explicit MCP capture for user-authored knowledge.

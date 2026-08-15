# 28 — Symbol-aware automatic memory

## Problem Statement

Automatic capture currently persists one `operation` memory per semantically
changed supported source file with a claim such as `Automatic change record:
app/main.py changed in this task.` The record is useful for exact-path
retrieval, but it does not identify the named code unit that changed. A later
task therefore cannot distinguish an added function, class, method, or type
from an unrelated edit in the same file without reading that file again.

## Solution

Make automatic capture symbol-aware. At turn start, record a compact,
deterministic inventory of resolvable named symbols and their semantic
fingerprints for each supported source file. At `Stop`, compare inventories and
persist one automatic `operation` memory for each added or semantically changed
symbol, using symbol evidence as the primary evidence. The generated claim must
name the symbol and its source path, and must identify whether the symbol was
introduced or changed. A source-file record remains only for a semantic change
that cannot be attributed to a named symbol, such as a supported module-level
declaration.

This makes an added Python symbol visible as, for example, `Automatic change
record: added symbol app/main.py:version.` It deliberately does not claim what
that symbol means or what user-visible behavior it establishes. Such facts
require a semantic judgment by the Codex instance, which continues to use
explicit `memory.capture` with appropriate code evidence.

## User Stories

1. As a developer, I want an automatic memory to name an added or changed
   function, class, method, type, or equivalent supported-language symbol, so
   that retrieval is more useful than a file-change notification.
2. As a developer, I want any new named code unit to be identifiable by its
   symbol, so that I can find the relevant code without treating all edits in
   its module as the same change.
3. As a developer, I want an automatic record for module-level semantic changes
   that have no named symbol, so that automatic coverage does not silently
   disappear for supported source files.
4. As a maintainer, I want automatic claims to remain deterministic and
   non-semantic, so that the local engine does not invent meaning, intent, or
   product contracts.

## Observable Test Seam

The highest seam is a real `UserPromptSubmit` and `Stop` hook cycle in a
temporary Git repository. Adding `def version()` to `app/main.py` must persist
an active automatic memory whose claim and primary evidence identify
`app/main.py:version`. Changing the function body in a later turn must stale
that revision and persist a new changed-symbol revision. A module-level
semantic change with no named symbol must retain a single source-file fallback
record.

## Expected Behavior

- A newly introduced resolvable symbol produces one `operation` memory with
  primary `symbol` evidence and the claim `Automatic change record: added
  symbol path:symbol.`
- A resolvable symbol whose semantic fingerprint changes produces one
  `operation` memory with primary `symbol` evidence and the claim `Automatic
  change record: changed symbol path:symbol.`
- A symbol is not recorded when only comments, formatting, or an accepted
  normalization changes.
- If one source file has several independently changed symbols, each receives
  its own automatic memory.
- If a supported file changes semantically but its named-symbol inventory is
  unchanged, it produces one source-file fallback record with the existing
  path-based claim.
- Deleted symbols create no new automatic memory; they still invalidate prior
  symbol-backed memories through lifecycle reconciliation.
- Existing explicit `memory.capture` behavior and evidence validation remain
  unchanged.

## Implementation Constraints

- Use only existing deterministic tree-sitter parsing and canonical symbol
  signatures. Do not call another LLM, invoke Codex recursively, inspect an
  assistant transcript, or infer the purpose, intent, behavior, or contract of
  code.
- Support only the project’s existing grammars. Preserve the deliberate
  exclusion of unsupported languages, Markdown, and configuration files from
  automatic capture.
- Keep task-state snapshots compact: locators and fingerprints only, never
  source text or diffs.
- Preserve atomic task/store writes and non-blocking hooks.
- Maintain backward compatibility when reading an in-flight task state that
  lacks the new symbol snapshot: it may use the existing source-file automatic
  capture for that turn.

## Testing Decisions

- Confirm the hook-cycle seam above before the first test.
- First red-green slice: an added Python function produces a symbol-backed
  automatic memory with an independently asserted claim and locator; the
  existing implementation must fail because it emits a source-file record.
- Subsequent slices cover a changed symbol, multiple changed symbols in one
  file, trivia and normalized-local changes, source fallback for a module-level
  change, deletion, and legacy in-flight task state.
- Exercise real files and temporary Git repositories; do not mock
  project-owned parsing, lifecycle, or storage modules.
- Run focused tests throughout, then all required format, lint, type, and test
  validation commands.

## Out of Scope

- Generating natural-language summaries of a code change's purpose, behavior,
  design rationale, or user-facing contract from source code.
- Framework-specific semantic parsing or any equivalent domain-specific
  inference.
- Automatic test or dependency discovery.
- Replacing Codex-authored `memory.capture` for durable semantic knowledge.

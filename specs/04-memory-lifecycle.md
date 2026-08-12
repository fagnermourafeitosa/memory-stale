# 04 — Memory store and lifecycle

## Problem Statement

Captured claims must become auditable memory, and memories tied to changed code must become stale deterministically.

## Solution

Implement a pure engine that receives memories, a ledger, and captures and returns persistable operations.

## User Stories

1. As a team, I want project memory that can be versioned with the project.
2. As a user, I want to know why a memory became stale.
3. As Codex, I want to create a memory with multiple refs changed during the same task.

## Implementation Decisions

- Memories live at `<repo>/.agents/skills/.agent-memory/memories/*.md` with structured front matter.
- The engine creates memory for a valid candidate and marks an existing active memory stale when its current signature diverges.
- Staleness records a reason per ref: changed, missing symbol, missing file, or unresolvable.
- The engine does not edit an active claim to represent a change; a new fact becomes new memory.
- Writes are atomic: failure does not leave partial memory.

## Testing Decisions

- Seam confirmed by continuous authorization: a pure public function receives the corpus, captures, and current ref states and returns the reconciled corpus; the Markdown store is tested through the public persisted directory.
- Test creation, multiple refs, each staleness reason, idempotency, and atomic writes.
- Test the engine as a single seam with pure inputs and outputs.

## Out of Scope

- HTML rendering, ranking, and hook calls.

## Further Notes

- Cache and ledger do not belong in the durable store.

# 06 — `/memory-stale dream`

## Problem Statement

Users need to trigger broad reconciliation without waiting for a normal task to change code.

## Solution

Add an explicit skill operation: `/memory-stale dream`.

## User Stories

1. As a user, I want to trigger a deliberate memory audit whenever I choose.
2. As a user, I want adjustments applied and summarized in the same flow.
3. As a maintainer, I want Dream not to rewrite active memory without evidence.

## Implementation Decisions

- Dream audits only stale memory, broken refs, and unresolvable symbols.
- The same Codex instance reviews context and uses `memory.capture` for new facts; there is no other LLM.
- Adjustments are applied directly, and the summary lists created memories, stale memories, and errors.
- Dream does not alter active memories without a verifiable reason.

## Testing Decisions

- Seam confirmed by continuous authorization: the public `dream` operation receives the repository, audits the real store, and returns a structured summary; the skill directs the same Codex instance to use that operation and `memory.capture`.
- Simulate a mixed corpus and verify the limited audit scope.
- Test the summary and non-blocking error propagation.

## Out of Scope

- Rewriting the entire store, embeddings, or automatic Dream execution.

## Further Notes

- Dream is a manual, user-triggered feature; the normal lifecycle remains automatic.

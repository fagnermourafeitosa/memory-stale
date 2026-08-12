# 11 — Preserve active memory during a read-only turn

## Problem Statement

A newly captured and correctly retrieved memory was marked `stale` at the end of
a turn that did not modify its symbol. This occurs when history contains an older
stale memory for the same ref: its historical signature overwrites the evidence
for the active memory. This creates a false positive, removes valid knowledge
from later turns, and degrades retrieval.

## Solution

Ensure that the hook cycle compares only changes that occurred after the
`UserPromptSubmit` snapshot. A `Stop` event with no change to the referenced file
must preserve the memory's signature, `active` status, and retrieval eligibility.

## User Stories

1. As a user, I want to query memory without invalidating it, so that reading is not confused with semantic change.
2. As an agent, I want to receive only the most recent active version, so that I do not use obsolete facts.
3. As a maintainer, I want a regression test through the public hook cycle, so that false-positive staleness is detected.

## Observable Test Seam

The confirmed seam is the public `UserPromptSubmit → Stop` cycle, executed by
the real hook commands in a temporary Git repository. The referenced file is
already modified before the turn begins, and the corpus contains both a stale
memory and an active memory for the same ref, reproducing the real working state.
The file remains byte-for-byte identical between the two hooks.

## Expected Behavior

- An active memory whose signature matches the current symbol remains `active` after a read-only turn.
- Pre-existing working-tree changes are not attributed to the current turn.
- The memory remains retrievable through an exact-ref query.
- Stale memories remain excluded, and unrelated queries remain empty.

## Implementation Constraints

- Git remains mandatory and is the only source of working-tree identity.
- Do not weaken detection of semantic changes made during the turn.
- Do not add global state, semantic heuristics, or calls to another LLM.
- Keep hooks non-blocking and writes atomic.

## Testing Decisions

- First test: a tracked file already dirty, an older stale memory with its previous signature, an active memory signed against current content, and a hook cycle with no new edits; observe failure before the fix and then require that only the current memory remain `active` and retrievable.
- Run the focused test in red and green, the relevant suite, and every quality gate.
- Repeat validation against the installed plugin after updating its cachebuster.

## Out of Scope

- Changing BM25 ranking, the context budget, or memory identity.
- Removing stale history.
- Creating a fallback for files outside Git or unsupported languages.

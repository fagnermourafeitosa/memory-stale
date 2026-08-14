# 00 — System contract

## Problem Statement

Define shared boundaries before building adapters or memory logic.

## Solution

Establish contracts, states, and the order of the following specs.

## User Stories

1. As a maintainer, I want explicit boundaries, so that modules do not create conflicting rules.
2. As a user, I want automatic memory without another LLM or a manual CLI.

## Implementation Decisions

- Product: project-local Codex `memory-stale` skill with a local MCP server and hooks.
- Git is required; without Git, the local integration reports its state and does not operate.
- States: `active` and `stale`. A ref change marks memory stale; there is no implicit supersession.
- No unsupported-language fallback. Automatic capture may use deterministic
  source-file evidence for code resolved by a supported grammar.
- Memory failures never block the Codex task.
- Order: 01 runtime, 02 capture, 03 indexing, 04 lifecycle, 05 retrieval, 06 dream, 07 report/config, 08 tests.

## Testing Decisions

- Each subsequent spec validates its contract without requiring a real Codex session.

## Out of Scope

- Implementing any module in this spec.

## Further Notes

- Every shared product decision belongs here rather than being duplicated across task specs.

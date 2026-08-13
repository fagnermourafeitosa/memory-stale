# 13 — Staleness requires revalidation

**Status: Done (2026-08-11)**

## Problem Statement

The product currently associates a memory with structural signatures and marks
it `stale` when any recorded evidence changes. Public language can still imply
that this result proves the claim became false, even though the engine can only
establish that the observed evidence is no longer identical. This overstatement
weakens the technical thesis and hides both unnecessary revalidations and
semantic changes outside the recorded refs.

## Solution

Define `active` and `stale` as provenance-validation states rather than truth
values for a claim. An `active` revision has resolvable recorded evidence with
the fingerprints observed at capture. A `stale` revision has at least one item
of evidence that changed, was removed, or became unresolvable and requires
revalidation before returning to normal context. The product retains the names
`active` and `stale` while stating explicitly that `active` does not prove truth
and `stale` does not prove falsehood.

## User Stories

1. As a user, I want to understand that `stale` means “requires revalidation,” so that I do not treat the diagnosis as proof of falsehood.
2. As a user, I want to understand that `active` means “recorded evidence is unchanged,” so that I do not assume the evidence set is complete.
3. As a maintainer, I want one definition of the states, so that the README, skill, MCP tools, report, and specs do not express contradictory contracts.
4. As a maintainer, I want to preserve conservative invalidation, so that a conceptual correction does not silently reduce context protection.
5. As a project evaluator, I want to distinguish evidence validity from semantic truth, so that the product's scientific limits are verifiable.
6. As Codex, I want only `active` revisions in normal context, so that claims whose provenance changed remain excluded from automatic use.

## Implementation Decisions

- The public product thesis is “memory provenance with deterministic revalidation when source evidence changes.”
- `active` means only that every recorded item of evidence still matches its observed fingerprint; it does not mean the claim was proven or the provenance is complete.
- `stale` means that at least one recorded item of evidence changed, disappeared, or could not be resolved; it does not mean the claim was refuted.
- Structural change remains a conservative revalidation trigger. Comments and formatting remain outside the structural signature.
- `stale` revisions remain excluded from normal context and preserved for audit.
- Every public surface that describes invalidation, validity, or truth uses the same vocabulary, including documentation, skill instructions, MCP descriptions, and reports.
- The observable lifecycle does not change in this spec; it corrects the epistemic contract and the language used to present it.
- Incomplete provenance and unrecorded dependencies are explicit limitations.

## Testing Decisions

- Highest seam confirmed: the local integration's observable public surfaces and the lifecycle already exercised by the installed harness.
- This is a contract and documentation change; no artificial red test will be created for editorial text.
- Existing lifecycle and end-to-end tests continue to prove that changed evidence produces `stale` and that `stale` revisions do not enter context.
- If MCP descriptions or rendered content change structurally, tests observe the complete public response rather than helper functions or internal calls.
- Documentation review verifies that no surface claims the engine detects semantic falsehood.

## Out of Scope

- Changing claim or evidence-revision identity.
- Reactivating a claim after revalidation.
- Adding new evidence types or transitive dependencies.
- Measuring unnecessary revalidation or missed semantic-change rates.
- Adding embeddings, another LLM, a vector database, GraphRAG, or local semantic inference.

## Further Notes

- This spec is the conceptual prerequisite for every subsequent spec.
- “Invalidation” remains acceptable when its object is evidence validation rather than claim truth.

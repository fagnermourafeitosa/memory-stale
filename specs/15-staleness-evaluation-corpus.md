# 15 — Staleness evaluation corpus

**Status: Done (2026-08-12)**

## Problem Statement

The lifecycle uses structural change as a conservative proxy for revalidation,
but the project does not measure when that proxy reacts to semantically
irrelevant changes or fails to react because a change occurred outside recorded
evidence. Without a labeled corpus, decisions about granularity, evidence sets,
or transitive dependencies remain anecdotal, and there is no baseline for
evaluating whether the architecture improves the product's differentiator.

## Solution

Add a small, versioned, reviewable corpus of before-and-after scenarios with
claims, recorded evidence, a labeled semantic outcome, and the expected
lifecycle result. A deterministic evaluator calculates separate metrics for
semantically unnecessary revalidation and undetected semantic change. Labels
are independent human-authored examples; no LLM judges truth during evaluation.

## User Stories

1. As a maintainer, I want to measure unnecessary revalidation, so that I understand the cost of the conservative heuristic.
2. As a maintainer, I want to measure missed semantic changes, so that I understand the risk of incomplete provenance.
3. As a contributor, I want reproducible scenarios, so that indexer or lifecycle changes can be compared with a baseline.
4. As an evaluator, I want to separate deterministic behavior from labeled truth, so that metrics do not confuse contract with semantics.
5. As a maintainer, I want coverage of every supported grammar, so that improvements are not inferred from one language.
6. As a user, I want instrumentation and equivalent refactors represented in measurements, so that common false-stale cases are visible.
7. As a user, I want dependency and configuration changes represented in measurements, so that architectural false negatives are visible.
8. As a contributor, I want labels and baselines updated deliberately, so that recomputed expectations do not hide regressions.

## Implementation Decisions

- Each scenario contains prior state, subsequent state, an independent claim, a recorded evidence snapshot, and a semantic label of `preserved` or `changed`.
- The semantic expectation is literal and reviewed; it is never calculated by the same algorithm as the product.
- The evaluator runs the public lifecycle against fixtures and records whether the revision remained `active` or became `stale`.
- `unnecessary_revalidation_rate` counts claims labeled `preserved` that the engine marked `stale`.
- `missed_semantic_change_rate` counts claims labeled `changed` that the engine kept `active`.
- Semantic metrics evaluate product trade-offs; they do not redefine `stale` as false or make conservative revalidation a bug by itself.
- At minimum, the corpus covers instrumentation, logging, metrics, equivalent refactoring, relevant literal changes, control-flow changes, rename or deletion, indirect dependency changes, configuration, comments, and formatting.
- Every supported grammar has fixtures for a preserving change and a local semantic change. Cross-cutting cases may begin with languages that express the scenario best without claiming universal coverage.
- Baseline results are versioned, and changes require an explanation alongside intentional behavior adjustments.
- The evaluator is a development and test surface, not a human-facing CLI as the primary product surface.
- The corpus does not call another model, use embeddings, or depend on the network.

## Testing Decisions

- Highest seam confirmed: a deterministic evaluator consumes the versioned corpus and the public lifecycle and runs within the normal project suite.
- Corpus schema validation provides actionable messages for incomplete scenarios, invalid labels, or inconsistent evidence locators.
- Tests prove formulas with a minimal set of literal results without recomputing expectations through the production algorithm.
- An instrumentation scenario demonstrates semantically unnecessary revalidation under the structural baseline.
- An indirect MFA policy scenario demonstrates a missed semantic change while only the local ref is recorded.
- Comment and formatting fixtures continue to prove the absence of structural change for every supported grammar.
- The suite distinguishes a mechanical lifecycle regression from a deliberate change to semantic metrics.

## Out of Scope

- Automatically optimizing the lifecycle to improve metrics.
- Using an LLM as the label judge.
- Defining quality thresholds as a public promise before a baseline exists.
- Adding evidence sets, evidence types, or a dependency graph.
- Measuring lexical or semantic retrieval quality.
- Turning the evaluator into a service, remote dashboard, or primary CLI.

## Further Notes

- This spec depends on the definitions in spec 13 and runs against the revisioned model from spec 14.
- The corpus guides the priority of later specs without blocking the known evidence-revision fix.

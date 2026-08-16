# 20 — LLM-Wiki positioning and repository-scale evaluation

**Status: Done (2026-08-12)**

## Problem Statement

Memory Stale can be mistaken for a system with no persistent memory when its
staleness mechanism is described without its capture and retrieval lifecycle.
That would be inaccurate: it persists durable claims and automatically injects
eligible active claims in later Codex tasks. It also risks being positioned as
an alternative to Karpathy's LLM-Wiki pattern even though that pattern already
describes persistent, LLM-maintained knowledge.

The current labeled evaluation corpus measures structural staleness on isolated
before-and-after fixtures. It does not yet provide repository-scale,
end-to-end statistical evidence that the public lifecycle makes the correct
availability decision after realistic Git changes.

## Solution

Document Memory Stale as a specialized, complementary implementation of
persistent agent memory for evolving codebases: an integrity layer that uses
code-anchored evidence to prevent unsupported claims from being injected until
they are revalidated. Do not claim that LLM-Wiki lacks memory or maintenance.

Plan and later implement a deterministic, versioned repository evaluation
suite. Each trial creates a temporary Git repository, captures a memory through
the public lifecycle, applies a labeled change, completes lifecycle processing,
and observes whether a later prompt receives the memory as active context.

## User Stories

1. As a prospective user, I want to understand that Memory Stale has persistent
   memory and how it relates to LLM-Wiki.
2. As a maintainer, I want evidence that the safety boundary works in real
   repositories rather than only in isolated source fixtures.
3. As a maintainer, I want the suite to distinguish correct invalidation from
   unnecessary revalidation and missed semantic changes.
4. As a contributor, I want deterministic statistics and a versioned baseline
   so that product trade-offs remain visible as lifecycle behavior changes.

## Implementation Decisions

### Positioning

- State the full lifecycle explicitly: durable capture, Markdown persistence,
  active-context retrieval, evidence revalidation, and immutable revision
  history.
- Describe an LLM-Wiki as persistent, LLM-maintained compiled knowledge. Do
  not assert or imply that it cannot update a claim after a source changes.
- Describe Memory Stale's distinct enforcement point precisely: a divergence in
  recorded evidence makes the revision `stale` and excludes it from ordinary
  context before an LLM maintenance or recompilation pass can repair it.
- Make no claim that `active` proves semantic truth or that `stale` proves a
  claim false.
- Position the systems as complementary: a broad wiki owns exploratory and
  documentary knowledge; Memory Stale supplies provenance and freshness
  enforcement for code-anchored facts.

### Repository evaluation plan

- Add a versioned, human-labeled manifest of repository trials. Each trial
  defines a repository blueprint, initial files, initial commit, capture claim
  and typed evidence, a subsequent Git change, later retrieval prompt, and
  independent semantic label (`preserved` or `changed`).
- Build every trial in a temporary Git repository. The runner must execute the
  real public hook/MCP boundaries and inspect persisted Markdown and subsequent
  `UserPromptSubmit` context. It must not call private lifecycle, store, or
  indexer functions as the system under test.
- One labeled claim/revision is one statistical observation. A trial's observed
  classifier output is `stale` when the claim is excluded after reconciliation,
  and `active` when it remains eligible and is returned for its exact retrieval
  prompt.
- Report the complete confusion matrix: true stale (`changed` → `stale`), false
  stale (`preserved` → `stale`), missed change (`changed` → `active`), and true
  active (`preserved` → `active`). Report counts before rates.
- Derive `stale_recall`, `stale_precision`, `specificity`,
  `unnecessary_revalidation_rate`, `missed_semantic_change_rate`, and overall
  accuracy. Report Wilson 95% intervals for rate metrics, but label them
  descriptive rather than population estimates; this is a curated corpus, not
  a random sample of all repositories.
- Keep capture failures, hook failures, unresolved locators, and retrieval
  misses as separate operational outcomes. They must not silently become a
  favorable `stale` result or be mixed into semantic classification metrics.
- Add a checked-in JSON or YAML baseline with the matrix, derived metrics,
  corpus version, and per-trial outcome. Any intentional baseline change must
  explain which trial results changed and why.

### Trial families

- Direct local semantic changes: literals, parameter contracts, control flow,
  return values, permission checks, and error handling.
- Semantically preserving changes: comments, formatting, import reordering,
  symbol-local equivalent refactors, and test-only changes that do not alter a
  recorded behavior.
- Conservative false-stale cases: instrumentation, logging, metrics, tracing,
  harmless guard extraction, and equivalent implementation rewrites.
- Incomplete-provenance false-active cases: an unchanged primary symbol whose
  observable behavior changes through a configuration, schema, supporting
  evidence, indirect policy, or dependency.
- Evidence-graph cases: one-, two-, and three-hop dependencies, shared
  supporting evidence, cycles, and changed nodes whose deterministic path must
  appear in the stale reason.
- Repository-shape cases: multi-module imports, source plus tests, source plus
  configuration/schema, dirty baseline, unrelated simultaneous edits, a new
  commit during the task, deletion, rename, and an unsupported or unresolvable
  locator rejected at capture.
- Cover every supported grammar with at least one `changed` and one `preserved`
  repository trial. Cross-language dependency examples must be explicit rather
  than inferred by an automatic call graph.

## Testing Decisions

- Highest seam to confirm before implementation: the real hook commands and
  real `memory.capture` MCP process operate inside a temporary Git repository;
  a later real `UserPromptSubmit` event is the final availability observation.
- First red-green slice: a two-trial Python repository manifest produces one
  true-stale and one true-active result, with literal matrix counts and no
  mocked project modules.
- Subsequent slices add one trial family at a time, beginning with direct,
  preserving, and incomplete-provenance scenarios. Each addition supplies
  independently written labels and expected literal outcomes.
- Tests must assert the persisted status and the later injected context. Where
  stale, assert the item-specific reason; where active, assert the expected
  claim is injected by an exact path or symbol prompt.
- The normal suite validates corpus schema and deterministic ordering through
  small representative trials. Exact full-corpus statistics and baseline
  consistency run only through the explicit repository-evaluation marker; the
  heavy corpus must never run as part of the normal suite.
- Run the required quality gates before completion:

  ```bash
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src tests
  uv run pytest
  ```

## Out of Scope

- Claiming statistical generalization from a curated corpus to all real-world
  codebases.
- Calling another LLM, using an LLM as a label judge, or introducing embeddings
  or a remote benchmark service.
- Automatically tuning staleness rules to optimize the reported metrics.
- Implementing a general LLM-Wiki, source ingestion system, session compiler,
  or cross-agent knowledge base.
- Changing the current lifecycle behavior as part of the README positioning
  work.

## Further Notes

- This work extends, rather than replaces, spec 15's isolated structural
  corpus. The two datasets answer different questions: unit-level structural
  behavior and end-to-end repository behavior.
- Corpus labels are a reviewed oracle about whether a particular claim remains
  semantically supported. They are intentionally independent from the product
  algorithm.

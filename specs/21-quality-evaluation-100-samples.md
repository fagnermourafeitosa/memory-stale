# 21 — Quality evaluation with 100 semantically reviewed samples

**Status: Done (2026-08-12)**

## Problem Statement

The repository-scale lifecycle result currently reports 88.9% accuracy from 18
curated trials. Fourteen observations are two nearly identical source changes
repeated across seven grammars, so the aggregate overweights grammar
compatibility and understates uncertainty across distinct semantic situations.
The two deliberately adverse examples also have invalid or incomplete semantic
oracles: the instrumentation fixture calls an undefined function, while the
configuration fixture claims a behavioral dependency that its source never
consumes. The result is reproducible, but it is not yet a credible measurement
of Memory Stale's semantic availability decisions.

## Solution

Replace the 18-trial repository corpus with exactly 100 independently identified,
explicitly labeled, and reviewable trials. Keep the real hook and MCP lifecycle as the system
under test, correct every fixture so its label follows from complete source and
configuration, and record an explicit label rationale and semantic case group
for auditability. Balance changed and preserved labels, cover every supported
grammar without treating grammar translations as independent semantic breadth,
and include realistic direct changes, preserving edits, conservative
false-stale cases, incomplete-provenance cases, evidence graphs, and repository
shape changes.

Extend the checked-in result with attempted and classifiable counts, per-family
confusion matrices, per-family accuracy, and an unweighted macro-family
accuracy. Retain aggregate counts and rates for regression comparison, but
describe them as corpus scores rather than estimated real-world accuracy.

## User Stories

1. As a maintainer, I want 100 auditable samples so that one or two hand-picked
   edge cases do not dominate the quality claim.
2. As a reviewer, I want each semantic label justified by the complete fixture,
   so that narrative intent cannot contradict executable or observable behavior.
3. As a contributor, I want grammar compatibility separated from semantic
   diversity, so that translations of one example do not inflate confidence.
4. As a product evaluator, I want family-level and macro metrics, so that a
   strong result on trivial local edits cannot hide weak provenance behavior.
5. As a user, I want public documentation to state exactly what the corpus score
   can and cannot establish about accuracy.

## Observable Contract

- `evaluator.repository_lifecycle.evaluate_repository_corpus(...)` remains the
  highest public evaluation seam.
- `evaluator/corpus/repository-lifecycle-corpus.yaml` contains exactly 100
  trials, 50 labeled `changed` and 50 labeled `preserved`.
- Every trial has a non-empty `semantic_case` and `label_rationale` independent
  of the observed lifecycle result.
- Semantic case identifiers group translated or closely related variants. The
  evaluator rejects duplicate trial IDs and requires at least two distinct case
  groups in every multi-sample family.
- The corpus covers Python, JavaScript, TypeScript, Go, Java, Kotlin, and Rust,
  while the result reports family metrics so those variants do not masquerade
  as independent real-world sampling.
- The result records `attempted_count`, `sample_count`, operational outcomes,
  the aggregate confusion matrix, aggregate rates, family matrices and rates,
  and `macro_family_accuracy` computed as the unweighted mean of classifiable
  family accuracies.
- Operational failures remain outside the semantic confusion matrices, but
  `attempted_count` prevents them from disappearing from the result.
- The checked-in baseline records every trial outcome and must match a fresh
  evaluation exactly.

## Sample Design

The 100 observations must span these families without relying exclusively on
literal-return and comment-only mutations:

- direct local semantic changes: return values, branches, default parameters,
  comparisons, error behavior, permission checks, and data transformations;
- semantically preserving edits: comments, formatting, equivalent expressions,
  local renames, harmless extraction, and import or declaration reordering;
- conservative false-stale candidates: defined no-op logging, metrics, tracing,
  caching that preserves the claim, and equivalent implementation rewrites;
- incomplete provenance: primary symbols that visibly consume changed config,
  policy, schema, constants, or dependencies not included in captured evidence;
- evidence graphs: one-, two-, and three-hop dependencies, shared support,
  configuration evidence, and cycles with deterministic stale reasons;
- repository shape: deletion, rename, multi-module movement, unrelated edits,
  source-plus-test changes, and simultaneous changes.

The corrected instrumentation samples must define their instrumentation boundary
and preserve the stated claim. Configuration or dependency samples must include
source code that actually consumes the changed value. A label rationale must
state why the exact claim is preserved or changed, not merely restate the label.

## Implementation Constraints

- Do not call an LLM or derive labels from Memory Stale's own output.
- Keep the evaluator deterministic and local, using temporary Git repositories,
  the real hook commands, the real `memory.capture` MCP process, persisted
  Markdown, and later `UserPromptSubmit` context.
- Do not add a human-facing CLI or a runtime dependency.
- Do not claim population-level accuracy or use Wilson intervals as evidence of
  generalization from the curated corpus.
- Preserve the older isolated structural corpus; it answers a separate question.
- Keep runtime bounded enough for the normal test suite and deterministic on the
  Python version declared by `pyproject.toml`.

## Testing Decisions

- Highest seam confirmed: invoke `evaluate_repository_corpus(...)` with a
  versioned manifest and observe the returned aggregate and family results plus
  the checked-in YAML baseline.
- First vertical slice: a small manifest with explicit semantic cases produces
  literal attempted/classifiable counts and two literal family matrices. The
  existing implementation must fail because these public result fields do not
  exist.
- Second slice: schema validation rejects a missing semantic case or rationale.
- Third slice: the checked-in corpus proves exact count, 50/50 label balance,
  supported-grammar coverage, family breadth, corrected adverse fixtures, and a
  reproducible baseline.
- Expected matrices and macro values are independent literals in tests and the
  checked-in result; tests must not calculate their own expected values with the
  production metric implementation.
- Before completion run:

  ```bash
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src tests evaluator
  uv run pytest
  ```

## Out of Scope

- Claiming that the 100 curated trials estimate accuracy across all repositories.
- Random sampling from public repositories or building a patch-mining pipeline.
- LLM judging, embeddings, semantic retrieval ranking, or natural-language
  retrieval quality measurement.
- Executing every supported language toolchain in CI.
- Automatically tuning Memory Stale behavior to improve the checked-in score.
- Changing capture, lifecycle, evidence resolution, or retrieval behavior.

# 41 — Retrieval ranking metrics and standardized English reporting

## Problem Statement

Memory Stale evaluates retrieval performance by checking binary inclusion of target memories inside the injected top-k prefix, alongside silence and precision metrics. However, binary inclusion ignores rank position: placing the target memory at position #1 versus position #5 provides different attentional focus for the consuming LLM. Furthermore, metric naming across the public documentation, evaluator output schemas, and HTML health reports can be standardized with canonical Information Retrieval (IR) terminology in English (such as MRR, NDCG@5, Target Recall@5, and Micro-Precision@5) to make quality benchmarks immediately clear to evaluators.

## Solution

Extend the local deterministic evaluation suite with position-aware ranking metrics:
1. **Mean Reciprocal Rank (MRR)**: Measures the reciprocal rank ($1/\text{rank}$) of the first relevant target memory among retrieved candidates ($0.0$ if absent).
2. **Normalized Discounted Cumulative Gain at K (NDCG@5)**: Computes position-discounted gain using binary relevance ($1$ for expected target, $0$ for distractors) normalized by ideal DCG.
3. **Standardized English Naming in Documentation & Reports**: Unify metric names in `README.md`, HTML health reports, and evaluation schemas with standard IR conventions (`MRR`, `NDCG@5`, `Target Recall@5`, `Precision@5`, `Silence / Exclusion Rate`).

All metric calculations remain 100% deterministic and local, with zero external LLM calls or vector dependencies.

## User Stories

1. As an evaluator, I want position-aware ranking metrics (MRR and NDCG@5), so that I can observe whether the relevant memory is ranked at the top of the context rather than merely entering the top-5 prefix.
2. As a researcher, I want MRR and NDCG calculated deterministically from ground truth trial targets, so that evaluation remains fast, reproducible, and offline without calling an external LLM.
3. As a developer reading the `README.md` and HTML health report, I want standard English Information Retrieval nomenclature, so that evaluation results are unambiguous and comparable with standard RAG benchmarks.
4. As a maintainer, I want existing freshness/lifecycle confusion matrices and counterfactual term-assisted metrics preserved, so that earlier baseline comparisons remain valid.
5. As a maintainer, I want the evaluator result schema versioned, so that historical result YAMLs and fresh runs remain machine-readable and backward-compatible.

## Implementation Decisions

- Extend `evaluator.repository_lifecycle.evaluate_repository_corpus(...)` to compute `mrr` and `ndcg_5` across all retrieval trials where a target is expected.
- Define binary target relevance: relevance = 1 if candidate memory matches expected target memory ID; relevance = 0 for all distractor or unrelated memories.
- Reciprocal Rank for trial $i$: if target appears at 1-based rank $r \le 5$, $RR_i = 1/r$; otherwise $RR_i = 0.0$. MRR is the arithmetic mean across positive target trials.
- DCG@5 for trial $i$: $\sum_{r=1}^{\min(5, |\text{retrieved}|)} \frac{rel_r}{\log_2(r + 1)}$. Since only 1 target is relevant per trial, IDCG@5 = 1.0, so $\text{NDCG@5}_i = \text{DCG@5}_i$. Mean NDCG@5 is averaged across target retrieval trials.
- Update `evaluator/results/*.yaml` schemas to store `mrr` and `ndcg_5` under `retrieval_metrics`, `retrieval_partitions`, and trial-level entries (`target_rank`).
- Standardize English labels in `src/memory_stale/reporting.py` (HTML health report) and `README.md` Measured Evaluation tables.
- Keep execution fully deterministic with no external API calls or LLM dependencies.

## Testing Decisions

- Highest observable seam: `evaluator.repository_lifecycle.evaluate_repository_corpus(...)`.
- TDD slice 1: Unit tests for MRR and NDCG@5 calculation helper functions on known ranking permutations (rank 1, rank 2, rank 5, unretrieved).
- TDD slice 2: Corpus evaluation test asserting `mrr` and `ndcg_5` fields in returned result dictionaries.
- TDD slice 3: Full 100-trial repository evaluation run (`uv run pytest -m repository_evaluation`) recording a dated baseline result file.
- Before completion validation:
  ```bash
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src tests evaluator
  uv run pytest
  ```

## Out of Scope

- Using an external LLM or embeddings to judge semantic similarity of ranking candidates.
- Graded (non-binary) human relevance judgments beyond target memory ID matches.
- Modifying retrieval scoring weights or BM25 parameters.
- Changing MCP server core transport protocols.
- Committing or pushing without explicit user authorization.

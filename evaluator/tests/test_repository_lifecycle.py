from pathlib import Path

import pytest

from evaluator.repository_lifecycle import (
    ConfusionMatrix,
    assert_repository_baseline,
    evaluate_repository_corpus,
)


def test_repository_trials_observe_real_lifecycle_availability(tmp_path: Path) -> None:
    repository_root = Path(__file__).parents[2]
    corpus = tmp_path / "repository-corpus.yaml"
    corpus.write_text(
        """version: 1
trials:
  - id: python-literal-change
    family: direct-local
    label: changed
    initial_files:
      service.py: |-
        def compute():
            return 1
    capture_files:
      service.py: |-
        def compute():
            return 2
    capture:
      kind: behavior
      claim: Compute returns two.
      durability_reason: Callers rely on the result.
      evidence:
        - type: symbol
          role: primary
          locator: service.py:compute
    change_files:
      service.py: |-
        def compute():
            return 3
    retrieval_prompt: service.py:compute
  - id: python-comment-only
    family: preserving
    label: preserved
    initial_files:
      service.py: |-
        def compute():
            return 1
    capture_files:
      service.py: |-
        def compute():
            return 2
    capture:
      kind: behavior
      claim: Compute returns two.
      durability_reason: Callers rely on the result.
      evidence:
        - type: symbol
          role: primary
          locator: service.py:compute
    change_files:
      service.py: |-
        # implementation comment
        def compute():
            return 2
    retrieval_prompt: service.py:compute
""",
        encoding="utf-8",
    )

    result = evaluate_repository_corpus(
        corpus,
        tmp_path / "repositories",
        repository_root,
    )

    assert result.operational_outcomes == ()
    assert result.sample_count == 2
    assert result.matrix == ConfusionMatrix(
        true_stale=1,
        false_stale=0,
        missed_change=0,
        true_active=1,
    )
    assert [
        (trial.identifier, trial.lifecycle_status, trial.retrieval_status)
        for trial in result.trials
    ] == [
        ("python-comment-only", "active", "active"),
        ("python-literal-change", "stale", "stale"),
    ]
    assert result.metrics.stale_recall.count == 1
    assert result.metrics.stale_recall.denominator == 1
    assert result.metrics.stale_recall.rate == 1.0
    assert result.metrics.stale_recall.wilson_interval == pytest.approx((0.2065, 1.0), abs=0.0001)
    assert result.metrics.unnecessary_revalidation_rate.rate == 0.0
    assert result.metrics.unnecessary_revalidation_rate.wilson_interval == pytest.approx(
        (0.0, 0.7935), abs=0.0001
    )
    assert result.metrics.overall_accuracy.rate == 1.0

    baseline = tmp_path / "repository-baseline.yaml"
    baseline.write_text(
        """version: 1
corpus_version: 1
sample_count: 2
matrix:
  true_stale: 1
  false_stale: 0
  missed_change: 0
  true_active: 1
metrics:
  stale_recall: {count: 1, denominator: 1, rate: 1.0, wilson_95: [0.20654931437723745, 1.0]}
  stale_precision: {count: 1, denominator: 1, rate: 1.0, wilson_95: [0.20654931437723745, 1.0]}
  specificity: {count: 1, denominator: 1, rate: 1.0, wilson_95: [0.20654931437723745, 1.0]}
  unnecessary_revalidation_rate: {count: 0, denominator: 1, rate: 0.0, wilson_95: [0.0, 0.7934506856227626]}
  missed_semantic_change_rate: {count: 0, denominator: 1, rate: 0.0, wilson_95: [0.0, 0.7934506856227626]}
  overall_accuracy: {count: 2, denominator: 2, rate: 1.0, wilson_95: [0.34238022750665303, 1.0]}
operational_outcomes: []
trials:
  - id: python-comment-only
    label: preserved
    lifecycle_status: active
    retrieval_status: active
  - id: python-literal-change
    label: changed
    lifecycle_status: stale
    retrieval_status: stale
""",
        encoding="utf-8",
    )
    assert_repository_baseline(result, baseline)


def test_checked_in_repository_corpus_has_a_reproducible_baseline(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    evaluator_root = root / "evaluator"

    result = evaluate_repository_corpus(
        evaluator_root / "corpus" / "repository-lifecycle-corpus.yaml",
        tmp_path / "repositories",
        root,
    )

    assert result.matrix == ConfusionMatrix(
        true_stale=9,
        false_stale=1,
        missed_change=1,
        true_active=7,
    )
    for language in ("python", "javascript", "typescript", "go", "java", "kotlin", "rust"):
        outcomes = {item.identifier: item for item in result.trials}
        assert outcomes[f"{language}-local-change"].retrieval_status == "stale"
        assert outcomes[f"{language}-trivia"].retrieval_status == "active"
    assert_repository_baseline(
        result,
        evaluator_root / "results" / "2026-08-12-repository-lifecycle-evaluation.yaml",
    )

from pathlib import Path

import pytest

from evaluator.repository_lifecycle import (
    ConfusionMatrix,
    RepositoryCorpusError,
    assert_repository_baseline,
    evaluate_repository_corpus,
    load_repository_corpus,
    ndcg_at_k,
    reciprocal_rank,
    repository_baseline_document,
)


def test_reciprocal_rank_and_ndcg_ranking_calculations() -> None:
    assert reciprocal_rank(1) == 1.0
    assert reciprocal_rank(2) == 0.5
    assert reciprocal_rank(5) == 0.2
    assert reciprocal_rank(None) == 0.0
    assert reciprocal_rank(0) == 0.0

    assert ndcg_at_k(1, 5) == 1.0
    assert ndcg_at_k(2, 5) == pytest.approx(1.0 / 1.5849625, abs=0.0001)
    assert ndcg_at_k(5, 5) == pytest.approx(1.0 / 2.5849625, abs=0.0001)
    assert ndcg_at_k(6, 5) == 0.0
    assert ndcg_at_k(None, 5) == 0.0


def test_repository_trials_observe_real_lifecycle_availability(tmp_path: Path) -> None:
    repository_root = Path(__file__).parents[2]
    corpus = tmp_path / "repository-corpus.yaml"
    corpus.write_text(
        """version: 1
retrieval_distractors:
  files:
    retrieval_context.py: |-
      def reporting_currency():
          return "USD"
  captures:
    - kind: behavior
      claim: The reporting currency is USD.
      durability_reason: Reports depend on the configured currency.
      retrieval_terms: [arithmetic contract]
      evidence:
        - type: symbol
          role: primary
          locator: retrieval_context.py:reporting_currency
trials:
  - id: python-literal-change
    family: direct-local
    semantic_case: return-value-change
    label_rationale: The captured function returns two and the changed function returns three.
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
    semantic_case: leading-comment
    label_rationale: Adding a comment does not change the function return value.
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
      retrieval_terms: [arithmetic contract]
      evidence:
        - type: symbol
          role: primary
          locator: service.py:compute
    change_files:
      service.py: |-
        # implementation comment
        def compute():
            return 2
    retrieval_case: declared-term
    expected_retrieval: true
    retrieval_prompt: arithmetic contract compute
""",
        encoding="utf-8",
    )

    result = evaluate_repository_corpus(
        corpus,
        tmp_path / "repositories",
        repository_root,
    )

    assert result.operational_outcomes == ()
    assert result.attempted_count == 2
    assert result.sample_count == 2
    assert result.matrix == ConfusionMatrix(
        true_stale=1,
        false_stale=0,
        missed_change=0,
        true_active=1,
    )
    assert [
        (
            trial.identifier,
            trial.lifecycle_status,
            trial.retrieval_case,
            trial.expected_retrieval,
            trial.target_retrieved,
            trial.context_returned,
            trial.returned_claim_count,
            trial.term_baseline_target_retrieved,
            trial.term_baseline_context_returned,
            trial.term_baseline_returned_claim_count,
        )
        for trial in result.trials
    ] == [
        (
            "python-comment-only",
            "active",
            "declared-term",
            True,
            True,
            True,
            2,
            True,
            True,
            2,
        ),
        (
            "python-literal-change",
            "stale",
            "standard",
            False,
            False,
            True,
            1,
            None,
            None,
            None,
        ),
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
    assert result.retrieval_metrics.recall.rate == 1.0
    assert result.retrieval_metrics.exclusion_rate.rate == 1.0
    assert result.retrieval_metrics.overall_accuracy.rate == 1.0
    assert result.retrieval_metrics.without_terms_overall_accuracy.rate == 1.0
    assert result.retrieval_metrics.precision.rate == 0.5
    assert result.retrieval_metrics.mrr == 1.0
    assert result.retrieval_metrics.ndcg_5 == 1.0
    assert result.retrieval_metrics.term_baseline_recall.rate == 1.0
    assert result.retrieval_metrics.term_assisted_recall.rate == 1.0
    assert result.retrieval_metrics.term_baseline_precision.rate == 0.5
    assert result.retrieval_metrics.term_assisted_precision.rate == 0.5
    assert result.retrieval_metrics.term_baseline_mrr == 0.5
    assert result.retrieval_metrics.term_assisted_mrr == 1.0
    assert result.retrieval_metrics.term_baseline_ndcg_5 == pytest.approx(0.6309297, abs=0.0001)
    assert result.retrieval_metrics.term_assisted_ndcg_5 == 1.0
    assert result.retrieval_metrics.term_net_gain == 0
    assert result.retrieval_partitions == ()
    document = repository_baseline_document(result)
    assert document["version"] == 3
    assert document["retrieval_partitions"] == []
    retrieval_metrics = document["retrieval_metrics"]
    assert isinstance(retrieval_metrics, dict)
    precision = retrieval_metrics["precision"]
    assert isinstance(precision, dict)
    assert precision["rate"] == 0.5
    trials = document["trials"]
    assert isinstance(trials, list)
    first_trial = trials[0]
    assert isinstance(first_trial, dict)
    assert first_trial["returned_claim_count"] == 2
    assert [
        (family.family, family.sample_count, family.matrix, family.accuracy.rate)
        for family in result.families
    ] == [
        ("direct-local", 1, ConfusionMatrix(1, 0, 0, 0), 1.0),
        ("preserving", 1, ConfusionMatrix(0, 0, 0, 1), 1.0),
    ]
    assert result.macro_family_accuracy == 1.0

    baseline = tmp_path / "repository-baseline.yaml"
    baseline.write_text(
        """version: 2
corpus_version: 1
attempted_count: 2
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
families:
  - family: direct-local
    sample_count: 1
    matrix: {true_stale: 1, false_stale: 0, missed_change: 0, true_active: 0}
    accuracy: {count: 1, denominator: 1, rate: 1.0, wilson_95: [0.20654931437723745, 1.0]}
  - family: preserving
    sample_count: 1
    matrix: {true_stale: 0, false_stale: 0, missed_change: 0, true_active: 1}
    accuracy: {count: 1, denominator: 1, rate: 1.0, wilson_95: [0.20654931437723745, 1.0]}
macro_family_accuracy: 1.0
operational_outcomes: []
trials:
  - id: python-comment-only
    family: preserving
    label: preserved
    lifecycle_status: active
    retrieval_status: active
  - id: python-literal-change
    family: direct-local
    label: changed
    lifecycle_status: stale
    retrieval_status: stale
""",
        encoding="utf-8",
    )
    assert_repository_baseline(result, baseline)


@pytest.mark.parametrize("missing_field", ["semantic_case", "label_rationale"])
def test_repository_labels_require_an_auditable_semantic_basis(
    tmp_path: Path, missing_field: str
) -> None:
    fields = {
        "semantic_case": "return-value-change",
        "label_rationale": "The changed function returns two instead of one.",
    }
    del fields[missing_field]
    corpus = tmp_path / "repository-corpus.yaml"
    corpus.write_text(
        """version: 1
trials:
  - id: auditable-label
    family: direct-local
    label: changed
    initial_files: {service.py: "def compute():\\n    return 0\\n"}
    capture_files: {service.py: "def compute():\\n    return 1\\n"}
    capture: {kind: behavior, claim: Compute returns one., durability_reason: Callers rely on it., evidence: [{type: symbol, role: primary, locator: service.py:compute}]}
    change_files: {service.py: "def compute():\\n    return 2\\n"}
    retrieval_prompt: service.py:compute
"""
        + "".join(f"    {name}: {value}\n" for name, value in fields.items()),
        encoding="utf-8",
    )

    with pytest.raises(RepositoryCorpusError, match=missing_field):
        load_repository_corpus(corpus)


def test_repository_families_cannot_repeat_one_semantic_case_as_independent_breadth(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "repository-corpus.yaml"
    trial = """    family: direct-local
    semantic_case: translated-literal
    label_rationale: The returned literal changes from one to two.
    label: changed
    initial_files: {service.py: "def compute():\\n    return 0\\n"}
    capture_files: {service.py: "def compute():\\n    return 1\\n"}
    capture: {kind: behavior, claim: Compute returns one., durability_reason: Callers rely on it., evidence: [{type: symbol, role: primary, locator: service.py:compute}]}
    change_files: {service.py: "def compute():\\n    return 2\\n"}
    retrieval_prompt: service.py:compute
"""
    corpus.write_text(
        "version: 2\ntrials:\n  - id: first\n" + trial + "  - id: second\n" + trial,
        encoding="utf-8",
    )

    with pytest.raises(RepositoryCorpusError, match="distinct semantic cases"):
        load_repository_corpus(corpus)


def test_checked_in_repository_corpus_balances_retrieval_scenarios() -> None:
    root = Path(__file__).parents[2]
    corpus = root / "evaluator" / "corpus" / "repository-lifecycle-corpus.yaml"

    version, trials = load_repository_corpus(corpus)

    declared_terms = tuple(trial for trial in trials if trial.retrieval_case == "declared-term")
    unrelated = tuple(trial for trial in trials if trial.retrieval_case == "unrelated")
    assert version == 3
    assert len(trials) == 100
    assert len(declared_terms) == 20
    assert sum(trial.expected_retrieval for trial in declared_terms) == 10
    assert sum(not trial.expected_retrieval for trial in declared_terms) == 10
    assert all("retrieval_terms" in trial.capture for trial in declared_terms)
    assert {
        trial.retrieval_partition
        for trial in declared_terms
        if trial.retrieval_partition is not None
    } == {"calibration", "holdout"}
    assert sum(trial.retrieval_partition == "calibration" for trial in declared_terms) == 10
    assert sum(trial.retrieval_partition == "holdout" for trial in declared_terms) == 10
    assert (
        sum(
            trial.retrieval_partition == "calibration" and trial.expected_retrieval
            for trial in declared_terms
        )
        == 5
    )
    assert (
        sum(
            trial.retrieval_partition == "holdout" and trial.expected_retrieval
            for trial in declared_terms
        )
        == 5
    )
    assert all(len(trial.distractor_captures) == 4 for trial in declared_terms)
    assert all(set(trial.distractor_files) == {"retrieval_context.py"} for trial in declared_terms)
    assert {trial.identifier for trial in declared_terms if trial.expected_retrieval} == {
        "python-conservative-defined-logging",
        "python-conservative-defined-metric",
        "python-conservative-defined-tracing",
        "graph-one-hop-comment",
        "graph-two-hop-comment",
        "graph-three-hop-formatting",
        "graph-cycle-comment",
        "shape-unrelated-source-edit",
        "shape-test-only-edit",
        "shape-documentation-edit",
    }
    assert {trial.identifier for trial in declared_terms if not trial.expected_retrieval} == {
        "incomplete-policy-function",
        "incomplete-yaml-config",
        "incomplete-json-config",
        "incomplete-toml-config",
        "incomplete-pricing-module",
        "incomplete-permission-module",
        "incomplete-schema-required",
        "graph-one-hop-change",
        "graph-two-hop-change",
        "graph-config-change",
    }
    assert len(unrelated) == 10
    assert all(trial.label == "preserved" for trial in unrelated)
    assert all(not trial.expected_retrieval for trial in unrelated)


@pytest.mark.repository_evaluation
def test_checked_in_repository_corpus_has_a_reproducible_baseline(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    evaluator_root = root / "evaluator"
    corpus_path = evaluator_root / "corpus" / "repository-lifecycle-corpus.yaml"

    _version, trials = load_repository_corpus(corpus_path)
    assert len(trials) == 100
    assert sum(trial.label == "changed" for trial in trials) == 50
    assert sum(trial.label == "preserved" for trial in trials) == 50
    assert {
        family: sum(trial.family == family for trial in trials)
        for family in sorted({trial.family for trial in trials})
    } == {
        "conservative-false-stale": 12,
        "direct-local": 28,
        "evidence-graph": 10,
        "incomplete-provenance": 12,
        "preserving": 28,
        "repository-shape": 10,
    }
    assert {
        Path(path).suffix
        for trial in trials
        for path in trial.capture_files
        if Path(path).suffix in {".go", ".java", ".js", ".kt", ".py", ".rs", ".ts"}
    } == {".go", ".java", ".js", ".kt", ".py", ".rs", ".ts"}

    result = evaluate_repository_corpus(
        corpus_path,
        tmp_path / "repositories",
        root,
    )

    assert result.attempted_count == 100
    assert result.sample_count == 100
    assert result.matrix == ConfusionMatrix(
        true_stale=44,
        false_stale=8,
        missed_change=6,
        true_active=42,
    )
    assert [
        (family.family, family.sample_count, family.matrix, family.accuracy.rate)
        for family in result.families
    ] == [
        ("conservative-false-stale", 12, ConfusionMatrix(0, 8, 0, 4), 1 / 3),
        ("direct-local", 28, ConfusionMatrix(28, 0, 0, 0), 1.0),
        ("evidence-graph", 10, ConfusionMatrix(6, 0, 0, 4), 1.0),
        ("incomplete-provenance", 12, ConfusionMatrix(6, 0, 6, 0), 0.5),
        ("preserving", 28, ConfusionMatrix(0, 0, 0, 28), 1.0),
        ("repository-shape", 10, ConfusionMatrix(4, 0, 0, 6), 1.0),
    ]
    assert result.macro_family_accuracy == pytest.approx(29 / 36)
    assert result.retrieval_metrics.recall.count == 32
    assert result.retrieval_metrics.recall.denominator == 40
    assert result.retrieval_metrics.recall.rate == 0.8
    assert result.retrieval_metrics.exclusion_rate.count == 50
    assert result.retrieval_metrics.exclusion_rate.denominator == 60
    assert result.retrieval_metrics.exclusion_rate.rate == 50 / 60
    assert result.retrieval_metrics.precision.count == 7
    assert result.retrieval_metrics.precision.denominator == 27
    assert result.retrieval_metrics.precision.rate == 7 / 27
    assert result.retrieval_metrics.mrr == pytest.approx(0.45)
    assert result.retrieval_metrics.ndcg_5 == pytest.approx(0.5398719, abs=0.0001)
    assert result.retrieval_metrics.overall_accuracy.count == 82
    assert result.retrieval_metrics.overall_accuracy.denominator == 100
    assert result.retrieval_metrics.overall_accuracy.rate == 0.82
    assert result.retrieval_metrics.without_terms_overall_accuracy.count == 82
    assert result.retrieval_metrics.without_terms_overall_accuracy.denominator == 100
    assert result.retrieval_metrics.without_terms_overall_accuracy.rate == 0.82
    assert result.retrieval_metrics.without_terms_mrr == pytest.approx(0.4125)
    assert result.retrieval_metrics.without_terms_ndcg_5 == pytest.approx(0.5121916, abs=0.0001)
    assert result.retrieval_metrics.term_baseline_recall.count == 7
    assert result.retrieval_metrics.term_baseline_recall.denominator == 10
    assert result.retrieval_metrics.term_assisted_recall.count == 7
    assert result.retrieval_metrics.term_assisted_recall.denominator == 10
    assert result.retrieval_metrics.term_baseline_exclusion_rate.count == 3
    assert result.retrieval_metrics.term_baseline_exclusion_rate.denominator == 10
    assert result.retrieval_metrics.term_assisted_exclusion_rate.count == 3
    assert result.retrieval_metrics.term_assisted_exclusion_rate.denominator == 10
    assert result.retrieval_metrics.term_baseline_precision.count == 7
    assert result.retrieval_metrics.term_baseline_precision.denominator == 28
    assert result.retrieval_metrics.term_assisted_precision.count == 7
    assert result.retrieval_metrics.term_assisted_precision.denominator == 27
    assert result.retrieval_metrics.term_baseline_mrr == 0.55
    assert result.retrieval_metrics.term_assisted_mrr == 0.70
    assert result.retrieval_metrics.term_baseline_ndcg_5 == pytest.approx(0.5892789, abs=0.0001)
    assert result.retrieval_metrics.term_assisted_ndcg_5 == 0.70
    assert result.retrieval_metrics.term_net_gain == 0
    assert [
        (
            partition.partition,
            partition.sample_count,
            partition.metrics.overall_accuracy.rate,
            partition.metrics.without_terms_overall_accuracy.rate,
            partition.metrics.recall.rate,
            partition.metrics.exclusion_rate.rate,
            partition.metrics.precision.rate,
            partition.metrics.mrr,
            partition.metrics.ndcg_5,
        )
        for partition in result.retrieval_partitions
    ] == [
        ("calibration", 10, 0.2, 0.2, 0.4, 0.0, 2 / 14, 0.4, 0.4),
        ("holdout", 10, 0.8, 0.8, 1.0, 0.6, 5 / 13, 1.0, 1.0),
    ]
    assert_repository_baseline(
        result,
        evaluator_root / "results" / "2026-08-18-post-ranking-metrics.yaml",
    )

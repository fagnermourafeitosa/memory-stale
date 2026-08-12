from pathlib import Path

import pytest

from evaluator.repository_lifecycle import (
    ConfusionMatrix,
    RepositoryCorpusError,
    assert_repository_baseline,
    evaluate_repository_corpus,
    load_repository_corpus,
)


def test_repository_trials_observe_real_lifecycle_availability(tmp_path: Path) -> None:
    repository_root = Path(__file__).parents[2]
    corpus = tmp_path / "repository-corpus.yaml"
    corpus.write_text(
        """version: 1
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
    assert result.attempted_count == 2
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
        true_stale=38,
        false_stale=26,
        missed_change=12,
        true_active=24,
    )
    assert [
        (family.family, family.sample_count, family.matrix, family.accuracy.rate)
        for family in result.families
    ] == [
        ("conservative-false-stale", 12, ConfusionMatrix(0, 12, 0, 0), 0.0),
        ("direct-local", 28, ConfusionMatrix(28, 0, 0, 0), 1.0),
        ("evidence-graph", 10, ConfusionMatrix(6, 0, 0, 4), 1.0),
        ("incomplete-provenance", 12, ConfusionMatrix(0, 0, 12, 0), 0.0),
        ("preserving", 28, ConfusionMatrix(0, 14, 0, 14), 0.5),
        ("repository-shape", 10, ConfusionMatrix(4, 0, 0, 6), 1.0),
    ]
    assert result.macro_family_accuracy == pytest.approx(7 / 12)
    assert_repository_baseline(
        result,
        evaluator_root / "results" / "2026-08-12-repository-lifecycle-evaluation.yaml",
    )

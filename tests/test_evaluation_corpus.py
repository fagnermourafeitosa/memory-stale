from pathlib import Path

import pytest

from memory_stale.evaluation import CorpusError, evaluate_corpus, load_corpus


def test_evaluator_reports_labeled_false_stale_and_missed_changes(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.yaml"
    corpus.write_text(
        """version: 1
scenarios:
  - id: instrumentation
    label: preserved
    evidence: service.py:compute
    before:
      service.py: |-
        def compute():
            return 1
    after:
      service.py: |-
        def compute():
            trace_metric()
            return 1
  - id: indirect-policy
    label: changed
    evidence: auth.py:login
    depends_on: [policy.py:mfa_policy]
    before:
      auth.py: |-
        def login():
            return allow_login()
      policy.py: |-
        def mfa_policy():
            return True
    after:
      auth.py: |-
        def login():
            return allow_login()
      policy.py: |-
        def mfa_policy():
            return False
""",
        encoding="utf-8",
    )

    result = evaluate_corpus(corpus, tmp_path / "fixtures")

    assert result.unnecessary_revalidation_rate == 1.0
    assert result.missed_semantic_change_rate == 1.0
    assert [(item.identifier, item.lifecycle_status) for item in result.scenarios] == [
        ("indirect-policy", "active"),
        ("instrumentation", "stale"),
    ]
    assert [(item.identifier, item.lifecycle_status) for item in result.graph_scenarios] == [
        ("indirect-policy", "stale"),
        ("instrumentation", "stale"),
    ]
    assert result.graph_missed_semantic_change_rate == 0.0


def test_corpus_schema_errors_name_the_invalid_scenario(tmp_path: Path) -> None:
    corpus = tmp_path / "invalid.yaml"
    corpus.write_text(
        "version: 1\nscenarios:\n  - id: missing-label\n    evidence: service.py:compute\n",
        encoding="utf-8",
    )

    with pytest.raises(CorpusError, match=r"missing-label.*label"):
        load_corpus(corpus)


def test_versioned_baseline_corpus_covers_each_supported_grammar(tmp_path: Path) -> None:
    corpus = Path(__file__).parents[1] / "evaluation-corpus.yaml"

    result = evaluate_corpus(corpus, tmp_path / "fixtures")

    identifiers = {item.identifier for item in result.scenarios}
    for language in ("python", "javascript", "typescript", "go", "java", "kotlin", "rust"):
        assert f"{language}-trivia" in identifiers
        assert f"{language}-local-change" in identifiers
    assert result.unnecessary_revalidation_rate == pytest.approx(1 / 8)
    assert result.missed_semantic_change_rate == pytest.approx(1 / 8)
    assert result.graph_unnecessary_revalidation_rate == pytest.approx(1 / 8)
    assert result.graph_missed_semantic_change_rate == 0.0

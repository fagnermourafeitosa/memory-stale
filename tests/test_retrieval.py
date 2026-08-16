import pytest

from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.retrieval import retrieve


def _memory(
    identifier: str,
    claim: str,
    ref: str,
    *,
    status: str = "active",
    durability_reason: str = "Future work relies on this.",
) -> Memory:
    return Memory(
        identifier,
        "behavior",
        status,
        claim,
        durability_reason,
        (EvidenceItem("symbol", "primary", ref, "sig"),),
    )


def test_retrieval_filters_stale_prioritizes_refs_and_respects_budget() -> None:
    memories = [
        _memory("text", "Authentication validates passwords.", "other.py:check"),
        _memory("exact", "Sessions require MFA.", "auth.py:login"),
        _memory("stale", "Never return this stale fact.", "auth.py:login", status="stale"),
    ]

    context = retrieve(memories, "Change auth.py:login authentication", budget=18)

    assert "Sessions require MFA." in context
    assert "Authentication validates passwords." not in context
    assert "Never return this stale fact." not in context


def test_retrieval_returns_empty_context_for_empty_or_unrelated_corpus() -> None:
    assert retrieve([], "anything", budget=1500) == ""
    assert (
        retrieve([_memory("one", "Database replicas lag.", "db.py:replica")], "style CSS", 1500)
        == ""
    )


def test_retrieval_finds_active_memory_through_locator_vocabulary() -> None:
    memory = _memory(
        "session-renewal",
        "Credentials renew after successful authorization.",
        "src/security/session.py:rotate_token",
    )

    context = retrieve([memory], "Adjust session token handling", budget=1500)

    assert "Credentials renew after successful authorization." in context


def test_retrieval_weights_claim_above_durability_reason() -> None:
    memories = [
        _memory(
            "a-reason",
            "Archives remain available.",
            "archive.py:store",
            durability_reason="Retention policy matters.",
        ),
        _memory(
            "z-claim",
            "Retention policy applies.",
            "records.py:keep",
            durability_reason="Operators need guidance.",
        ),
    ]

    context = retrieve(memories, "retention", budget=1500)

    assert context.index("Retention policy applies.") < context.index("Archives remain available.")


def test_retrieval_does_not_treat_missing_symbol_suffix_as_an_exact_path_match() -> None:
    memory = Memory(
        "database-source",
        "behavior",
        "active",
        "Database replicas lag.",
        "Operators account for delayed reads.",
        (EvidenceItem("source", "primary", "src/storage/database.py", "sig"),),
    )

    context = retrieve([memory], "Adjust CSS typography", budget=1500)

    assert context == ""


def test_retrieval_prioritizes_an_exact_symbol_without_its_path() -> None:
    memory = _memory(
        "session-renewal",
        "Credentials renew after successful authorization.",
        "src/security/session.py:rotate_token",
    )

    context = retrieve([memory], "Change rotate_token", budget=1500)

    assert "Credentials renew after successful authorization." in context


def test_retrieval_prioritizes_an_exact_document_path_without_its_pointer() -> None:
    memory = Memory(
        "auth-timeout",
        "constraint",
        "active",
        "Authentication requests expire promptly.",
        "Operators rely on bounded request lifetimes.",
        (EvidenceItem("config", "primary", "config/app.toml#auth.timeout", "sig"),),
    )

    context = retrieve([memory], "Change config/app.toml", budget=1500)

    assert "Authentication requests expire promptly." in context


def test_retrieval_weights_locator_above_claim() -> None:
    memories = [
        _memory(
            "a-claim",
            "Session behavior stays available.",
            "archive.py:store",
        ),
        _memory(
            "z-locator",
            "Credentials remain available.",
            "src/security/session.py:rotate",
        ),
    ]

    context = retrieve(memories, "session", budget=1500)

    assert context.index("Credentials remain available.") < context.index(
        "Session behavior stays available."
    )


@pytest.mark.parametrize(
    ("locator", "prompt"),
    [
        ("src/security/session.py:rotate_token", "Change security controls"),
        ("src/security/session.py:rotate_token", "Change session handling"),
        ("src/security/session.py:rotate_token", "Review py modules"),
        ("src/jobs/task-runner.py:retry-policy", "Change task runner retries"),
        ("src/security/session.py:rotateToken", "Change rotate token behavior"),
    ],
)
def test_retrieval_searches_structural_locator_components(locator: str, prompt: str) -> None:
    memory = _memory(
        "structural-locator",
        "Credentials renew after successful authorization.",
        locator,
    )

    context = retrieve([memory], prompt, budget=1500)

    assert "Credentials renew after successful authorization." in context


def test_retrieval_ranking_is_independent_of_evidence_order() -> None:
    evidence = (
        EvidenceItem("symbol", "primary", "src/security/session.py:rotate_token", "sig-1"),
        EvidenceItem("test", "supporting", "tests/audit/test_log.py:records", "sig-2"),
    )
    competitor = _memory(
        "a-claim",
        "Session behavior remains available.",
        "archive.py:store",
    )

    contexts = [
        retrieve(
            [
                Memory(
                    "z-locator",
                    "behavior",
                    "active",
                    "Credentials update after authorization.",
                    "Existing clients require uninterrupted access.",
                    ordered_evidence,
                ),
                competitor,
            ],
            "session",
            budget=1500,
        )
        for ordered_evidence in (evidence, tuple(reversed(evidence)))
    ]

    for context in contexts:
        assert context.index("Credentials update after authorization.") < context.index(
            "Session behavior remains available."
        )

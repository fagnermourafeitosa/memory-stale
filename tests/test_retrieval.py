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


def test_retrieval_returns_only_the_configured_top_ranked_candidates() -> None:
    memories = [
        _memory("a-first", "First session behavior.", "auth.py:login"),
        _memory("b-second", "Second session behavior.", "auth.py:login"),
        _memory("c-third", "Third session behavior.", "auth.py:login"),
    ]

    context = retrieve(memories, "Change auth.py:login", budget=1500, top_k=2)

    assert "First session behavior." in context
    assert "Second session behavior." in context
    assert "Third session behavior." not in context


def test_retrieval_returns_empty_context_for_empty_or_unrelated_corpus() -> None:
    assert retrieve([], "anything", budget=1500) == ""
    assert (
        retrieve([_memory("one", "Database replicas lag.", "db.py:replica")], "style CSS", 1500)
        == ""
    )


def test_retrieval_excludes_memory_anchored_inside_the_agents_directory() -> None:
    memories = [
        _memory(
            "installed-runtime",
            "Installed runtime handles retries.",
            ".agents/skills/memory-stale/runtime.py:run",
        ),
        _memory(
            "project-auth",
            "Authentication requires review.",
            "auth.py:login",
        ),
    ]

    context = retrieve(memories, "Review runtime and auth.py:login", budget=1500)

    assert "Authentication requires review." in context
    assert "Installed runtime handles retries." not in context


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


def test_retrieval_rejects_declared_terms_without_claim_or_locator_corroboration() -> None:
    memory = Memory(
        "term-only",
        "behavior",
        "active",
        "Login verifies a second factor before granting access.",
        "Authentication changes must preserve the extra verification step.",
        (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
        retrieval_terms=("MFA",),
    )

    assert retrieve([memory], "MFA", budget=1500) == ""
    assert "Login verifies a second factor before granting access." in retrieve(
        [memory], "MFA login", budget=1500
    )


def test_retrieval_excludes_weak_lexical_tail_below_the_relative_threshold() -> None:
    target = Memory(
        "target",
        "behavior",
        "active",
        "Session login requires authorization.",
        "Clients rely on the authentication policy.",
        (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
        retrieval_terms=("MFA session authorization",),
    )
    weak = _memory(
        "weak",
        "Telemetry emits audit events.",
        "telemetry.py:emit",
    )

    context = retrieve([target, weak], "MFA session authorization login telemetry", budget=1500)

    assert "Session login requires authorization." in context
    assert "Telemetry emits audit events." not in context


def test_retrieval_keeps_exact_locators_and_excludes_weaker_declared_terms() -> None:
    memories = [
        Memory(
            "a-terms",
            "behavior",
            "active",
            "Credentials remain available.",
            "Operators preserve access.",
            (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
            retrieval_terms=("rotate_token",),
        ),
        _memory(
            "z-exact",
            "Session rotation invalidates old credentials.",
            "src/security/session.py:rotate_token",
        ),
    ]

    context = retrieve(memories, "rotate_token", budget=1500)

    assert "Session rotation invalidates old credentials." in context
    assert "Credentials remain available." not in context


def test_retrieval_excludes_stale_memory_even_when_a_declared_term_matches() -> None:
    memory = Memory(
        "stale-term",
        "behavior",
        "stale",
        "Credentials remain available.",
        "Operators preserve access.",
        (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
        retrieval_terms=("velociraptor",),
    )

    assert retrieve([memory], "velociraptor", budget=1500) == ""


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

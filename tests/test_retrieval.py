from memory_stale.lifecycle import Memory
from memory_stale.retrieval import retrieve


def _memory(identifier: str, claim: str, ref: str, *, status: str = "active") -> Memory:
    return Memory(
        identifier, "behavior", status, claim, "Future work relies on this.", {ref: "sig"}
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

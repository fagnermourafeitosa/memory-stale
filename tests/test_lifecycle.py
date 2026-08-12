from pathlib import Path

from memory_stale.lifecycle import Memory, RefEvidence, reconcile
from memory_stale.memory_store import MemoryStore


def test_lifecycle_creates_memory_and_marks_changed_evidence_stale(tmp_path: Path) -> None:
    capture = {
        "kind": "behavior",
        "claim": "Login validates MFA.",
        "refs": ["auth.py:login"],
        "durability_reason": "Authentication must preserve MFA.",
        "signatures": {"auth.py:login": "old-signature"},
    }
    created = reconcile([], [capture], {"auth.py:login": RefEvidence("old-signature")})
    assert len(created) == 1
    assert created[0].status == "active"

    stale = reconcile(created, [], {"auth.py:login": RefEvidence("new-signature")})
    assert stale[0].status == "stale"
    assert stale[0].stale_reasons == {"auth.py:login": "changed"}

    store = MemoryStore(tmp_path)
    store.write_all(stale)
    loaded = store.load_all()
    assert loaded == stale
    assert list(store.directory.glob("*.md"))


def test_lifecycle_records_missing_and_unresolvable_reasons() -> None:
    memory = Memory(
        id="memory-1",
        kind="contract",
        status="active",
        claim="Public behavior is stable.",
        durability_reason="Callers rely on it.",
        signatures={"gone.py:gone": "a", "broken.py:broken": "b"},
    )
    result = reconcile(
        [memory],
        [],
        {
            "gone.py:gone": RefEvidence(None, "file_missing"),
            "broken.py:broken": RefEvidence(None, "unresolvable"),
        },
    )
    assert result[0].stale_reasons == {
        "broken.py:broken": "unresolvable",
        "gone.py:gone": "file_missing",
    }


def test_lifecycle_is_idempotent_and_preserves_stale_history(tmp_path: Path) -> None:
    capture = {
        "kind": "constraint",
        "claim": "Writes are atomic.",
        "refs": ["store.py:write"],
        "durability_reason": "Partial files are unsafe.",
        "signatures": {"store.py:write": "signature"},
    }
    first = reconcile([], [capture, capture], {})
    assert len(first) == 1
    stale = [
        Memory(
            id=first[0].id,
            kind=first[0].kind,
            status="stale",
            claim=first[0].claim,
            durability_reason=first[0].durability_reason,
            signatures=first[0].signatures,
            stale_reasons={"store.py:write": "changed"},
        )
    ]
    assert reconcile(stale, [], {}) == stale
    assert MemoryStore(tmp_path).load_all() == []

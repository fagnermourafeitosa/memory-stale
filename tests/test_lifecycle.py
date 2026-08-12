from pathlib import Path

from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory, RefEvidence, reconcile
from memory_stale.memory_store import MemoryStore


def test_lifecycle_creates_memory_and_marks_changed_evidence_stale(tmp_path: Path) -> None:
    capture = {
        "kind": "behavior",
        "claim": "Login validates MFA.",
        "durability_reason": "Authentication must preserve MFA.",
        "evidence": [
            {
                "type": "symbol",
                "role": "primary",
                "locator": "auth.py:login",
                "fingerprint": "old-signature",
            }
        ],
    }
    created = reconcile([], [capture], {"symbol:auth.py:login": RefEvidence("old-signature")})
    assert len(created) == 1
    assert created[0].status == "active"

    stale = reconcile(created, [], {"symbol:auth.py:login": RefEvidence("new-signature")})
    assert stale[0].status == "stale"
    assert stale[0].stale_reasons == {"symbol:auth.py:login": "changed"}

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
        evidence=(
            EvidenceItem("symbol", "primary", "gone.py:gone", "a"),
            EvidenceItem("symbol", "supporting", "broken.py:broken", "b"),
        ),
    )
    result = reconcile(
        [memory],
        [],
        {
            "symbol:gone.py:gone": RefEvidence(None, "file_missing"),
            "symbol:broken.py:broken": RefEvidence(None, "unresolvable"),
        },
    )
    assert result[0].stale_reasons == {
        "symbol:broken.py:broken": "unresolvable",
        "symbol:gone.py:gone": "file_missing",
    }


def test_lifecycle_is_idempotent_and_preserves_stale_history(tmp_path: Path) -> None:
    capture = {
        "kind": "constraint",
        "claim": "Writes are atomic.",
        "durability_reason": "Partial files are unsafe.",
        "evidence": [
            {
                "type": "symbol",
                "role": "primary",
                "locator": "store.py:write",
                "fingerprint": "signature",
            }
        ],
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
            evidence=first[0].evidence,
            stale_reasons={"symbol:store.py:write": "changed"},
        )
    ]
    assert reconcile(stale, [], {}) == stale
    assert MemoryStore(tmp_path).load_all() == []


def test_legacy_markdown_migrates_to_one_versioned_revision_without_losing_history(
    tmp_path: Path,
) -> None:
    store = MemoryStore(tmp_path)
    store.directory.mkdir(parents=True)
    legacy = store.directory / "legacy-id.md"
    legacy.write_text(
        "---\n"
        "id: legacy-id\n"
        "kind: behavior\n"
        "status: stale\n"
        "durability_reason: Preserve the guard.\n"
        "signatures:\n"
        "  auth.py:login: old-signature\n"
        "stale_reasons:\n"
        "  auth.py:login: changed\n"
        "---\n\n"
        "Login requires MFA.\n",
        encoding="utf-8",
    )

    migrated = store.load_all()

    assert len(migrated) == 1
    revision = migrated[0]
    assert revision.schema_version == 3
    assert revision.legacy_id == "legacy-id"
    assert revision.id != "legacy-id"
    assert revision.claim_id is not None
    assert revision.status == "stale"
    assert revision.stale_reasons == {"symbol:auth.py:login": "changed"}

    store.write_all(migrated)

    paths = list(store.directory.glob("*.md"))
    assert [path.name for path in paths] == [f"{revision.id}.md"]
    assert "schema_version: 3" in paths[0].read_text(encoding="utf-8")
    assert store.load_all() == migrated

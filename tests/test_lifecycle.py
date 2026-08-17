from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
import yaml

from memory_stale.evidence import EvidenceEdge, EvidenceItem
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

    captured_at = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    store = MemoryStore(tmp_path, clock=lambda: captured_at)
    store.write_all(stale)
    loaded = store.load_all()
    assert loaded == [
        replace(
            stale[0],
            observed_at="2026-08-16T12:00:00+00:00",
            generated_at="2026-08-16T12:00:00+00:00",
        )
    ]
    assert list(store.directory.glob("*.md"))
    _opening, front_matter, _body = (
        next(store.directory.glob("*.md")).read_text(encoding="utf-8").split("---", 2)
    )
    document = yaml.safe_load(front_matter)
    assert document["status"] == "deprecated"
    assert document["memory_stale"]["status"] == "stale"
    assert document["memory_stale"]["stale_reasons"] == {"symbol:auth.py:login": "changed"}


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


def test_lifecycle_preserves_retrieval_vocabulary_as_a_distinct_revision() -> None:
    capture = {
        "kind": "behavior",
        "claim": "Login verifies a second factor before granting access.",
        "durability_reason": "Authentication must preserve the extra verification step.",
        "evidence": [
            {
                "type": "symbol",
                "role": "primary",
                "locator": "auth.py:login",
                "fingerprint": "signature",
            }
        ],
        "retrieval_terms": ["MFA"],
    }

    first = reconcile([], [capture], {})
    revised = reconcile(
        first,
        [{**capture, "retrieval_terms": ["two-factor login"]}],
        {"symbol:auth.py:login": RefEvidence("signature")},
    )

    assert len(revised) == 2
    assert {memory.status for memory in revised} == {"active", "superseded"}
    assert len({memory.claim_id for memory in revised}) == 1
    assert {memory.retrieval_terms for memory in revised} == {("MFA",), ("two-factor login",)}


def test_legacy_markdown_migrates_to_one_versioned_revision_without_losing_history(
    tmp_path: Path,
) -> None:
    store = MemoryStore(
        tmp_path,
        clock=lambda: datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
    )
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
    assert revision.schema_version == 5
    assert revision.legacy_id == "legacy-id"
    assert revision.id != "legacy-id"
    assert revision.claim_id is not None
    assert revision.status == "stale"
    assert revision.stale_reasons == {"symbol:auth.py:login": "changed"}

    store.write_all(migrated)

    paths = list(store.directory.glob("*.md"))
    assert [path.name for path in paths] == [f"{revision.id}.md"]
    migrated_text = paths[0].read_text(encoding="utf-8")
    assert "type: Memory Stale Claim" in migrated_text
    assert "schema_version: 5" in migrated_text
    reloaded = store.load_all()
    assert reloaded[0].id == revision.id
    assert reloaded[0].claim_id == revision.claim_id
    assert reloaded[0].evidence == revision.evidence
    assert reloaded[0].stale_reasons == revision.stale_reasons

    store.write_all(reloaded)

    assert paths[0].read_text(encoding="utf-8") == migrated_text


def test_store_preserves_unknown_okf_fields_without_affecting_memory_state(tmp_path: Path) -> None:
    store = MemoryStore(
        tmp_path,
        clock=lambda: datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
    )
    memory = Memory(
        id="retry-policy",
        kind="behavior",
        status="active",
        claim="Jobs retry transient failures.",
        durability_reason="Retries are a reliability contract.",
        evidence=(EvidenceItem("symbol", "primary", "jobs.py:retry", "retry-v1"),),
    )
    store.write_all([memory])
    path = next(store.directory.glob("*.md"))
    _opening, front_matter, body = path.read_text(encoding="utf-8").split("---", 2)
    document = yaml.safe_load(front_matter)
    document["tags"] = ["jobs", "retry"]
    path.write_text(
        f"---\n{yaml.safe_dump(document, sort_keys=False)}---{body}",
        encoding="utf-8",
    )

    loaded = store.load_all()
    store.write_all(loaded)

    _opening, front_matter, _body = path.read_text(encoding="utf-8").split("---", 2)
    persisted = yaml.safe_load(front_matter)
    assert persisted["tags"] == ["jobs", "retry"]
    assert loaded[0].status == "active"
    assert loaded[0].evidence == memory.evidence


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing_source", "mismatched evidence source"),
        ("duplicate_source", "duplicate source"),
        ("mismatched_resource", "mismatched evidence source"),
        ("unknown_graph_source", "supported_by references unknown evidence"),
        ("missing_primary", "missing primary evidence"),
    ],
)
def test_store_rejects_invalid_okf_evidence_mappings(
    tmp_path: Path, case: str, message: str
) -> None:
    store = MemoryStore(tmp_path / case)
    store.write_all(
        [
            Memory(
                id="retry-policy",
                kind="behavior",
                status="active",
                claim="Jobs retry transient failures.",
                durability_reason="Retries are a reliability contract.",
                evidence=(EvidenceItem("symbol", "primary", "jobs.py:retry", "retry-v1"),),
            )
        ]
    )
    path = next(store.directory.glob("*.md"))
    _opening, front_matter, body = path.read_text(encoding="utf-8").split("---", 2)
    document = cast(dict[str, object], yaml.safe_load(front_matter))
    sources = cast(list[dict[str, object]], document["sources"])
    extension = cast(dict[str, object], document["memory_stale"])
    evidence = cast(list[dict[str, object]], extension["evidence"])
    if case == "missing_source":
        document["sources"] = []
    elif case == "duplicate_source":
        sources.append(dict(sources[0]))
    elif case == "mismatched_resource":
        sources[0]["resource"] = "jobs.py:other"
    elif case == "unknown_graph_source":
        extension["supported_by"] = ["symbol:missing"]
    else:
        evidence[0]["role"] = "supporting"
    path.write_text(
        f"---\n{yaml.safe_dump(document, sort_keys=False)}---{body}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        store.load_all()


def test_dependency_cycle_has_a_finite_deterministic_invalidation_path() -> None:
    login = EvidenceItem("symbol", "primary", "auth.py:login", "login-before")
    policy = EvidenceItem("symbol", "supporting", "policy.py:authentication", "policy-before")
    memory = Memory(
        id="cycle",
        kind="behavior",
        status="active",
        claim="Login follows policy.",
        durability_reason="Policy is reusable evidence.",
        evidence=(login, policy),
        supported_by=(login.key,),
        dependencies=(EvidenceEdge(login.key, policy.key), EvidenceEdge(policy.key, login.key)),
    )

    reconciled = reconcile(
        [memory],
        [],
        {
            login.key: RefEvidence("login-before"),
            policy.key: RefEvidence("policy-after"),
        },
    )

    assert reconciled[0].status == "stale"
    assert reconciled[0].stale_reasons == {policy.key: f"changed via {login.key} -> {policy.key}"}

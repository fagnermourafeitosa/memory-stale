"""`dream` explains why evidence broke and isolates failures per memory."""

import os
from pathlib import Path

import pytest

from memory_stale.dream import dream
from memory_stale.evidence import EvidenceItem, resolve_item
from memory_stale.lifecycle import Memory
from memory_stale.memory_store import MemoryStore


def _memory(repository: Path, memory_id: str, item_type: str, locator: str) -> Memory:
    item = resolve_item(repository, item_type, "primary", locator)
    return Memory(
        memory_id,
        "behavior",
        "active",
        f"Claim backed by {locator}.",
        "Durable.",
        (EvidenceItem(item.type, item.role, item.locator, item.fingerprint),),
    )


def _seed(repository: Path) -> None:
    (repository / "jobs.py").write_text(
        "def retry():\n    return 3\n\n\ndef backoff():\n    return 2\n", encoding="utf-8"
    )
    (repository / "settings.json").write_text('{"retries": 3}\n', encoding="utf-8")
    (repository / "flags.json").write_text('{"beta": true}\n', encoding="utf-8")
    MemoryStore(repository).write_all(
        [
            _memory(repository, "retry", "symbol", "jobs.py:retry"),
            _memory(repository, "backoff", "symbol", "jobs.py:backoff"),
            _memory(repository, "settings", "config", "settings.json#/retries"),
            _memory(repository, "flags", "config", "flags.json#/beta"),
        ]
    )


def _reasons(repository: Path) -> dict[str, dict[str, str] | None]:
    return {memory.id: memory.stale_reasons for memory in MemoryStore(repository).load_all()}


def test_dream_records_why_each_piece_of_evidence_broke(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "jobs.py").write_text("def retry():\n    return 3\n", encoding="utf-8")
    (tmp_path / "settings.json").unlink()
    (tmp_path / "flags.json").write_text("{broken", encoding="utf-8")

    summary = dream(tmp_path)

    assert summary.errors == []
    assert summary.marked_stale == ["backoff", "flags", "settings"]
    reasons = _reasons(tmp_path)
    assert reasons["retry"] is None
    assert reasons["backoff"] == {"symbol:jobs.py:backoff": "locator_missing"}
    assert reasons["settings"] == {"config:settings.json#/retries": "file_missing"}
    assert reasons["flags"] == {"config:flags.json#/beta": "unresolvable"}


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_dream_isolates_an_unreadable_source_from_other_audits(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "settings.json").write_text('{"retries": 5}\n', encoding="utf-8")
    source = tmp_path / "jobs.py"
    source.chmod(0)
    try:
        summary = dream(tmp_path)
    finally:
        source.chmod(0o644)

    assert [error.split(": ")[0:2] for error in summary.errors] == [
        ["backoff:symbol:jobs.py:backoff", "PermissionError"],
        ["retry:symbol:jobs.py:retry", "PermissionError"],
    ]
    assert "settings" in summary.marked_stale
    assert _reasons(tmp_path)["settings"] == {"config:settings.json#/retries": "changed"}

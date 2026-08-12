"""Explicit wide reconciliation for project memory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory_stale.evidence import EvidenceError, resolve_stored_item
from memory_stale.lifecycle import RefEvidence, reconcile
from memory_stale.memory_store import MemoryStore


@dataclass(frozen=True)
class DreamSummary:
    audited: list[str]
    marked_stale: list[str]
    errors: list[str]


def dream(repository: Path) -> DreamSummary:
    store = MemoryStore(repository)
    memories = store.load_all()
    evidence: dict[str, RefEvidence] = {}
    affected: set[str] = {memory.id for memory in memories if memory.status == "stale"}
    errors: list[str] = []
    for memory in memories:
        if memory.status != "active":
            continue
        for item in memory.evidence:
            try:
                current = resolve_stored_item(repository, item)
                evidence[item.key] = RefEvidence(current)
                if current != item.fingerprint:
                    affected.add(memory.id)
            except EvidenceError as error:  # noqa: PERF203 - isolate each item failure
                evidence[item.key] = RefEvidence(None, _evidence_error_reason(error))
                affected.add(memory.id)
            except Exception as error:
                errors.append(f"{memory.id}:{item.key}: {type(error).__name__}: {error}")
    reconciled = reconcile(memories, [], evidence)
    previously_active = {memory.id for memory in memories if memory.status == "active"}
    marked_stale = sorted(
        memory.id
        for memory in reconciled
        if memory.id in previously_active and memory.status == "stale"
    )
    store.write_all(reconciled)
    return DreamSummary(sorted(affected), marked_stale, errors)


def _evidence_error_reason(error: EvidenceError) -> str:
    message = str(error)
    if "file not found" in message:
        return "file_missing"
    if "locator not found" in message or "symbol not found" in message:
        return "locator_missing"
    return "unresolvable"

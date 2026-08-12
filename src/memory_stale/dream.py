"""Explicit wide reconciliation for project memory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory_stale.lifecycle import RefEvidence, reconcile
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer, SymbolIndexError, SymbolNotFoundError


@dataclass(frozen=True)
class DreamSummary:
    audited: list[str]
    marked_stale: list[str]
    errors: list[str]


def dream(repository: Path) -> DreamSummary:
    store = MemoryStore(repository)
    memories = store.load_all()
    indexer = SymbolIndexer(repository)
    evidence: dict[str, RefEvidence] = {}
    affected: set[str] = {memory.id for memory in memories if memory.status == "stale"}
    errors: list[str] = []
    for memory in memories:
        if memory.status != "active":
            continue
        for ref, expected in memory.signatures.items():
            try:
                current = indexer.signature(ref)
                evidence[ref] = RefEvidence(current)
                if current != expected:
                    affected.add(memory.id)
            except SymbolNotFoundError as error:  # noqa: PERF203 - isolate each ref failure
                reason = "file_missing" if "file not found" in str(error) else "symbol_missing"
                evidence[ref] = RefEvidence(None, reason)
                affected.add(memory.id)
            except SymbolIndexError:
                evidence[ref] = RefEvidence(None, "unresolvable")
                affected.add(memory.id)
            except Exception as error:
                errors.append(f"{memory.id}:{ref}: {type(error).__name__}: {error}")
    reconciled = reconcile(memories, [], evidence)
    previously_active = {memory.id for memory in memories if memory.status == "active"}
    marked_stale = sorted(
        memory.id
        for memory in reconciled
        if memory.id in previously_active and memory.status == "stale"
    )
    store.write_all(reconciled)
    return DreamSummary(sorted(affected), marked_stale, errors)

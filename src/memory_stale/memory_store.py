"""Project-local Markdown memory store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml

from memory_stale.evidence import EvidenceEdge, EvidenceItem
from memory_stale.lifecycle import Memory, migrate_legacy_memory


class MemoryStore:
    def __init__(self, repository: Path) -> None:
        self.directory = repository / ".agents" / "skills" / ".agent-memory" / "memories"

    def load_all(self) -> list[Memory]:
        if not self.directory.is_dir():
            return []
        return [self._load(path) for path in sorted(self.directory.glob("*.md"))]

    def write_all(self, memories: list[Memory]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        for memory in memories:
            self._write(memory)
        expected = {f"{memory.id}.md" for memory in memories}
        for path in self.directory.glob("*.md"):
            if path.name not in expected:
                path.unlink()

    def _write(self, memory: Memory) -> None:
        path = self.directory / f"{memory.id}.md"
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        data = {
            "schema_version": memory.schema_version,
            "claim_id": memory.claim_id or memory.id,
            "revision_id": memory.id,
            "kind": memory.kind,
            "status": memory.status,
            "durability_reason": memory.durability_reason,
            "evidence": [
                {
                    "type": item.type,
                    "role": item.role,
                    "locator": item.locator,
                    "fingerprint": item.fingerprint,
                }
                for item in memory.evidence
            ],
            "supported_by": list(memory.supported_by),
            "dependencies": [
                {"from": edge.source, "to": edge.target} for edge in memory.dependencies
            ],
            "stale_reasons": memory.stale_reasons,
            "observed_commit": memory.observed_commit,
            "observed_at": memory.observed_at,
            "legacy_id": memory.legacy_id,
        }
        text = f"---\n{yaml.safe_dump(data, sort_keys=True)}---\n\n{memory.claim}\n"
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self, path: Path) -> Memory:
        text = path.read_text(encoding="utf-8")
        _opening, front_matter, claim = text.split("---", 2)
        data = cast(dict[str, object], yaml.safe_load(front_matter))
        stale_reasons = cast(dict[str, str] | None, data.get("stale_reasons"))
        schema_version = data.get("schema_version")
        if schema_version == 3:
            evidence = _evidence(data, path)
            return Memory(
                id=str(data["revision_id"]),
                kind=str(data["kind"]),
                status=str(data["status"]),
                claim=claim.strip(),
                durability_reason=str(data["durability_reason"]),
                evidence=evidence,
                stale_reasons=stale_reasons,
                claim_id=_optional_string(data, "claim_id") or str(data["revision_id"]),
                observed_commit=_optional_string(data, "observed_commit"),
                observed_at=_optional_string(data, "observed_at"),
                legacy_id=_optional_string(data, "legacy_id"),
            )
        if schema_version != 4:
            signatures = cast(dict[str, str], data["signatures"])
            return migrate_legacy_memory(
                legacy_id=str(data.get("revision_id", data.get("id"))),
                kind=str(data["kind"]),
                status=str(data["status"]),
                claim=claim.strip(),
                durability_reason=str(data["durability_reason"]),
                signatures=signatures,
                stale_reasons=stale_reasons,
                observed_commit=_optional_string(data, "observed_commit"),
                observed_at=_optional_string(data, "observed_at"),
            )
        evidence = _evidence(data, path)
        supported_by = _supported_by(data, path)
        dependencies = _dependencies(data, path)
        _validate_graph(evidence, supported_by, dependencies, path)
        return Memory(
            id=str(data["revision_id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            claim=claim.strip(),
            durability_reason=str(data["durability_reason"]),
            evidence=evidence,
            stale_reasons=stale_reasons,
            schema_version=schema_version,
            claim_id=_optional_string(data, "claim_id") or str(data["revision_id"]),
            observed_commit=_optional_string(data, "observed_commit"),
            observed_at=_optional_string(data, "observed_at"),
            legacy_id=_optional_string(data, "legacy_id"),
            supported_by=supported_by,
            dependencies=dependencies,
        )


def _evidence(data: dict[str, object], path: Path) -> tuple[EvidenceItem, ...]:
    raw_items = data.get("evidence")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"invalid evidence in {path}")
    items: list[EvidenceItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError(f"invalid evidence item in {path}")
        item = cast(dict[str, object], raw)
        items.append(
            EvidenceItem(
                _evidence_string(item, "type", path),
                _evidence_string(item, "role", path),
                _evidence_string(item, "locator", path),
                _evidence_string(item, "fingerprint", path),
            )
        )
    canonical = tuple(sorted(items))
    if len({(item.type, item.locator) for item in canonical}) != len(canonical):
        raise ValueError(f"duplicate evidence item in {path}")
    if not any(item.role == "primary" for item in canonical):
        raise ValueError(f"missing primary evidence in {path}")
    return canonical


def _evidence_string(data: dict[str, object], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid evidence item in {path}")
    return value


def _supported_by(data: dict[str, object], path: Path) -> tuple[str, ...]:
    raw = data.get("supported_by")
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"invalid supported_by in {path}")
    result = tuple(sorted(cast(list[str], raw)))
    if len(set(result)) != len(result):
        raise ValueError(f"duplicate supported_by in {path}")
    return result


def _dependencies(data: dict[str, object], path: Path) -> tuple[EvidenceEdge, ...]:
    raw = data.get("dependencies")
    if not isinstance(raw, list):
        raise ValueError(f"invalid dependencies in {path}")
    edges: list[EvidenceEdge] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"from", "to"}:
            raise ValueError(f"invalid dependency in {path}")
        edge = cast(dict[str, object], item)
        edges.append(
            EvidenceEdge(_evidence_string(edge, "from", path), _evidence_string(edge, "to", path))
        )
    result = tuple(sorted(set(edges)))
    if len(result) != len(edges):
        raise ValueError(f"duplicate dependency in {path}")
    return result


def _validate_graph(
    evidence: tuple[EvidenceItem, ...],
    supported_by: tuple[str, ...],
    dependencies: tuple[EvidenceEdge, ...],
    path: Path,
) -> None:
    keys = {item.key for item in evidence}
    if not set(supported_by) <= keys:
        raise ValueError(f"supported_by references unknown evidence in {path}")
    if any(edge.source not in keys or edge.target not in keys for edge in dependencies):
        raise ValueError(f"dependency references unknown evidence in {path}")


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None

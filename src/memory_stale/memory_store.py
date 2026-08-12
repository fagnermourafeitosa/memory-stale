"""Project-local Markdown memory store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml

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
            "signatures": memory.signatures,
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
        signatures = cast(dict[str, str], data["signatures"])
        stale_reasons = cast(dict[str, str] | None, data.get("stale_reasons"))
        schema_version = data.get("schema_version")
        if schema_version is None:
            return migrate_legacy_memory(
                legacy_id=str(data["id"]),
                kind=str(data["kind"]),
                status=str(data["status"]),
                claim=claim.strip(),
                durability_reason=str(data["durability_reason"]),
                signatures=signatures,
                stale_reasons=stale_reasons,
            )
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError(f"invalid schema_version in {path}")
        return Memory(
            id=str(data["revision_id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            claim=claim.strip(),
            durability_reason=str(data["durability_reason"]),
            signatures=signatures,
            stale_reasons=stale_reasons,
            schema_version=schema_version,
            claim_id=_optional_string(data, "claim_id") or str(data["revision_id"]),
            observed_commit=_optional_string(data, "observed_commit"),
            observed_at=_optional_string(data, "observed_at"),
            legacy_id=_optional_string(data, "legacy_id"),
        )


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None

"""Project-local Markdown memory store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml

from memory_stale.lifecycle import Memory


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

    def _write(self, memory: Memory) -> None:
        path = self.directory / f"{memory.id}.md"
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        data = {
            "id": memory.id,
            "kind": memory.kind,
            "status": memory.status,
            "durability_reason": memory.durability_reason,
            "signatures": memory.signatures,
            "stale_reasons": memory.stale_reasons,
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
        return Memory(
            id=str(data["id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            claim=claim.strip(),
            durability_reason=str(data["durability_reason"]),
            signatures=cast(dict[str, str], data["signatures"]),
            stale_reasons=cast(dict[str, str] | None, data.get("stale_reasons")),
        )

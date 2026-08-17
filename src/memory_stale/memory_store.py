"""Project-local OKF-compatible Markdown memory store."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import yaml

from memory_stale.evidence import EvidenceEdge, EvidenceItem
from memory_stale.lifecycle import Memory, migrate_legacy_memory, normalize_retrieval_terms

_OKF_TYPE = "Memory Stale Claim"
_KNOWN_OKF_FIELDS = frozenset(
    {"type", "title", "description", "sources", "generated", "verified", "status", "memory_stale"}
)


class MemoryStore:
    def __init__(
        self,
        repository: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.directory = repository / ".agents" / "skills" / ".agent-memory" / "memories"
        self._clock = clock or _utc_now

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
        generated_at = memory.generated_at or memory.observed_at or _timestamp(self._clock())
        extension = {
            "schema_version": 5,
            "claim_id": memory.claim_id or memory.id,
            "revision_id": memory.id,
            "kind": memory.kind,
            "status": memory.status,
            "durability_reason": memory.durability_reason,
            "evidence": [
                {
                    "source_id": item.key,
                    "type": item.type,
                    "role": item.role,
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
            "observed_at": memory.observed_at or generated_at,
            "legacy_id": memory.legacy_id,
        }
        if memory.retrieval_terms:
            extension["retrieval_terms"] = list(memory.retrieval_terms)
        data: dict[str, object] = {
            "type": _OKF_TYPE,
            "title": _display_title(memory.claim),
            "description": memory.durability_reason,
            "sources": [{"id": item.key, "resource": item.locator} for item in memory.evidence],
            "generated": {"by": "process:memory-stale", "at": generated_at},
            "verified": [{"by": "process:memory-stale", "at": generated_at}],
            "status": _okf_status(memory.status),
        }
        data.update(memory.okf_extras)
        data["memory_stale"] = extension
        text = f"---\n{yaml.safe_dump(data, sort_keys=False)}---\n\n{memory.claim}\n"
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self, path: Path) -> Memory:
        text = path.read_text(encoding="utf-8")
        _opening, front_matter, claim = text.split("---", 2)
        loaded = yaml.safe_load(front_matter)
        if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
            raise ValueError(f"invalid front matter in {path}")
        data = cast(dict[str, object], loaded)
        extension = data.get("memory_stale")
        if isinstance(extension, dict) and extension.get("schema_version") == 5:
            return _load_v5(data, claim.strip(), path)
        return _load_legacy(data, claim.strip(), path)


def _load_v5(data: dict[str, object], claim: str, path: Path) -> Memory:
    if data.get("type") != _OKF_TYPE:
        raise ValueError(f"invalid OKF type in {path}")
    extension = _mapping(data, "memory_stale", path)
    title = _string(data, "title", path)
    durability_reason = _string(data, "description", path)
    if title != _display_title(claim) or not claim:
        raise ValueError(f"invalid title in {path}")
    generated_at = _generated_at(data, path)
    _verified(data, generated_at, path)
    evidence = _v5_evidence(extension, data, path)
    supported_by = _supported_by(extension, path)
    dependencies = _dependencies(extension, path)
    _validate_graph(evidence, supported_by, dependencies, path)
    status = _string(extension, "status", path)
    if status not in {"active", "stale", "superseded"} or data.get("status") != _okf_status(status):
        raise ValueError(f"invalid status in {path}")
    stale_reasons = _stale_reasons(extension, path)
    if stale_reasons is not None and not set(stale_reasons) <= {item.key for item in evidence}:
        raise ValueError(f"stale reason references unknown evidence in {path}")
    extras = {key: value for key, value in data.items() if key not in _KNOWN_OKF_FIELDS}
    return Memory(
        id=_string(extension, "revision_id", path),
        kind=_string(extension, "kind", path),
        status=status,
        claim=claim,
        durability_reason=durability_reason,
        evidence=evidence,
        stale_reasons=stale_reasons,
        schema_version=5,
        claim_id=_string(extension, "claim_id", path),
        observed_commit=_optional_string(extension, "observed_commit", path),
        observed_at=_optional_string(extension, "observed_at", path),
        generated_at=generated_at,
        legacy_id=_optional_string(extension, "legacy_id", path),
        supported_by=supported_by,
        dependencies=dependencies,
        retrieval_terms=_retrieval_terms(extension, path),
        okf_extras=extras,
    )


def _load_legacy(data: dict[str, object], claim: str, path: Path) -> Memory:
    stale_reasons = _legacy_stale_reasons(data, path)
    schema_version = data.get("schema_version")
    if schema_version == 3:
        evidence = _legacy_evidence(data, path)
        return Memory(
            id=_string(data, "revision_id", path),
            kind=_string(data, "kind", path),
            status=_string(data, "status", path),
            claim=claim,
            durability_reason=_string(data, "durability_reason", path),
            evidence=evidence,
            stale_reasons=stale_reasons,
            claim_id=_optional_string(data, "claim_id", path) or _string(data, "revision_id", path),
            observed_commit=_optional_string(data, "observed_commit", path),
            observed_at=_optional_string(data, "observed_at", path),
            generated_at=_optional_string(data, "observed_at", path),
            legacy_id=_optional_string(data, "legacy_id", path),
        )
    if schema_version == 4:
        evidence = _legacy_evidence(data, path)
        supported_by = _supported_by(data, path)
        dependencies = _dependencies(data, path)
        _validate_graph(evidence, supported_by, dependencies, path)
        return Memory(
            id=_string(data, "revision_id", path),
            kind=_string(data, "kind", path),
            status=_string(data, "status", path),
            claim=claim,
            durability_reason=_string(data, "durability_reason", path),
            evidence=evidence,
            stale_reasons=stale_reasons,
            claim_id=_optional_string(data, "claim_id", path) or _string(data, "revision_id", path),
            observed_commit=_optional_string(data, "observed_commit", path),
            observed_at=_optional_string(data, "observed_at", path),
            generated_at=_optional_string(data, "observed_at", path),
            legacy_id=_optional_string(data, "legacy_id", path),
            supported_by=supported_by,
            dependencies=dependencies,
        )
    signatures = data.get("signatures")
    if not isinstance(signatures, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in signatures.items()
    ):
        raise ValueError(f"invalid legacy signatures in {path}")
    return migrate_legacy_memory(
        legacy_id=str(data.get("revision_id", data.get("id"))),
        kind=_string(data, "kind", path),
        status=_string(data, "status", path),
        claim=claim,
        durability_reason=_string(data, "durability_reason", path),
        signatures=cast(dict[str, str], signatures),
        stale_reasons=stale_reasons,
        observed_commit=_optional_string(data, "observed_commit", path),
        observed_at=_optional_string(data, "observed_at", path),
    )


def _v5_evidence(
    extension: dict[str, object], data: dict[str, object], path: Path
) -> tuple[EvidenceItem, ...]:
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"invalid sources in {path}")
    resources: dict[str, str] = {}
    for raw in sources:
        if not isinstance(raw, dict):
            raise ValueError(f"invalid source in {path}")
        source = cast(dict[str, object], raw)
        source_id = _string(source, "id", path)
        source_resource = _string(source, "resource", path)
        if source_id in resources:
            raise ValueError(f"duplicate source in {path}")
        resources[source_id] = source_resource
    raw_items = extension.get("evidence")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"invalid evidence in {path}")
    items: list[EvidenceItem] = []
    source_ids: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError(f"invalid evidence item in {path}")
        item = cast(dict[str, object], raw)
        source_id = _string(item, "source_id", path)
        item_type = _string(item, "type", path)
        resource = resources.get(source_id)
        if resource is None or source_id != f"{item_type}:{resource}":
            raise ValueError(f"mismatched evidence source in {path}")
        source_ids.add(source_id)
        items.append(
            EvidenceItem(
                item_type,
                _string(item, "role", path),
                resource,
                _string(item, "fingerprint", path),
            )
        )
    if source_ids != set(resources) or len(source_ids) != len(items):
        raise ValueError(f"evidence and sources differ in {path}")
    return _canonical_evidence(items, path)


def _legacy_evidence(data: dict[str, object], path: Path) -> tuple[EvidenceItem, ...]:
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
                _string(item, "type", path),
                _string(item, "role", path),
                _string(item, "locator", path),
                _string(item, "fingerprint", path),
            )
        )
    return _canonical_evidence(items, path)


def _canonical_evidence(items: list[EvidenceItem], path: Path) -> tuple[EvidenceItem, ...]:
    canonical = tuple(sorted(items))
    if len({(item.type, item.locator) for item in canonical}) != len(canonical):
        raise ValueError(f"duplicate evidence item in {path}")
    if not any(item.role == "primary" for item in canonical):
        raise ValueError(f"missing primary evidence in {path}")
    return canonical


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
        edges.append(EvidenceEdge(_string(edge, "from", path), _string(edge, "to", path)))
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


def _generated_at(data: dict[str, object], path: Path) -> str:
    generated = _mapping(data, "generated", path)
    if generated.get("by") != "process:memory-stale":
        raise ValueError(f"invalid generated actor in {path}")
    return _string(generated, "at", path)


def _verified(data: dict[str, object], generated_at: str, path: Path) -> None:
    raw = data.get("verified")
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise ValueError(f"invalid verification in {path}")
    verification = cast(dict[str, object], raw[0])
    if verification != {"by": "process:memory-stale", "at": generated_at}:
        raise ValueError(f"invalid verification in {path}")


def _stale_reasons(data: dict[str, object], path: Path) -> dict[str, str] | None:
    value = data.get("stale_reasons")
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(reason, str) for key, reason in value.items()
    ):
        raise ValueError(f"invalid stale reasons in {path}")
    return dict(sorted(cast(dict[str, str], value).items()))


def _retrieval_terms(data: dict[str, object], path: Path) -> tuple[str, ...]:
    try:
        return normalize_retrieval_terms(data.get("retrieval_terms"))
    except ValueError as error:
        raise ValueError(f"invalid retrieval_terms in {path}: {error}") from error


def _legacy_stale_reasons(data: dict[str, object], path: Path) -> dict[str, str] | None:
    value = data.get("stale_reasons")
    if value is None:
        return None
    return _stale_reasons(data, path)


def _mapping(data: Mapping[str, object], key: str, path: Path) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict) or not all(isinstance(name, str) for name in value):
        raise ValueError(f"invalid {key} in {path}")
    return cast(dict[str, object], value)


def _string(data: Mapping[str, object], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {key} in {path}")
    return value


def _optional_string(data: Mapping[str, object], key: str, path: Path) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {key} in {path}")
    return value


def _display_title(claim: str) -> str:
    return " ".join(claim.split())


def _okf_status(status: str) -> str:
    return "stable" if status == "active" else "deprecated"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()

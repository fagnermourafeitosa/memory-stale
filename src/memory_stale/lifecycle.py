"""Pure memory lifecycle engine."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import cast

from memory_stale.evidence import EvidenceEdge, EvidenceItem

MAX_RETRIEVAL_TERMS = 8
MAX_RETRIEVAL_TERM_LENGTH = 80


@dataclass(frozen=True)
class RefEvidence:
    signature: str | None
    reason: str | None = None


@dataclass(frozen=True)
class Memory:
    id: str
    kind: str
    status: str
    claim: str
    durability_reason: str
    evidence: tuple[EvidenceItem, ...]
    stale_reasons: dict[str, str] | None = None
    schema_version: int = 5
    claim_id: str | None = None
    observed_commit: str | None = None
    observed_at: str | None = None
    generated_at: str | None = field(default=None, compare=False)
    legacy_id: str | None = None
    supported_by: tuple[str, ...] = ()
    dependencies: tuple[EvidenceEdge, ...] = ()
    dependency_extractor_version: str | None = None
    dependency_expansion_complete: bool | None = None
    retrieval_terms: tuple[str, ...] = ()
    okf_extras: dict[str, object] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.supported_by:
            object.__setattr__(self, "supported_by", tuple(item.key for item in self.evidence))

    @property
    def signatures(self) -> dict[str, str]:
        """Compatibility view for consumers that display evidence fingerprints."""
        return {item.key: item.fingerprint for item in self.evidence}


def _identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _claim_id(kind: str, claim: str, evidence: Sequence[EvidenceItem]) -> str:
    normalized_claim = " ".join(claim.casefold().split())
    primary_scope = "\0".join(
        f"{item.type}\0{item.locator}" for item in evidence if item.role == "primary"
    )
    return _identifier(f"{kind}\0{normalized_claim}\0{primary_scope}")


def _revision_id(
    claim_id: str,
    evidence: Sequence[EvidenceItem],
    supported_by: Sequence[str],
    dependencies: Sequence[EvidenceEdge],
    retrieval_terms: Sequence[str],
) -> str:
    fingerprints = "\0".join(
        f"{item.type}\0{item.role}\0{item.locator}\0{item.fingerprint}" for item in evidence
    )
    graph = "\0".join(
        (
            *supported_by,
            *(
                f"{edge.source}\0{edge.target}\0{edge.relationship}\0{edge.origin}"
                for edge in dependencies
            ),
        )
    )
    terms = "\0".join(term.casefold() for term in retrieval_terms)
    return _identifier(f"{claim_id}\0{fingerprints}\0{graph}\0{terms}")


def _capture_memory(capture: Mapping[str, object]) -> Memory:
    kind = str(capture["kind"])
    claim = str(capture["claim"])
    durability_reason = str(capture["durability_reason"])
    evidence_value = capture.get("evidence")
    if not isinstance(evidence_value, list):
        raise ValueError("capture evidence must be an array")
    evidence = _stored_items(evidence_value)
    supported_by = _stored_supported_by(capture.get("supported_by"), evidence)
    dependencies = _stored_edges(capture.get("dependencies"), evidence)
    retrieval_terms = normalize_retrieval_terms(capture.get("retrieval_terms"))
    claim_id = _claim_id(kind, claim, evidence)
    revision_id = _revision_id(claim_id, evidence, supported_by, dependencies, retrieval_terms)
    return Memory(
        id=revision_id,
        kind=kind,
        status="active",
        claim=claim,
        durability_reason=durability_reason,
        evidence=evidence,
        claim_id=claim_id,
        observed_commit=_optional_string(capture, "observed_commit"),
        observed_at=_optional_string(capture, "observed_at"),
        generated_at=_optional_string(capture, "generated_at")
        or _optional_string(capture, "observed_at"),
        supported_by=supported_by,
        dependencies=dependencies,
        dependency_extractor_version=_optional_string(capture, "dependency_extractor_version"),
        dependency_expansion_complete=_optional_bool(capture, "dependency_expansion_complete"),
        retrieval_terms=retrieval_terms,
    )


def normalize_retrieval_terms(value: object) -> tuple[str, ...]:
    """Return canonical, bounded host-declared retrieval vocabulary."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("retrieval_terms must be an array")
    if len(value) > MAX_RETRIEVAL_TERMS:
        raise ValueError(f"retrieval_terms must contain at most {MAX_RETRIEVAL_TERMS} items")
    terms: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("retrieval_terms must contain only strings")
        term = item.strip()
        if not term:
            raise ValueError("retrieval_terms must not contain blank strings")
        if len(term) > MAX_RETRIEVAL_TERM_LENGTH:
            raise ValueError(
                f"retrieval_terms entries must contain at most {MAX_RETRIEVAL_TERM_LENGTH} characters"
            )
        terms.append((term.casefold(), term))
    canonical = tuple(sorted(terms))
    if len({term for term, _display in canonical}) != len(canonical):
        raise ValueError("retrieval_terms must not contain duplicates")
    return tuple(display for _term, display in canonical)


def _stored_items(value: list[object]) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("capture evidence item must be an object")
        item = cast(dict[str, object], raw)
        items.append(
            EvidenceItem(
                _evidence_string(item, "type"),
                _evidence_string(item, "role"),
                _evidence_string(item, "locator"),
                _evidence_string(item, "fingerprint"),
            )
        )
    canonical = tuple(sorted(items))
    if not canonical or not any(item.role == "primary" for item in canonical):
        raise ValueError("capture evidence requires a primary item")
    if len({(item.type, item.locator) for item in canonical}) != len(canonical):
        raise ValueError("capture evidence must not contain duplicate locators")
    return canonical


def _evidence_string(item: Mapping[str, object], name: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError("capture evidence item is invalid")
    return value


def _stored_supported_by(value: object, evidence: Sequence[EvidenceItem]) -> tuple[str, ...]:
    if value is None:
        return tuple(item.key for item in evidence)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError("capture supported_by must be a non-empty array")
    supported_by = tuple(sorted(cast(list[str], value)))
    keys = {item.key for item in evidence}
    if len(set(supported_by)) != len(supported_by) or not set(supported_by) <= keys:
        raise ValueError("capture supported_by has unknown or duplicate evidence")
    return supported_by


def _stored_edges(value: object, evidence: Sequence[EvidenceItem]) -> tuple[EvidenceEdge, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("capture dependencies must be an array")
    edges: list[EvidenceEdge] = []
    keys = {item.key for item in evidence}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("capture dependency must be an object")
        edge = cast(dict[str, object], raw)
        source = _evidence_string(edge, "from")
        target = _evidence_string(edge, "to")
        if not {"from", "to"} <= set(edge) <= {"from", "to", "relationship", "origin"}:
            raise ValueError("capture dependency has unsupported fields")
        relationship = str(edge.get("relationship", "depends_on"))
        origin = str(edge.get("origin", "declared"))
        if source not in keys or target not in keys:
            raise ValueError("capture dependency has an unknown node")
        if relationship not in {"depends_on", "calls", "reads"}:
            raise ValueError("capture dependency has an invalid relationship")
        if origin not in {"declared", "static"}:
            raise ValueError("capture dependency has an invalid origin")
        edges.append(EvidenceEdge(source, target, relationship, origin))
    canonical = tuple(sorted(set(edges)))
    if len(canonical) != len(edges):
        raise ValueError("capture dependencies must not contain duplicates")
    return canonical


def _optional_string(capture: Mapping[str, object], name: str) -> str | None:
    value = capture.get(name)
    return value if isinstance(value, str) and value else None


def _optional_bool(capture: Mapping[str, object], name: str) -> bool | None:
    value = capture.get(name)
    return value if isinstance(value, bool) else None


def migrate_legacy_memory(
    *,
    legacy_id: str,
    kind: str,
    status: str,
    claim: str,
    durability_reason: str,
    signatures: dict[str, str],
    stale_reasons: dict[str, str] | None,
    observed_commit: str | None = None,
    observed_at: str | None = None,
) -> Memory:
    """Migrate implicit symbol refs into primary typed evidence."""
    evidence = tuple(
        EvidenceItem("symbol", "primary", locator, fingerprint)
        for locator, fingerprint in sorted(signatures.items())
    )
    claim_id = _claim_id(kind, claim, evidence)
    supported_by = tuple(item.key for item in evidence)
    revision_id = _revision_id(claim_id, evidence, supported_by, (), ())
    remapped_reasons = (
        {f"symbol:{locator}": reason for locator, reason in stale_reasons.items()}
        if stale_reasons
        else None
    )
    return Memory(
        id=revision_id,
        kind=kind,
        status=status,
        claim=claim,
        durability_reason=durability_reason,
        evidence=evidence,
        stale_reasons=remapped_reasons,
        claim_id=claim_id,
        observed_commit=observed_commit,
        observed_at=observed_at,
        generated_at=observed_at,
        legacy_id=legacy_id if legacy_id != revision_id else None,
        supported_by=supported_by,
    )


def reconcile(
    memories: Sequence[Memory],
    captures: Sequence[Mapping[str, object]],
    evidence: Mapping[str, RefEvidence],
) -> list[Memory]:
    result: list[Memory] = []
    for memory in memories:
        if memory.status != "active":
            result.append(memory)
            continue
        reasons: dict[str, str] = {}
        paths = _provenance_paths(memory)
        for item in memory.evidence:
            current = evidence.get(item.key)
            if current is None or current.signature is None:
                reason = current.reason if current and current.reason else "unresolvable"
                reasons[item.key] = _with_path(reason, paths.get(item.key, (item.key,)))
            elif current.signature != item.fingerprint:
                reasons[item.key] = _with_path("changed", paths.get(item.key, (item.key,)))
        result.append(
            replace(memory, status="stale", stale_reasons=dict(sorted(reasons.items())))
            if reasons
            else memory
        )
    known = {memory.id for memory in result}
    for capture in captures:
        memory = _capture_memory(capture)
        if memory.id in known:
            continue
        for index, existing in enumerate(result):
            if existing.status == "active" and existing.claim_id == memory.claim_id:
                result[index] = replace(existing, status="superseded", stale_reasons=None)
        result.append(memory)
        known.add(memory.id)
    return result


def _provenance_paths(memory: Memory) -> dict[str, str]:
    adjacency: dict[str, list[EvidenceEdge]] = {}
    for edge in memory.dependencies:
        adjacency.setdefault(edge.source, []).append(edge)
    paths: dict[str, str] = {}
    queue: list[tuple[str, str]] = [(root, root) for root in sorted(memory.supported_by)]
    while queue:
        node, path = queue.pop(0)
        if node in paths:
            continue
        paths[node] = path
        for edge in sorted(adjacency.get(node, [])):
            if edge.target in paths:
                continue
            separator = (
                " -> " if edge.relationship == "depends_on" else f" -[{edge.relationship}]-> "
            )
            queue.append((edge.target, f"{path}{separator}{edge.target}"))
    return paths


def _with_path(reason: str, path: str | tuple[str, ...]) -> str:
    rendered = " -> ".join(path) if isinstance(path, tuple) else path
    return reason if "->" not in rendered else f"{reason} via {rendered}"

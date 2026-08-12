"""Pure memory lifecycle engine."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

from memory_stale.evidence import EvidenceItem


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
    schema_version: int = 3
    claim_id: str | None = None
    observed_commit: str | None = None
    observed_at: str | None = None
    legacy_id: str | None = None

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


def _revision_id(claim_id: str, evidence: Sequence[EvidenceItem]) -> str:
    fingerprints = "\0".join(
        f"{item.type}\0{item.role}\0{item.locator}\0{item.fingerprint}" for item in evidence
    )
    return _identifier(f"{claim_id}\0{fingerprints}")


def _capture_memory(capture: Mapping[str, object]) -> Memory:
    kind = str(capture["kind"])
    claim = str(capture["claim"])
    durability_reason = str(capture["durability_reason"])
    evidence_value = capture.get("evidence")
    if not isinstance(evidence_value, list):
        raise ValueError("capture evidence must be an array")
    evidence = _stored_items(evidence_value)
    claim_id = _claim_id(kind, claim, evidence)
    revision_id = _revision_id(claim_id, evidence)
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
    )


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


def _optional_string(capture: Mapping[str, object], name: str) -> str | None:
    value = capture.get(name)
    return value if isinstance(value, str) and value else None


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
    revision_id = _revision_id(claim_id, evidence)
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
        legacy_id=legacy_id if legacy_id != revision_id else None,
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
        for item in memory.evidence:
            current = evidence.get(item.key)
            if current is None or current.signature is None:
                reasons[item.key] = current.reason if current and current.reason else "unresolvable"
            elif current.signature != item.fingerprint:
                reasons[item.key] = "changed"
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

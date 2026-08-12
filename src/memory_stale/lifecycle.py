"""Pure memory lifecycle engine."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace


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
    signatures: dict[str, str]
    stale_reasons: dict[str, str] | None = None
    schema_version: int = 2
    claim_id: str | None = None
    observed_commit: str | None = None
    observed_at: str | None = None
    legacy_id: str | None = None


def _identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _claim_id(kind: str, claim: str, signatures: Mapping[str, str]) -> str:
    normalized_claim = " ".join(claim.casefold().split())
    canonical_scope = "\0".join(sorted(signatures))
    return _identifier(f"{kind}\0{normalized_claim}\0{canonical_scope}")


def _revision_id(claim_id: str, signatures: Mapping[str, str]) -> str:
    fingerprints = "\0".join(f"{ref}\0{signature}" for ref, signature in sorted(signatures.items()))
    return _identifier(f"{claim_id}\0{fingerprints}")


def _capture_memory(capture: Mapping[str, object]) -> Memory:
    kind = str(capture["kind"])
    claim = str(capture["claim"])
    durability_reason = str(capture["durability_reason"])
    signatures_value = capture["signatures"]
    if not isinstance(signatures_value, dict):
        raise ValueError("capture signatures must be an object")
    signatures = {str(ref): str(signature) for ref, signature in signatures_value.items()}
    claim_id = _claim_id(kind, claim, signatures)
    revision_id = _revision_id(claim_id, signatures)
    return Memory(
        id=revision_id,
        kind=kind,
        status="active",
        claim=claim,
        durability_reason=durability_reason,
        signatures=signatures,
        claim_id=claim_id,
        observed_commit=_optional_string(capture, "observed_commit"),
        observed_at=_optional_string(capture, "observed_at"),
    )


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
) -> Memory:
    """Create the versioned representation of one pre-schema memory."""
    claim_id = _claim_id(kind, claim, signatures)
    revision_id = _revision_id(claim_id, signatures)
    return Memory(
        id=revision_id,
        kind=kind,
        status=status,
        claim=claim,
        durability_reason=durability_reason,
        signatures=signatures,
        stale_reasons=stale_reasons,
        claim_id=claim_id,
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
        for ref, expected in memory.signatures.items():
            current = evidence.get(ref)
            if current is None or current.signature is None:
                reasons[ref] = current.reason if current and current.reason else "unresolvable"
            elif current.signature != expected:
                reasons[ref] = "changed"
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

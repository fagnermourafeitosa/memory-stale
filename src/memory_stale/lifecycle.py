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


def _capture_memory(capture: Mapping[str, object]) -> Memory:
    kind = str(capture["kind"])
    claim = str(capture["claim"])
    durability_reason = str(capture["durability_reason"])
    signatures_value = capture["signatures"]
    if not isinstance(signatures_value, dict):
        raise ValueError("capture signatures must be an object")
    signatures = {str(ref): str(signature) for ref, signature in signatures_value.items()}
    normalized_claim = " ".join(claim.casefold().split())
    normalized_refs = "\0".join(sorted(signatures))
    identity = f"{kind}\0{normalized_claim}\0{normalized_refs}"
    return Memory(
        id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        kind=kind,
        status="active",
        claim=claim,
        durability_reason=durability_reason,
        signatures=signatures,
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
        if memory.id not in known:
            result.append(memory)
            known.add(memory.id)
    return result

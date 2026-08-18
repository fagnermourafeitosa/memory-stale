"""Tests for reactive coeffects, reverse dependency indexing, HMR staleness, and target reconciliation."""

from __future__ import annotations

from memory_stale.evidence import EvidenceEdge, EvidenceItem, EvidenceTarget
from memory_stale.lifecycle import (
    Memory,
    RefEvidence,
    build_reverse_index,
    reconcile,
)


def test_evidence_target_data_model() -> None:
    target = EvidenceTarget(
        identity="src/auth/jwt.py::verify_token",
        fingerprint="sha256:abc12345",
        kind="symbol",
    )
    assert target.identity == "src/auth/jwt.py::verify_token"
    assert target.fingerprint == "sha256:abc12345"
    assert target.kind == "symbol"


def test_reverse_dependency_index_construction_and_lookup() -> None:
    item1 = EvidenceItem("symbol", "primary", "src/auth.py:login", "sig-login")
    item2 = EvidenceItem("symbol", "supporting", "src/jwt.py:verify", "sig-verify")
    item3 = EvidenceItem("symbol", "primary", "src/user.py:get_user", "sig-user")

    mem1 = Memory(
        id="mem-1",
        kind="behavior",
        status="active",
        claim="Login verifies token.",
        durability_reason="Auth contract",
        evidence=(item1, item2),
        supported_by=(item1.key,),
        dependencies=(EvidenceEdge(item1.key, item2.key, "calls", "static"),),
    )
    mem2 = Memory(
        id="mem-2",
        kind="behavior",
        status="active",
        claim="User lookup works.",
        durability_reason="User contract",
        evidence=(item3,),
        supported_by=(item3.key,),
    )

    index = build_reverse_index([mem1, mem2])

    assert index.affected_memories(["src/jwt.py:verify"]) == {"mem-1"}
    assert index.affected_memories(["src/auth.py:login"]) == {"mem-1"}
    assert index.affected_memories(["src/user.py:get_user"]) == {"mem-2"}
    assert index.affected_memories(["unrelated.py:foo"]) == set()
    assert index.affected_memories(["src/jwt.py:verify", "src/user.py:get_user"]) == {
        "mem-1",
        "mem-2",
    }


def test_hmr_staleness_propagation_on_downstream_dependency() -> None:
    caller = EvidenceItem("symbol", "primary", "src/auth/service.py:login", "sig-caller-v1")
    callee = EvidenceItem("symbol", "supporting", "src/auth/jwt.py:verify", "sig-callee-v1")

    memory = Memory(
        id="auth-mfa",
        kind="behavior",
        status="active",
        claim="Auth service uses JWT verification.",
        durability_reason="Security invariant",
        evidence=(caller, callee),
        supported_by=(caller.key,),
        dependencies=(EvidenceEdge(caller.key, callee.key, "calls", "static"),),
    )

    # Caller code unchanged, but callee code changed (HMR transitive staleness)
    reconciled = reconcile(
        [memory],
        [],
        {
            caller.key: RefEvidence("sig-caller-v1"),
            callee.key: RefEvidence("sig-callee-v2"),
        },
    )

    assert len(reconciled) == 1
    assert reconciled[0].status == "stale"
    assert callee.key in (reconciled[0].stale_reasons or {})
    assert "changed via" in (reconciled[0].stale_reasons or {})[callee.key]


def test_differentiated_lifecycle_states_unbound_and_orphan() -> None:
    sym = EvidenceItem("symbol", "primary", "src/auth.py:login", "sig-1")
    src = EvidenceItem("source", "primary", "src/missing_file.py", "sig-2")

    mem_unbound = Memory(
        id="mem-unbound",
        kind="contract",
        status="active",
        claim="Symbol renamed or deleted.",
        durability_reason="Contract",
        evidence=(sym,),
    )
    mem_orphan = Memory(
        id="mem-orphan",
        kind="contract",
        status="active",
        claim="File deleted.",
        durability_reason="Contract",
        evidence=(src,),
    )

    reconciled = reconcile(
        [mem_unbound, mem_orphan],
        [],
        {
            sym.key: RefEvidence(None, "locator_missing"),
            src.key: RefEvidence(None, "file_missing"),
        },
    )

    assert reconciled[0].status == "stale"
    assert (reconciled[0].stale_reasons or {})[sym.key] == "locator_missing"

    assert reconciled[1].status == "stale"
    assert (reconciled[1].stale_reasons or {})[src.key] == "file_missing"


def test_inertial_target_signature_computation() -> None:
    item1 = EvidenceItem("symbol", "primary", "src/auth.py:login", "sig-login")
    item2 = EvidenceItem("symbol", "supporting", "src/jwt.py:verify", "sig-verify")

    mem = Memory(
        id="mem-target",
        kind="behavior",
        status="active",
        claim="Inertial target test.",
        durability_reason="Reason",
        evidence=(item1, item2),
    )

    index = build_reverse_index([mem])
    sig1 = index.target_signature(mem)
    assert isinstance(sig1, str) and len(sig1) > 0

    # Mutate fingerprint in copy
    item2_changed = EvidenceItem("symbol", "supporting", "src/jwt.py:verify", "sig-verify-v2")
    mem_changed = Memory(
        id="mem-target",
        kind="behavior",
        status="active",
        claim="Inertial target test.",
        durability_reason="Reason",
        evidence=(item1, item2_changed),
    )
    index2 = build_reverse_index([mem_changed])
    sig2 = index2.target_signature(mem_changed)

    assert sig1 != sig2


def test_hmr_diamond_dependency_invalidation_path() -> None:
    root = EvidenceItem("symbol", "primary", "service.py:main", "sig-root")
    left = EvidenceItem("symbol", "supporting", "left.py:process", "sig-left")
    right = EvidenceItem("symbol", "supporting", "right.py:process", "sig-right")
    leaf = EvidenceItem("symbol", "supporting", "leaf.py:compute", "sig-leaf-v1")

    memory = Memory(
        id="mem-diamond",
        kind="behavior",
        status="active",
        claim="Service completes through diamond dependencies.",
        durability_reason="Architecture contract",
        evidence=(root, left, right, leaf),
        supported_by=(root.key,),
        dependencies=(
            EvidenceEdge(root.key, left.key, "calls", "static"),
            EvidenceEdge(root.key, right.key, "calls", "static"),
            EvidenceEdge(left.key, leaf.key, "calls", "static"),
            EvidenceEdge(right.key, leaf.key, "calls", "static"),
        ),
    )

    reconciled = reconcile(
        [memory],
        [],
        {
            root.key: RefEvidence("sig-root"),
            left.key: RefEvidence("sig-left"),
            right.key: RefEvidence("sig-right"),
            leaf.key: RefEvidence("sig-leaf-v2"),
        },
    )

    assert len(reconciled) == 1
    assert reconciled[0].status == "stale"
    assert leaf.key in (reconciled[0].stale_reasons or {})
    reason = (reconciled[0].stale_reasons or {})[leaf.key]
    assert "changed via" in reason
    assert root.key in reason
    assert leaf.key in reason


def test_reverse_index_unaffected_memories_are_isolated() -> None:
    memories: list[Memory] = []
    for i in range(10):
        item = EvidenceItem("symbol", "primary", f"module_{i}.py:func", f"sig-{i}")
        memories.append(
            Memory(
                id=f"mem-{i}",
                kind="behavior",
                status="active",
                claim=f"Claim {i}",
                durability_reason=f"Reason {i}",
                evidence=(item,),
                supported_by=(item.key,),
            )
        )

    index = build_reverse_index(memories)

    # Only module_3.py was modified
    affected = index.affected_memories(["module_3.py:func"])
    assert affected == {"mem-3"}

    # Multiple symbols modified
    affected_multi = index.affected_memories(["module_0.py:func", "module_7.py:func"])
    assert affected_multi == {"mem-0", "mem-7"}

    # No memories affected by unknown symbol
    assert index.affected_memories(["non_existent.py:func"]) == set()


def test_target_signature_permutation_invariance() -> None:
    item_a = EvidenceItem("symbol", "primary", "a.py:func", "sig-a")
    item_b = EvidenceItem("symbol", "supporting", "b.py:func", "sig-b")
    item_c = EvidenceItem("symbol", "supporting", "c.py:func", "sig-c")

    mem_1 = Memory(
        id="mem-1",
        kind="behavior",
        status="active",
        claim="Claim",
        durability_reason="Reason",
        evidence=(item_a, item_b, item_c),
    )
    mem_2 = Memory(
        id="mem-2",
        kind="behavior",
        status="active",
        claim="Claim",
        durability_reason="Reason",
        evidence=(item_c, item_a, item_b),
    )

    assert mem_1.target_signature == mem_2.target_signature

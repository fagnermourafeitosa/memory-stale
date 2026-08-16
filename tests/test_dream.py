from pathlib import Path

from memory_stale.dream import dream
from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer


def test_dream_does_not_audit_memory_anchored_inside_the_agents_directory(
    tmp_path: Path,
) -> None:
    installed_runtime = tmp_path / ".agents" / "skills" / "memory-stale" / "runtime.py"
    installed_runtime.parent.mkdir(parents=True)
    installed_runtime.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    signature = SymbolIndexer(tmp_path).signature(".agents/skills/memory-stale/runtime.py:run")
    store = MemoryStore(tmp_path)
    store.write_all(
        [
            Memory(
                "installed-runtime",
                "behavior",
                "active",
                "Installed runtime returns one.",
                "The hook depends on this behavior.",
                (
                    EvidenceItem(
                        "symbol",
                        "primary",
                        ".agents/skills/memory-stale/runtime.py:run",
                        signature,
                    ),
                ),
            )
        ]
    )
    installed_runtime.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")

    summary = dream(tmp_path)

    assert summary.audited == []
    assert summary.marked_stale == []
    assert summary.errors == []
    assert store.load_all()[0].status == "active"


def test_dream_limits_audit_to_stale_and_broken_evidence(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def healthy():\n    return 1\n", encoding="utf-8")
    signature = SymbolIndexer(tmp_path).signature("service.py:healthy")
    store = MemoryStore(tmp_path)
    store.write_all(
        [
            Memory(
                "healthy",
                "behavior",
                "active",
                "Healthy remains true.",
                "Stable.",
                (EvidenceItem("symbol", "primary", "service.py:healthy", signature),),
            ),
            Memory(
                "broken",
                "behavior",
                "active",
                "Missing code fact.",
                "Audit it.",
                (EvidenceItem("symbol", "primary", "missing.py:gone", "old"),),
            ),
            Memory(
                "old",
                "behavior",
                "stale",
                "Old fact.",
                "Review it.",
                (EvidenceItem("symbol", "primary", "service.py:healthy", "old"),),
                {"symbol:service.py:healthy": "changed"},
            ),
        ]
    )

    summary = dream(tmp_path)

    assert summary.audited == ["broken", "old"]
    assert summary.marked_stale == ["broken"]
    assert summary.errors == []
    memories = {memory.id: memory for memory in store.load_all()}
    assert memories["healthy"].status == "active"
    assert memories["broken"].stale_reasons == {"symbol:missing.py:gone": "file_missing"}

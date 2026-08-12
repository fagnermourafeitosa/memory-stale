from pathlib import Path
from typing import cast

from plugin_harness import PluginHarness

from memory_stale.memory_store import MemoryStore

PLUGIN_ROOT = Path(__file__).parents[1]


def test_full_context_capture_lifecycle_and_persistence_flow(tmp_path: Path) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    source = harness.root / "service.py"
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change service.py:compute")
    source.write_text("def compute():\n    return 2\n", encoding="utf-8")
    harness.hook(
        "PostToolUse",
        "turn-1",
        tool_name="apply_patch",
        tool_use_id="tool-1",
        tool_input={"command": "edit service.py"},
    )
    captured = harness.capture(
        kind="behavior",
        claim="Compute returns two.",
        refs=["service.py:compute"],
        durability_reason="Callers rely on the result.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False
    harness.hook("Stop", "turn-1")
    assert MemoryStore(harness.root).load_all()[0].status == "active"

    context = harness.hook("UserPromptSubmit", "turn-2", prompt="Modify service.py:compute")
    assert context is not None
    specific = cast(dict[str, object], context["hookSpecificOutput"])
    assert "Compute returns two." in str(specific["additionalContext"])
    source.write_text("def compute():\n    return 3\n", encoding="utf-8")
    harness.hook(
        "PostToolUse",
        "turn-2",
        tool_name="apply_patch",
        tool_use_id="tool-2",
        tool_input={"command": "edit service.py"},
    )
    harness.hook("Stop", "turn-2")
    assert MemoryStore(harness.root).load_all()[0].status == "stale"

    final_context = harness.hook("UserPromptSubmit", "turn-3", prompt="Modify service.py:compute")
    assert final_context is not None
    final_specific = cast(dict[str, object], final_context["hookSpecificOutput"])
    assert final_specific["additionalContext"] == ""


def test_recapturing_a_stale_claim_preserves_history_and_restores_active_context(
    tmp_path: Path,
) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    source = harness.root / "service.py"
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change service.py:compute")
    source.write_text("def compute():\n    return 2\n", encoding="utf-8")
    harness.capture(
        kind="behavior",
        claim="Compute has an established result.",
        refs=["service.py:compute"],
        durability_reason="Callers rely on the result.",
    )
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change service.py:compute")
    source.write_text("def compute():\n    return 3\n", encoding="utf-8")
    harness.hook("Stop", "turn-2")

    harness.hook("UserPromptSubmit", "turn-3", prompt="Change service.py:compute")
    source.write_text("def compute():\n    return 4\n", encoding="utf-8")
    recaptured = harness.capture(
        kind="behavior",
        claim="Compute has an established result.",
        refs=["service.py:compute"],
        durability_reason="Callers rely on the result.",
    )
    assert cast(dict[str, object], recaptured["result"])["isError"] is False
    harness.hook("Stop", "turn-3")

    revisions = MemoryStore(harness.root).load_all()
    assert len(revisions) == 2
    assert {revision.status for revision in revisions} == {"active", "stale"}
    assert len({revision.id for revision in revisions}) == 2
    assert len({revision.claim_id for revision in revisions}) == 1
    assert {revision.schema_version for revision in revisions} == {2}
    assert all(revision.observed_commit for revision in revisions)

    context = harness.hook("UserPromptSubmit", "turn-4", prompt="service.py:compute")
    assert context is not None
    additional_context = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert str(additional_context).count("Compute has an established result.") == 1

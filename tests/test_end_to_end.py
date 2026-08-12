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
        evidence=[{"type": "symbol", "role": "primary", "locator": "service.py:compute"}],
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


def test_supporting_symbol_evidence_invalidates_a_captured_claim(tmp_path: Path) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    login = harness.root / "auth.py"
    policy = harness.root / "policy.py"
    login.write_text("def login():\n    return False\n", encoding="utf-8")
    policy.write_text("def mfa_required():\n    return True\n", encoding="utf-8")
    harness.git("add", "auth.py", "policy.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change auth.py:login")
    login.write_text("def login():\n    return mfa_required()\n", encoding="utf-8")
    captured = harness.capture(
        kind="behavior",
        claim="Login follows the MFA policy.",
        evidence=[
            {"type": "symbol", "role": "primary", "locator": "auth.py:login"},
            {"type": "symbol", "role": "supporting", "locator": "policy.py:mfa_required"},
        ],
        durability_reason="The authentication path depends on this policy.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change policy.py:mfa_required")
    policy.write_text("def mfa_required():\n    return False\n", encoding="utf-8")
    harness.hook("Stop", "turn-2")

    revision = MemoryStore(harness.root).load_all()[0]
    assert revision.status == "stale"
    assert revision.stale_reasons == {"symbol:policy.py:mfa_required": "changed"}


def test_typed_config_schema_and_test_evidence_ignore_formatting_then_stale(
    tmp_path: Path,
) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    app = harness.root / "app.py"
    config = harness.root / "settings.yaml"
    schema = harness.root / "openapi.yaml"
    protective_test = harness.root / "test_policy.py"
    app.write_text("def login():\n    return False\n", encoding="utf-8")
    config.write_text("mfa:\n  required: true\n", encoding="utf-8")
    schema.write_text(
        "openapi: 3.1.0\ncomponents:\n  schemas:\n    Login:\n      type: object\n",
        encoding="utf-8",
    )
    protective_test.write_text("def test_mfa_policy():\n    assert True\n", encoding="utf-8")
    harness.git("add", "app.py", "settings.yaml", "openapi.yaml", "test_policy.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change app.py:login")
    app.write_text("def login():\n    return mfa_required()\n", encoding="utf-8")
    captured = harness.capture(
        kind="contract",
        claim="Login follows the configured MFA schema and protective test.",
        evidence=[
            {"type": "test", "role": "supporting", "locator": "test_policy.py:test_mfa_policy"},
            {
                "type": "schema",
                "role": "supporting",
                "locator": "openapi.yaml#/components/schemas/Login",
            },
            {"type": "symbol", "role": "primary", "locator": "app.py:login"},
            {"type": "config", "role": "supporting", "locator": "settings.yaml#/mfa/required"},
        ],
        durability_reason="Configuration, contract, and protective test constrain login.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Format evidence")
    config.write_text("# policy\nmfa:\n  required: true\n", encoding="utf-8")
    schema.write_text(
        "# API contract\nopenapi: 3.1.0\ncomponents:\n  schemas:\n    Login:\n      type: object\n",
        encoding="utf-8",
    )
    protective_test.write_text(
        "# protective scenario\ndef test_mfa_policy():\n    assert True\n", encoding="utf-8"
    )
    harness.hook("Stop", "turn-2")
    assert MemoryStore(harness.root).load_all()[0].status == "active"

    harness.hook("UserPromptSubmit", "turn-3", prompt="Change evidence")
    config.write_text("mfa:\n  required: false\n", encoding="utf-8")
    schema.write_text(
        "openapi: 3.1.0\ncomponents:\n  schemas:\n    Login:\n      type: string\n",
        encoding="utf-8",
    )
    protective_test.write_text("def test_mfa_policy():\n    assert False\n", encoding="utf-8")
    harness.hook("Stop", "turn-3")

    revision = MemoryStore(harness.root).load_all()[0]
    assert revision.status == "stale"
    assert revision.stale_reasons == {
        "config:settings.yaml#/mfa/required": "changed",
        "schema:openapi.yaml#/components/schemas/Login": "changed",
        "test:test_policy.py:test_mfa_policy": "changed",
    }


def test_capture_rejects_an_invalid_evidence_item_atomically(tmp_path: Path) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    source = harness.root / "app.py"
    source.write_text("def login():\n    return False\n", encoding="utf-8")
    harness.git("add", "app.py")
    harness.git("commit", "--quiet", "-m", "baseline")
    harness.hook("UserPromptSubmit", "turn-1", prompt="Change app.py:login")
    source.write_text("def login():\n    return True\n", encoding="utf-8")

    rejected = harness.capture(
        kind="behavior",
        claim="Login stays enabled.",
        evidence=[
            {"type": "symbol", "role": "primary", "locator": "app.py:login"},
            {"type": "config", "role": "supporting", "locator": "missing.yaml#/enabled"},
        ],
        durability_reason="A missing source cannot support a durable claim.",
    )

    result = cast(dict[str, object], rejected["result"])
    assert result["isError"] is True
    message = cast(list[dict[str, str]], result["content"])[0]["text"]
    assert "evidence[1]" in message
    harness.hook("Stop", "turn-1")
    assert MemoryStore(harness.root).load_all() == []


def test_transitive_evidence_dependency_marks_claim_stale_with_provenance_path(
    tmp_path: Path,
) -> None:
    harness = PluginHarness(tmp_path / "repo", PLUGIN_ROOT)
    login = harness.root / "auth.py"
    policy = harness.root / "policy.py"
    mfa = harness.root / "mfa.py"
    login.write_text("def login():\n    return False\n", encoding="utf-8")
    policy.write_text("def authentication_policy():\n    return True\n", encoding="utf-8")
    mfa.write_text("def mfa_policy():\n    return True\n", encoding="utf-8")
    harness.git("add", "auth.py", "policy.py", "mfa.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change auth.py:login")
    login.write_text("def login():\n    return authentication_policy()\n", encoding="utf-8")
    captured = harness.capture(
        kind="behavior",
        claim="Login follows the transitive MFA policy.",
        evidence=[
            {
                "type": "symbol",
                "role": "primary",
                "locator": "auth.py:login",
                "depends_on": [
                    {
                        "type": "symbol",
                        "locator": "policy.py:authentication_policy",
                        "depends_on": [{"type": "symbol", "locator": "mfa.py:mfa_policy"}],
                    }
                ],
            }
        ],
        durability_reason="Login policy depends on the MFA policy.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change mfa.py:mfa_policy")
    mfa.write_text("def mfa_policy():\n    return False\n", encoding="utf-8")
    harness.hook("Stop", "turn-2")

    revision = MemoryStore(harness.root).load_all()[0]
    assert revision.status == "stale"
    assert revision.stale_reasons == {
        "symbol:mfa.py:mfa_policy": (
            "changed via symbol:auth.py:login -> symbol:policy.py:authentication_policy "
            "-> symbol:mfa.py:mfa_policy"
        )
    }


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
        evidence=[{"type": "symbol", "role": "primary", "locator": "service.py:compute"}],
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
        evidence=[{"type": "symbol", "role": "primary", "locator": "service.py:compute"}],
        durability_reason="Callers rely on the result.",
    )
    assert cast(dict[str, object], recaptured["result"])["isError"] is False
    harness.hook("Stop", "turn-3")

    revisions = MemoryStore(harness.root).load_all()
    assert len(revisions) == 2
    assert {revision.status for revision in revisions} == {"active", "stale"}
    assert len({revision.id for revision in revisions}) == 2
    assert len({revision.claim_id for revision in revisions}) == 1
    assert {revision.schema_version for revision in revisions} == {4}
    assert all(revision.observed_commit for revision in revisions)

    context = harness.hook("UserPromptSubmit", "turn-4", prompt="service.py:compute")
    assert context is not None
    additional_context = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert str(additional_context).count("Compute has an established result.") == 1

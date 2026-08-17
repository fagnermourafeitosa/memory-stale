import json
from pathlib import Path
from typing import cast

import pytest
import yaml
from local_harness import LocalHarness

from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer

RUNTIME_ROOT = Path(__file__).parents[1]


def test_stop_persists_an_okf_memory_claim(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "jobs.py"
    source.write_text("def retry() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", "jobs.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update retry")
    source.write_text("def retry() -> int:\n    return 2\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    memory_file = next(MemoryStore(harness.root).directory.glob("*.md"))
    _opening, front_matter, body = memory_file.read_text(encoding="utf-8").split("---", 2)
    document = cast(dict[str, object], yaml.safe_load(front_matter))
    generated = cast(dict[str, object], document["generated"])
    verified = cast(list[dict[str, object]], document["verified"])
    extension = cast(dict[str, object], document["memory_stale"])
    evidence = cast(list[dict[str, object]], extension["evidence"])

    assert document["type"] == "Memory Stale Claim"
    assert document["title"] == "Automatic change record: changed symbol jobs.py:retry."
    assert document["description"] == (
        "Keeps the current implementation of jobs.py:retry available for exact-symbol retrieval."
    )
    assert document["sources"] == [{"id": "symbol:jobs.py:retry", "resource": "jobs.py:retry"}]
    assert generated == verified[0]
    assert document["status"] == "stable"
    assert document["memory_stale"] == {
        "schema_version": 5,
        "claim_id": extension["claim_id"],
        "revision_id": extension["revision_id"],
        "kind": "operation",
        "status": "active",
        "durability_reason": (
            "Keeps the current implementation of jobs.py:retry available for exact-symbol retrieval."
        ),
        "evidence": [
            {
                "source_id": "symbol:jobs.py:retry",
                "type": "symbol",
                "role": "primary",
                "fingerprint": evidence[0]["fingerprint"],
            }
        ],
        "supported_by": ["symbol:jobs.py:retry"],
        "dependencies": [],
        "dependency_extractor_version": "static-v1",
        "dependency_expansion_complete": True,
        "stale_reasons": None,
        "observed_commit": None,
        "observed_at": generated["at"],
        "legacy_id": None,
    }
    assert body == "\n\nAutomatic change record: changed symbol jobs.py:retry.\n"


def test_stop_ignores_a_semantic_change_inside_the_installed_agents_runtime(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    installed_runtime = harness.root / ".agents" / "skills" / "memory-stale" / "runtime.py"
    installed_runtime.parent.mkdir(parents=True)
    installed_runtime.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", ".agents/skills/memory-stale/runtime.py")
    harness.git("commit", "--quiet", "-m", "install runtime")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update the installed runtime")
    installed_runtime.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")
    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {}
    assert MemoryStore(harness.root).load_all() == []


def test_stop_ignores_agents_paths_left_in_a_legacy_task_baseline(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    relative_path = ".agents/skills/memory-stale/runtime.py"
    installed_runtime = harness.root / relative_path
    installed_runtime.parent.mkdir(parents=True)
    installed_runtime.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", relative_path)
    harness.git("commit", "--quiet", "-m", "install runtime")
    signature = SymbolIndexer(harness.root).signature(f"{relative_path}:run")
    store = MemoryStore(harness.root)
    store.write_all(
        [
            Memory(
                "installed-runtime",
                "behavior",
                "active",
                "Installed runtime returns one.",
                "The hook depends on this behavior.",
                (EvidenceItem("symbol", "primary", f"{relative_path}:run", signature),),
            )
        ]
    )

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update the installed runtime")
    task_path = next((harness.root / ".git" / "memory-stale" / "tasks").glob("*.json"))
    state = cast(dict[str, object], json.loads(task_path.read_text(encoding="utf-8")))
    baseline = cast(dict[str, object], state["baseline"])
    baseline[relative_path] = {"status": "  ", "sha256": "legacy-snapshot"}
    task_path.write_text(json.dumps(state), encoding="utf-8")
    installed_runtime.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")

    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {}
    assert store.load_all()[0].status == "active"


def test_stop_captures_project_code_but_ignores_agents_code_in_the_same_turn(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    service = harness.root / "service.py"
    service.write_text("def compute() -> int:\n    return 1\n", encoding="utf-8")
    installed_runtime = harness.root / ".agents" / "skills" / "memory-stale" / "runtime.py"
    installed_runtime.parent.mkdir(parents=True)
    installed_runtime.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py", ".agents/skills/memory-stale/runtime.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update project and runtime")
    service.write_text("def compute() -> int:\n    return 2\n", encoding="utf-8")
    installed_runtime.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")
    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {
        "systemMessage": (
            "Memory Stale semantic capture missing for changed locations: "
            "service.py:compute. Automatic provenance was stored."
        )
    }
    memories = MemoryStore(harness.root).load_all()
    assert [memory.claim for memory in memories] == [
        "Automatic change record: changed symbol service.py:compute."
    ]


@pytest.mark.parametrize("relative_path", [".agents-cache/tool.py", "src/.agents/tool.py"])
def test_stop_does_not_ignore_paths_that_only_resemble_the_agents_root(
    tmp_path: Path, relative_path: str
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / relative_path
    source.parent.mkdir(parents=True)
    source.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", relative_path)
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update tool")
    source.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    memories = MemoryStore(harness.root).load_all()
    assert [memory.evidence[0].locator for memory in memories] == [f"{relative_path}:run"]


def test_stop_automatically_persists_an_added_symbol(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "app" / "main.py"
    source.parent.mkdir()
    source.write_text("def health() -> str:\n    return 'ok'\n", encoding="utf-8")
    harness.git("add", "app/main.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Add the version endpoint")
    source.write_text(
        "def health() -> str:\n    return 'ok'\n\n\ndef version() -> str:\n    return '1.0'\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-1")

    memories = MemoryStore(harness.root).load_all()
    assert len(memories) == 1
    assert memories[0].kind == "operation"
    assert memories[0].status == "active"
    assert memories[0].claim == "Automatic change record: added symbol app/main.py:version."
    assert memories[0].evidence[0].type == "symbol"
    assert memories[0].evidence[0].locator == "app/main.py:version"


def test_stop_reports_changed_locations_without_semantic_descriptions(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def compute() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change compute")
    source.write_text("def compute() -> int:\n    return 2\n", encoding="utf-8")
    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {
        "systemMessage": (
            "Memory Stale semantic capture missing for changed locations: "
            "service.py:compute. Automatic provenance was stored."
        )
    }
    memories = MemoryStore(harness.root).load_all()
    assert [memory.claim for memory in memories] == [
        "Automatic change record: changed symbol service.py:compute."
    ]


def test_stop_automatically_captures_code_outside_a_function(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "settings.py"
    source.write_text("DEFAULT_TIMEOUT = 5\n", encoding="utf-8")
    harness.git("add", "settings.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change the default timeout")
    source.write_text("DEFAULT_TIMEOUT = 10\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    memories = MemoryStore(harness.root).load_all()
    assert len(memories) == 1
    assert memories[0].claim == "Automatic change record: settings.py changed in this task."
    assert memories[0].evidence[0].type == "source"
    assert memories[0].evidence[0].locator == "settings.py"


def test_stop_does_not_write_an_html_report_even_when_auto_report_is_enabled(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def health() -> str:\n    return 'ok'\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")
    config_directory = harness.root / ".agents" / "skills" / ".agent-memory"
    config_directory.mkdir(parents=True)
    (config_directory / "config.toml").write_text(
        'auto_report = true\nreport_path = "health/memory.html"\n', encoding="utf-8"
    )

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change health")
    source.write_text("def health() -> str:\n    return 'ready'\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    assert not (harness.root / "health" / "memory.html").exists()
    assert MemoryStore(harness.root).load_all()


def test_stop_ignores_configuration_and_markdown_changes(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    config = harness.root / "settings.yaml"
    readme = harness.root / "README.md"
    config.write_text("limit: 5\n", encoding="utf-8")
    readme.write_text("# Project\n", encoding="utf-8")
    harness.git("add", "settings.yaml", "README.md")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Update documentation and configuration")
    config.write_text("limit: 10\n", encoding="utf-8")
    readme.write_text("# Project\n\nUpdated.\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    assert MemoryStore(harness.root).load_all() == []


def test_stop_ignores_comment_and_format_only_source_edits(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def compute() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Format service.py")
    source.write_text(
        "# implementation note\n\ndef compute() -> int:\n\n    return 1\n", encoding="utf-8"
    )
    harness.hook("Stop", "turn-1")

    assert MemoryStore(harness.root).load_all() == []


def test_later_source_change_stales_the_prior_automatic_revision(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def compute() -> int:\n    return 1\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change compute")
    source.write_text("def compute() -> int:\n    return 2\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change compute again")
    source.write_text("def compute() -> int:\n    return 3\n", encoding="utf-8")
    harness.hook("Stop", "turn-2")

    memories = MemoryStore(harness.root).load_all()
    assert sorted(memory.status for memory in memories) == ["active", "stale"]
    assert {memory.claim for memory in memories} == {
        "Automatic change record: changed symbol service.py:compute."
    }


def test_full_context_capture_lifecycle_and_persistence_flow(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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
    manual_revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Compute returns two."
    )
    assert manual_revision.status == "active"

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
    manual_revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Compute returns two."
    )
    assert manual_revision.status == "stale"

    final_context = harness.hook("UserPromptSubmit", "turn-3", prompt="Modify service.py:compute")
    assert final_context is not None
    final_specific = cast(dict[str, object], final_context["hookSpecificOutput"])
    assert "Automatic change record: changed symbol service.py:compute." in str(
        final_specific["additionalContext"]
    )


def test_semantic_description_and_automatic_provenance_are_both_persisted_and_retrieved(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    service = harness.root / "checkout.py"
    protective_test = harness.root / "test_checkout.py"
    service.write_text(
        "def subtotal() -> int:\n    return 10\n\n\ndef discount() -> int:\n    return 0\n",
        encoding="utf-8",
    )
    protective_test.write_text(
        "def test_checkout_discount() -> None:\n    assert True\n", encoding="utf-8"
    )
    harness.git("add", "checkout.py", "test_checkout.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement the checkout discount policy")
    service.write_text(
        "def subtotal() -> int:\n    return 20\n\n\ndef discount() -> int:\n    return 5\n",
        encoding="utf-8",
    )
    protective_test.write_text(
        "def test_checkout_discount() -> None:\n    assert 20 - 5 == 15\n", encoding="utf-8"
    )
    captured = harness.capture(
        kind="behavior",
        claim="Checkout applies a five-unit discount to the current subtotal.",
        evidence=[
            {"type": "symbol", "role": "primary", "locator": "checkout.py:subtotal"},
            {"type": "symbol", "role": "primary", "locator": "checkout.py:discount"},
            {
                "type": "test",
                "role": "supporting",
                "locator": "test_checkout.py:test_checkout_discount",
            },
        ],
        durability_reason="Future checkout changes must preserve the discount policy.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False
    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {}

    memories = MemoryStore(harness.root).load_all()
    assert {memory.claim for memory in memories} == {
        "Checkout applies a five-unit discount to the current subtotal.",
        "Automatic change record: changed symbol checkout.py:discount.",
        "Automatic change record: changed symbol checkout.py:subtotal.",
        "Automatic change record: changed symbol test_checkout.py:test_checkout_discount.",
    }

    context = harness.hook(
        "UserPromptSubmit",
        "turn-2",
        prompt="How does the current checkout policy calculate totals?",
    )
    assert context is not None
    additional = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert "Checkout applies a five-unit discount to the current subtotal." in str(additional)


def test_declared_retrieval_term_recovers_an_active_semantic_claim(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "auth.py"
    source.write_text("def login() -> bool:\n    return True\n", encoding="utf-8")
    harness.git("add", "auth.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Require another login factor")
    source.write_text("def login() -> bool:\n    return verify_second_factor()\n", encoding="utf-8")
    captured = harness.capture(
        kind="behavior",
        claim="Login verifies a second factor before granting access.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "auth.py:login"}],
        durability_reason="Authentication must preserve the extra verification step.",
        retrieval_terms=["velociraptor"],
    )

    assert cast(dict[str, object], captured["result"])["isError"] is False
    harness.hook("Stop", "turn-1")

    term_only_context = harness.hook("UserPromptSubmit", "turn-2", prompt="velociraptor")

    assert term_only_context is not None
    term_only_additional = cast(dict[str, object], term_only_context["hookSpecificOutput"])[
        "additionalContext"
    ]
    assert "Login verifies a second factor before granting access." not in str(term_only_additional)

    corroborated_context = harness.hook("UserPromptSubmit", "turn-3", prompt="velociraptor login")

    assert corroborated_context is not None
    corroborated_additional = cast(dict[str, object], corroborated_context["hookSpecificOutput"])[
        "additionalContext"
    ]
    assert "Login verifies a second factor before granting access." in str(corroborated_additional)


def test_partial_semantic_capture_reports_only_the_uncovered_location(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text(
        "def first() -> int:\n    return 1\n\n\ndef second() -> int:\n    return 2\n",
        encoding="utf-8",
    )
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change both calculations")
    source.write_text(
        "def first() -> int:\n    return 10\n\n\ndef second() -> int:\n    return 20\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="The first calculation now returns ten.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "service.py:first"}],
        durability_reason="Callers rely on the first calculation result.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False

    stopped = harness.hook("Stop", "turn-1")

    assert stopped == {
        "systemMessage": (
            "Memory Stale semantic capture missing for changed locations: "
            "service.py:second. Automatic provenance was stored."
        )
    }
    assert {memory.claim for memory in MemoryStore(harness.root).load_all()} == {
        "The first calculation now returns ten.",
        "Automatic change record: changed symbol service.py:first.",
        "Automatic change record: changed symbol service.py:second.",
    }


def test_supporting_symbol_evidence_invalidates_a_captured_claim(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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

    revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the MFA policy."
    )
    assert revision.status == "stale"
    assert revision.stale_reasons == {"symbol:policy.py:mfa_required": "changed"}


def test_typed_config_schema_and_test_evidence_ignore_formatting_then_stale(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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
    revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the configured MFA schema and protective test."
    )
    assert revision.status == "active"

    harness.hook("UserPromptSubmit", "turn-3", prompt="Change evidence")
    config.write_text("mfa:\n  required: false\n", encoding="utf-8")
    schema.write_text(
        "openapi: 3.1.0\ncomponents:\n  schemas:\n    Login:\n      type: string\n",
        encoding="utf-8",
    )
    protective_test.write_text("def test_mfa_policy():\n    assert False\n", encoding="utf-8")
    harness.hook("Stop", "turn-3")

    revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the configured MFA schema and protective test."
    )
    assert revision.status == "stale"
    assert revision.stale_reasons == {
        "config:settings.yaml#/mfa/required": "changed",
        "schema:openapi.yaml#/components/schemas/Login": "changed",
        "test:test_policy.py:test_mfa_policy": "changed",
    }


def test_capture_rejects_an_invalid_evidence_item_atomically(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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
    memories = MemoryStore(harness.root).load_all()
    assert len(memories) == 1
    assert memories[0].claim == "Automatic change record: changed symbol app.py:login."


def test_stop_records_each_changed_symbol_in_one_source_file(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text(
        "def health() -> str:\n    return 'ok'\n\n\ndef version() -> str:\n    return '1.0'\n",
        encoding="utf-8",
    )
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change health and version")
    source.write_text(
        "def health() -> str:\n    return 'ready'\n\n\ndef version() -> str:\n    return '2.0'\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-1")

    memories = MemoryStore(harness.root).load_all()
    assert {memory.claim for memory in memories} == {
        "Automatic change record: changed symbol service.py:health.",
        "Automatic change record: changed symbol service.py:version.",
    }
    assert {memory.evidence[0].locator for memory in memories} == {
        "service.py:health",
        "service.py:version",
    }


def test_stop_does_not_replace_a_deleted_symbol_with_a_source_record(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def health() -> str:\n    return 'ok'\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Add version")
    source.write_text(
        "def health() -> str:\n    return 'ok'\n\n\ndef version() -> str:\n    return '1.0'\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-1")

    harness.hook("UserPromptSubmit", "turn-2", prompt="Remove version")
    source.write_text("def health() -> str:\n    return 'ok'\n", encoding="utf-8")
    harness.hook("Stop", "turn-2")

    memories = MemoryStore(harness.root).load_all()
    assert len(memories) == 1
    assert memories[0].status == "stale"
    assert memories[0].claim == "Automatic change record: added symbol service.py:version."


def test_stop_uses_source_record_for_a_legacy_task_without_symbol_snapshot(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text("def health() -> str:\n    return 'ok'\n", encoding="utf-8")
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Change health")
    task_path = next((harness.root / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task = json.loads(task_path.read_text(encoding="utf-8"))
    del task["symbols"]
    task_path.write_text(json.dumps(task), encoding="utf-8")
    source.write_text("def health() -> str:\n    return 'ready'\n", encoding="utf-8")
    harness.hook("Stop", "turn-1")

    memories = MemoryStore(harness.root).load_all()
    assert len(memories) == 1
    assert memories[0].claim == "Automatic change record: service.py changed in this task."
    assert memories[0].evidence[0].type == "source"


def test_transitive_evidence_dependency_marks_claim_stale_with_provenance_path(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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

    revision = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the transitive MFA policy."
    )
    assert revision.status == "stale"
    assert revision.stale_reasons == {
        "symbol:mfa.py:mfa_policy": (
            "changed via symbol:auth.py:login -> symbol:policy.py:authentication_policy "
            "-> symbol:mfa.py:mfa_policy"
        )
    }


def test_static_call_dependency_invalidates_a_claim_about_its_unchanged_caller(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "service.py"
    source.write_text(
        "def allow_login():\n    return True\n\n\ndef login():\n    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "service.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement service.py:login")
    source.write_text(
        "def allow_login():\n    return True\n\n\ndef login():\n    return allow_login()\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Login follows the repository access policy.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "service.py:login"}],
        durability_reason="The login result is delegated to the access policy.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    active = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the repository access policy."
    )
    assert [
        (edge.source, edge.target, edge.relationship, edge.origin) for edge in active.dependencies
    ] == [("symbol:service.py:login", "symbol:service.py:allow_login", "calls", "static")]

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change service.py:allow_login")
    source.write_text(
        "def allow_login():\n    return False\n\n\ndef login():\n    return allow_login()\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-2")

    stale = next(
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Login follows the repository access policy."
    )
    assert stale.status == "stale"
    assert stale.stale_reasons == {
        "symbol:service.py:allow_login": (
            "changed via symbol:service.py:login -[calls]-> symbol:service.py:allow_login"
        )
    }

    context = harness.hook("UserPromptSubmit", "turn-3", prompt="Review service.py:login")
    assert context is not None
    additional = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert "Login follows the repository access policy." not in str(additional)


def test_static_import_tracks_only_the_called_repository_symbol(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    app = harness.root / "app.py"
    policy = harness.root / "policy.py"
    app.write_text("def login():\n    return False\n", encoding="utf-8")
    policy.write_text(
        "def allow_login():\n    return True\n\n\ndef audit_label():\n    return 'old'\n",
        encoding="utf-8",
    )
    harness.git("add", "app.py", "policy.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement app.py:login")
    app.write_text(
        "from policy import allow_login as permitted\n\n\ndef login():\n    return permitted()\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Login delegates to the repository policy.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "app.py:login"}],
        durability_reason="The policy result controls login.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    memory = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Login delegates to the repository policy."
    )
    assert [(edge.target, edge.relationship) for edge in memory.dependencies] == [
        ("symbol:policy.py:allow_login", "calls")
    ]

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change the policy audit label")
    policy.write_text(
        "def allow_login():\n    return True\n\n\ndef audit_label():\n    return 'new'\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-2")
    unchanged = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Login delegates to the repository policy."
    )
    assert unchanged.status == "active"

    harness.hook("UserPromptSubmit", "turn-3", prompt="Change policy.py:allow_login")
    policy.write_text(
        "def allow_login():\n    return False\n\n\ndef audit_label():\n    return 'new'\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-3")
    changed = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Login delegates to the repository policy."
    )
    assert changed.status == "stale"


def test_static_named_read_invalidates_a_claim_about_its_unchanged_reader(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "jobs.py"
    source.write_text(
        "MAX_RETRIES = 3\n\n\ndef retry_limit():\n    return 0\n",
        encoding="utf-8",
    )
    harness.git("add", "jobs.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement jobs.py:retry_limit")
    source.write_text(
        "MAX_RETRIES = 3\n\n\ndef retry_limit():\n    return MAX_RETRIES\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Jobs retry at most three times.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "jobs.py:retry_limit"}],
        durability_reason="The retry function reads the repository limit.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    active = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Jobs retry at most three times."
    )
    assert [(edge.target, edge.relationship) for edge in active.dependencies] == [
        ("symbol:jobs.py:MAX_RETRIES", "reads")
    ]

    harness.hook("UserPromptSubmit", "turn-2", prompt="Raise MAX_RETRIES")
    source.write_text(
        "MAX_RETRIES = 5\n\n\ndef retry_limit():\n    return MAX_RETRIES\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-2")

    stale = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Jobs retry at most three times."
    )
    assert stale.status == "stale"
    assert stale.stale_reasons == {
        "symbol:jobs.py:MAX_RETRIES": (
            "changed via symbol:jobs.py:retry_limit -[reads]-> symbol:jobs.py:MAX_RETRIES"
        )
    }


def test_declared_code_dependency_is_also_expanded_statically(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "auth.py"
    source.write_text(
        "def rule():\n    return True\n\n\ndef policy():\n    return rule()\n\n\ndef login():\n"
        "    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "auth.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement auth.py:login")
    source.write_text(
        "def rule():\n    return True\n\n\ndef policy():\n    return rule()\n\n\ndef login():\n"
        "    return True\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Login follows the declared policy and its static rule.",
        evidence=[
            {
                "type": "symbol",
                "role": "primary",
                "locator": "auth.py:login",
                "depends_on": [{"type": "symbol", "locator": "auth.py:policy"}],
            }
        ],
        durability_reason="The declared policy delegates to the repository rule.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    active = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Login follows the declared policy and its static rule."
    )
    assert [
        (edge.source, edge.target, edge.relationship, edge.origin) for edge in active.dependencies
    ] == [
        ("symbol:auth.py:login", "symbol:auth.py:policy", "depends_on", "declared"),
        ("symbol:auth.py:policy", "symbol:auth.py:rule", "calls", "static"),
    ]


def test_automatic_symbol_record_tracks_its_static_dependencies(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "access.py"
    source.write_text(
        "def policy():\n    return True\n\n\ndef login():\n    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "access.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement access.py:login")
    source.write_text(
        "def policy():\n    return True\n\n\ndef login():\n    return policy()\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-1")

    automatic = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Automatic change record: changed symbol access.py:login."
    )
    assert [(edge.target, edge.relationship) for edge in automatic.dependencies] == [
        ("symbol:access.py:policy", "calls")
    ]

    harness.hook("UserPromptSubmit", "turn-2", prompt="Change access.py:policy")
    source.write_text(
        "def policy():\n    return False\n\n\ndef login():\n    return policy()\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-2")

    automatic = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Automatic change record: changed symbol access.py:login."
    )
    assert automatic.status == "stale"


def test_static_dependency_expansion_reports_its_depth_bound(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "chain.py"
    source.write_text(
        "def fourth():\n    return True\n\n\ndef third():\n    return fourth()\n\n\ndef second():\n"
        "    return third()\n\n\ndef first():\n    return second()\n\n\ndef entry():\n    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "chain.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement chain.py:entry")
    source.write_text(
        "def fourth():\n    return True\n\n\ndef third():\n    return fourth()\n\n\ndef second():\n"
        "    return third()\n\n\ndef first():\n    return second()\n\n\ndef entry():\n    return first()\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Entry follows the bounded repository chain.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "chain.py:entry"}],
        durability_reason="The entry result is delegated through repository functions.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    memory = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Entry follows the bounded repository chain."
    )
    assert memory.dependency_extractor_version == "static-v1"
    assert memory.dependency_expansion_complete is False
    assert {item.locator for item in memory.evidence} == {
        "chain.py:entry",
        "chain.py:first",
        "chain.py:second",
        "chain.py:third",
    }


def test_static_dependency_expansion_reports_its_node_bound(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "fanout.py"
    dependencies = "\n\n".join(
        f"def dependency_{index}():\n    return {index}" for index in range(70)
    )
    source.write_text(f"{dependencies}\n\n\ndef entry():\n    return 0\n", encoding="utf-8")
    harness.git("add", "fanout.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement fanout.py:entry")
    calls = ", ".join(f"dependency_{index}()" for index in range(70))
    source.write_text(
        f"{dependencies}\n\n\ndef entry():\n    return ({calls})\n",
        encoding="utf-8",
    )
    captured = harness.capture(
        kind="behavior",
        claim="Entry aggregates the repository dependency fanout.",
        evidence=[{"type": "symbol", "role": "primary", "locator": "fanout.py:entry"}],
        durability_reason="The aggregate reads a bounded dependency set.",
    )
    assert cast(dict[str, object], captured["result"])["isError"] is False, captured
    harness.hook("Stop", "turn-1")

    memory = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Entry aggregates the repository dependency fanout."
    )
    assert memory.dependency_expansion_complete is False
    assert len(memory.evidence) == 64


def test_static_dependency_cycle_is_finite_and_complete(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "cycle.py"
    source.write_text(
        "def policy():\n    return login()\n\n\ndef login():\n    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "cycle.py")
    harness.git("commit", "--quiet", "-m", "baseline")

    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement cycle.py:login")
    source.write_text(
        "def policy():\n    return login()\n\n\ndef login():\n    return policy()\n",
        encoding="utf-8",
    )
    harness.hook("Stop", "turn-1")

    memory = next(
        item
        for item in MemoryStore(harness.root).load_all()
        if item.claim == "Automatic change record: changed symbol cycle.py:login."
    )
    assert memory.dependency_expansion_complete is True
    assert [(edge.source, edge.target, edge.relationship) for edge in memory.dependencies] == [
        ("symbol:cycle.py:login", "symbol:cycle.py:policy", "calls"),
        ("symbol:cycle.py:policy", "symbol:cycle.py:login", "calls"),
    ]


def test_repeated_static_graph_capture_is_idempotent(tmp_path: Path) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
    source = harness.root / "idempotent.py"
    source.write_text(
        "def policy():\n    return True\n\n\ndef login():\n    return False\n",
        encoding="utf-8",
    )
    harness.git("add", "idempotent.py")
    harness.git("commit", "--quiet", "-m", "baseline")
    harness.hook("UserPromptSubmit", "turn-1", prompt="Implement idempotent.py:login")
    source.write_text(
        "def policy():\n    return True\n\n\ndef login():\n    return policy()\n",
        encoding="utf-8",
    )
    arguments = {
        "kind": "behavior",
        "claim": "Login follows the idempotent policy.",
        "evidence": [{"type": "symbol", "role": "primary", "locator": "idempotent.py:login"}],
        "durability_reason": "The policy result controls login.",
    }

    first = harness.capture(**arguments)
    duplicate = harness.capture(**arguments)

    first_result = cast(dict[str, object], first["result"])
    duplicate_result = cast(dict[str, object], duplicate["result"])
    assert first_result["isError"] is False
    assert duplicate_result["isError"] is False
    assert cast(list[dict[str, object]], duplicate_result["content"])[0]["text"] == (
        "Capture already staged for this turn."
    )


def test_recapturing_a_stale_claim_preserves_history_and_restores_active_context(
    tmp_path: Path,
) -> None:
    harness = LocalHarness(tmp_path / "repo", RUNTIME_ROOT)
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

    revisions = [
        memory
        for memory in MemoryStore(harness.root).load_all()
        if memory.claim == "Compute has an established result."
    ]
    assert len(revisions) == 2
    assert {revision.status for revision in revisions} == {"active", "stale"}
    assert len({revision.id for revision in revisions}) == 2
    assert len({revision.claim_id for revision in revisions}) == 1
    assert {revision.schema_version for revision in revisions} == {5}
    assert all(revision.observed_commit for revision in revisions)

    context = harness.hook("UserPromptSubmit", "turn-4", prompt="service.py:compute")
    assert context is not None
    additional_context = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert str(additional_context).count("Compute has an established result.") == 1

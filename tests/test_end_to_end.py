import json
from pathlib import Path
from typing import cast

from local_harness import LocalHarness

from memory_stale.memory_store import MemoryStore

RUNTIME_ROOT = Path(__file__).parents[1]


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
    assert {revision.schema_version for revision in revisions} == {4}
    assert all(revision.observed_commit for revision in revisions)

    context = harness.hook("UserPromptSubmit", "turn-4", prompt="service.py:compute")
    assert context is not None
    additional_context = cast(dict[str, object], context["hookSpecificOutput"])["additionalContext"]
    assert str(additional_context).count("Compute has an established result.") == 1

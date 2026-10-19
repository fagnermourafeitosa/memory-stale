import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer

RUNTIME_ROOT = Path(__file__).parents[1]


def _run_git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _create_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_git(repository, "init", "--quiet")
    _run_git(repository, "config", "user.email", "memory-stale@example.test")
    _run_git(repository, "config", "user.name", "Memory Stale Tests")
    tracked = repository / "tracked.txt"
    tracked.write_text("committed\n", encoding="utf-8")
    _run_git(repository, "add", "tracked.txt")
    _run_git(repository, "commit", "--quiet", "-m", "baseline")
    tracked.write_text("pre-existing\n", encoding="utf-8")
    return repository


def _hook_command(event: str) -> list[str]:
    scripts = {
        "UserPromptSubmit": "user_prompt_submit.py",
        "PostToolUse": "post_tool_use.py",
        "Stop": "stop.py",
    }
    return [
        "sh",
        str(RUNTIME_ROOT / "scripts" / "run-python.sh"),
        str(RUNTIME_ROOT / "hooks" / scripts[event]),
    ]


def _run_hook(
    event: str,
    repository: Path,
    payload: dict[str, object],
    environment_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["MEMORY_STALE_SKIP_SYNC"] = "1"
    environment["MEMORY_STALE_PROJECT_ENVIRONMENT"] = str(RUNTIME_ROOT / ".venv")
    environment.update(environment_overrides or {})
    return subprocess.run(
        _hook_command(event),
        cwd=repository,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def _only_task(repository: Path) -> dict[str, object]:
    task_files = _task_files(repository)
    assert len(task_files) == 1
    return cast(dict[str, object], json.loads(task_files[0].read_text(encoding="utf-8")))


def _task_files(repository: Path) -> list[Path]:
    return list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))


def test_prompt_hook_snapshots_dirty_workspace_before_returning_context(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(repository),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Change the tracked file",
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "Memory Stale completion requirement:\n"
                "If this task changes supported code, call memory.capture before the final "
                "response once per coherent change. The claim must describe what the resulting "
                "code does or guarantees, and its evidence must cover the relevant changed "
                "locations. Automatic provenance does not replace semantic capture."
            ),
        }
    }
    task = _only_task(repository)
    assert task["turn_id"] == "turn-1"
    baseline = task["baseline"]
    assert isinstance(baseline, dict)
    tracked = baseline["tracked.txt"]
    assert isinstance(tracked, dict)
    assert tracked["status"] == " M"
    assert task["ledger"] == []


def test_prompt_hook_requires_semantic_capture_for_supported_code_changes(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-semantic-capture",
            "cwd": str(repository),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Implement the requested behavior",
        },
    )

    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context == (
        "Memory Stale completion requirement:\n"
        "If this task changes supported code, call memory.capture before the final response "
        "once per coherent change. The claim must describe what the resulting code does or "
        "guarantees, and its evidence must cover the relevant changed locations. Automatic "
        "provenance does not replace semantic capture."
    )


def test_post_tool_hook_appends_write_to_the_turn_ledger(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    prompt_payload: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(repository),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Change the tracked file",
    }
    assert _run_hook("UserPromptSubmit", repository, prompt_payload).returncode == 0

    result = _run_hook(
        "PostToolUse",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(repository),
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_use_id": "tool-1",
            "tool_input": {"command": "*** Begin Patch\n*** End Patch"},
            "tool_response": {"content": "Done"},
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert _only_task(repository)["ledger"] == [
        {
            "tool_name": "apply_patch",
            "tool_use_id": "tool-1",
            "tool_input": {"command": "*** Begin Patch\n*** End Patch"},
        }
    ]


def test_stop_hook_finishes_turn_without_absorbing_pre_existing_changes(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    prompt_payload: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(repository),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Create a task file",
    }
    assert _run_hook("UserPromptSubmit", repository, prompt_payload).returncode == 0
    (repository / "created-during-task.txt").write_text("task change\n", encoding="utf-8")
    post_payload: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(repository),
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_use_id": "tool-1",
        "tool_input": {"command": "create created-during-task.txt"},
        "tool_response": {"content": "Done"},
    }
    assert _run_hook("PostToolUse", repository, post_payload).returncode == 0

    result = _run_hook(
        "Stop",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(repository),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "Created the requested file.",
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}
    assert _task_files(repository) == []
    assert (repository / "tracked.txt").read_text(encoding="utf-8") == "pre-existing\n"
    assert (repository / "created-during-task.txt").read_text(encoding="utf-8") == "task change\n"


def test_prompt_hook_explains_inactive_state_outside_git(tmp_path: Path) -> None:
    result = _run_hook(
        "UserPromptSubmit",
        tmp_path,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(tmp_path),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Work outside Git",
        },
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "systemMessage": "Memory Stale is inactive: cwd is not inside a Git repository."
    }
    assert not (tmp_path / ".git" / "memory-stale").exists()


def test_followup_hooks_do_not_block_when_task_state_is_unavailable(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    common: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "missing-turn",
        "cwd": str(repository),
    }

    post_result = _run_hook(
        "PostToolUse",
        repository,
        {
            **common,
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_use_id": "tool-1",
            "tool_input": {"command": "write a file"},
            "tool_response": {"content": "Done"},
        },
    )
    stop_result = _run_hook(
        "Stop",
        repository,
        {
            **common,
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": None,
        },
    )

    assert post_result.returncode == 0
    assert post_result.stdout == ""
    assert post_result.stderr == ""
    assert stop_result.returncode == 0
    assert json.loads(stop_result.stdout) == {}
    assert stop_result.stderr == ""


def test_followup_hooks_report_corrupt_task_state_without_blocking(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    prompt_payload: dict[str, object] = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(repository),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Change the tracked file",
    }
    assert _run_hook("UserPromptSubmit", repository, prompt_payload).returncode == 0
    task_files = _task_files(repository)
    assert len(task_files) == 1
    task_files[0].write_text("{not valid json", encoding="utf-8")

    post_result = _run_hook(
        "PostToolUse",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(repository),
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_use_id": "tool-1",
            "tool_input": {"command": "write a file"},
            "tool_response": {"content": "Done"},
        },
    )
    stop_result = _run_hook(
        "Stop",
        repository,
        {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": str(repository),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": None,
        },
    )

    assert post_result.returncode == 0
    assert post_result.stderr == ""
    post_message = json.loads(post_result.stdout)["systemMessage"]
    assert post_message.startswith("Memory Stale PostToolUse failed: JSONDecodeError:")
    assert stop_result.returncode == 0
    assert stop_result.stderr == ""
    stop_message = json.loads(stop_result.stdout)["systemMessage"]
    assert stop_message.startswith("Memory Stale Stop failed: JSONDecodeError:")


def test_stop_marks_memory_stale_when_task_changes_its_symbol(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    source = repository / "service.py"
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    _run_git(repository, "add", "service.py")
    _run_git(repository, "commit", "--quiet", "-m", "add service")
    signature = SymbolIndexer(repository).signature("service.py:compute")
    store = MemoryStore(repository)
    store.write_all(
        [
            Memory(
                "memory-1",
                "behavior",
                "active",
                "Compute returns one.",
                "Callers rely on it.",
                (EvidenceItem("symbol", "primary", "service.py:compute", signature),),
            )
        ]
    )
    assert (
        _run_hook(
            "UserPromptSubmit", repository, {"turn_id": "turn-2", "cwd": str(repository)}
        ).returncode
        == 0
    )
    source.write_text("def compute():\n    return 2\n", encoding="utf-8")

    result = _run_hook("Stop", repository, {"turn_id": "turn-2", "cwd": str(repository)})

    assert result.returncode == 0
    revision = next(memory for memory in store.load_all() if memory.claim == "Compute returns one.")
    assert revision.status == "stale"
    assert revision.stale_reasons == {"symbol:service.py:compute": "changed"}


def test_stop_preserves_legacy_structural_fingerprints_until_real_change(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    source = repository / "service.py"
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    _run_git(repository, "add", "service.py")
    _run_git(repository, "commit", "--quiet", "-m", "add service")
    indexer = SymbolIndexer(repository)
    legacy_signature = indexer.legacy_signature("service.py:compute")
    store = MemoryStore(repository)
    store.write_all(
        [
            Memory(
                "memory-legacy",
                "behavior",
                "active",
                "Compute returns one.",
                "Callers rely on it.",
                (EvidenceItem("symbol", "primary", "service.py:compute", legacy_signature),),
            )
        ]
    )

    _run_hook("UserPromptSubmit", repository, {"turn_id": "turn-1", "cwd": str(repository)})
    source.write_text("# note\ndef compute():\n    return 1\n", encoding="utf-8")
    _run_hook("Stop", repository, {"turn_id": "turn-1", "cwd": str(repository)})

    revision = next(memory for memory in store.load_all() if memory.claim == "Compute returns one.")
    assert revision.status == "active"

    _run_hook("UserPromptSubmit", repository, {"turn_id": "turn-2", "cwd": str(repository)})
    source.write_text("def compute():\n    return 2\n", encoding="utf-8")
    _run_hook("Stop", repository, {"turn_id": "turn-2", "cwd": str(repository)})

    revision = next(memory for memory in store.load_all() if memory.claim == "Compute returns one.")
    assert revision.status == "stale"


def test_read_only_turn_preserves_active_memory_for_preexisting_dirty_symbol(
    tmp_path: Path,
) -> None:
    repository = _create_repository(tmp_path)
    source = repository / "service.py"
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    _run_git(repository, "add", "service.py")
    _run_git(repository, "commit", "--quiet", "-m", "add service")
    source.write_text("def compute():\n    return 2\n", encoding="utf-8")
    signature = SymbolIndexer(repository).signature("service.py:compute")
    store = MemoryStore(repository)
    store.write_all(
        [
            Memory(
                "memory-old",
                "behavior",
                "stale",
                "Compute returns one.",
                "Historical behavior.",
                (EvidenceItem("symbol", "primary", "service.py:compute", "old-signature"),),
                {"symbol:service.py:compute": "changed"},
            ),
            Memory(
                "memory-1",
                "behavior",
                "active",
                "Compute returns two.",
                "Callers rely on it.",
                (EvidenceItem("symbol", "primary", "service.py:compute", signature),),
            ),
        ]
    )

    prompt = _run_hook(
        "UserPromptSubmit",
        repository,
        {"turn_id": "turn-read-only", "cwd": str(repository), "prompt": "service.py:compute"},
    )
    stopped = _run_hook("Stop", repository, {"turn_id": "turn-read-only", "cwd": str(repository)})

    assert prompt.returncode == 0
    assert (
        "Compute returns two."
        in json.loads(prompt.stdout)["hookSpecificOutput"]["additionalContext"]
    )
    assert stopped.returncode == 0
    memories = {memory.id: memory for memory in store.load_all()}
    assert memories["memory-old"].status == "stale"
    assert memories["memory-1"].status == "active"
    assert memories["memory-1"].stale_reasons is None


def test_prompt_hook_injects_only_relevant_active_memory(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    MemoryStore(repository).write_all(
        [
            Memory(
                "memory-1",
                "constraint",
                "active",
                "Auth changes require review.",
                "Security boundary.",
                (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
            )
        ]
    )

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {"turn_id": "turn-context", "cwd": str(repository), "prompt": "Change auth.py:login"},
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "Auth changes require review." in output["hookSpecificOutput"]["additionalContext"]


def test_prompt_hook_applies_the_project_top_k_setting(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    MemoryStore(repository).write_all(
        [
            Memory(
                "a-first",
                "behavior",
                "active",
                "First login behavior.",
                "Security boundary.",
                (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
            ),
            Memory(
                "b-second",
                "behavior",
                "active",
                "Second login behavior.",
                "Security boundary.",
                (EvidenceItem("symbol", "primary", "auth.py:login", "sig"),),
            ),
        ]
    )
    config_directory = repository / ".agents" / "skills" / ".agent-memory"
    config_directory.mkdir(parents=True, exist_ok=True)
    (config_directory / "config.toml").write_text("top_k = 1\n", encoding="utf-8")

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {"turn_id": "turn-context", "cwd": str(repository), "prompt": "Change auth.py:login"},
    )

    assert result.returncode == 0
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "First login behavior." in context
    assert "Second login behavior." not in context


def test_prompt_hook_injects_memory_found_through_locator_vocabulary(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    MemoryStore(repository).write_all(
        [
            Memory(
                "memory-1",
                "behavior",
                "active",
                "Credentials renew after successful authorization.",
                "Existing clients depend on uninterrupted renewal.",
                (
                    EvidenceItem(
                        "symbol",
                        "primary",
                        "src/security/session.py:rotate_token",
                        "sig",
                    ),
                ),
            )
        ]
    )

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {
            "turn_id": "turn-context",
            "cwd": str(repository),
            "prompt": "Adjust session token handling",
        },
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert (
        "Credentials renew after successful authorization."
        in output["hookSpecificOutput"]["additionalContext"]
    )


def _git_logging_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    real_git = shutil.which("git")
    assert real_git is not None
    shim_directory = tmp_path / "git-shim"
    shim_directory.mkdir()
    log = tmp_path / "git-invocations.log"
    log.touch()
    shim = shim_directory / "git"
    shim.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return {"PATH": f"{shim_directory}{os.pathsep}{os.environ['PATH']}"}, log


def _create_repository_with_modules(tmp_path: Path, module_count: int) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = _create_repository(tmp_path)
    for index in range(module_count):
        (repository / f"module_{index}.py").write_text(
            f"def compute_{index}():\n    return {index}\n", encoding="utf-8"
        )
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "--quiet", "-m", "add modules")
    return repository


def _prompt_hook_git_invocations(tmp_path: Path, module_count: int) -> int:
    repository = _create_repository_with_modules(tmp_path, module_count)
    environment, log = _git_logging_environment(tmp_path)

    result = _run_hook(
        "UserPromptSubmit",
        repository,
        {"turn_id": "turn-latency", "cwd": str(repository), "prompt": "compute"},
        environment,
    )

    assert result.returncode == 0, result.stderr
    return len(log.read_text(encoding="utf-8").splitlines())


def test_prompt_hook_git_invocations_do_not_grow_with_repository_size(tmp_path: Path) -> None:
    small = _prompt_hook_git_invocations(tmp_path / "small", 3)
    large = _prompt_hook_git_invocations(tmp_path / "large", 30)

    assert small == large
    assert large <= 5


def _stop_hook_git_invocations(tmp_path: Path, module_count: int) -> int:
    repository = _create_repository_with_modules(tmp_path, module_count)
    prompt = _run_hook(
        "UserPromptSubmit",
        repository,
        {"turn_id": "turn-latency", "cwd": str(repository), "prompt": "compute"},
    )
    assert prompt.returncode == 0, prompt.stderr
    (repository / "module_0.py").write_text("def compute_0():\n    return 100\n", encoding="utf-8")
    environment, log = _git_logging_environment(tmp_path)

    result = _run_hook(
        "Stop", repository, {"turn_id": "turn-latency", "cwd": str(repository)}, environment
    )

    assert result.returncode == 0, result.stderr
    return len(log.read_text(encoding="utf-8").splitlines())


def test_stop_hook_git_invocations_do_not_grow_with_repository_size(tmp_path: Path) -> None:
    small = _stop_hook_git_invocations(tmp_path / "small", 3)
    large = _stop_hook_git_invocations(tmp_path / "large", 30)

    assert small == large
    assert large <= 5


def test_stop_reresolves_only_memories_whose_evidence_files_changed(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    (repository / "service.py").write_text("def compute():\n    return 1\n", encoding="utf-8")
    (repository / "billing.py").write_text("def charge():\n    return 5\n", encoding="utf-8")
    _run_git(repository, "add", "service.py", "billing.py")
    _run_git(repository, "commit", "--quiet", "-m", "add modules")
    compute_signature = SymbolIndexer(repository).signature("service.py:compute")
    store = MemoryStore(repository)
    store.write_all(
        [
            Memory(
                "memory-compute",
                "behavior",
                "active",
                "Compute returns one.",
                "Callers rely on it.",
                (EvidenceItem("symbol", "primary", "service.py:compute", compute_signature),),
            ),
            Memory(
                "memory-charge",
                "behavior",
                "active",
                "Charge returns five.",
                "Billing relies on it.",
                (EvidenceItem("symbol", "primary", "billing.py:charge", "stored-fingerprint"),),
            ),
        ]
    )
    _run_hook("UserPromptSubmit", repository, {"turn_id": "turn-1", "cwd": str(repository)})
    (repository / "service.py").write_text("def compute():\n    return 2\n", encoding="utf-8")

    result = _run_hook("Stop", repository, {"turn_id": "turn-1", "cwd": str(repository)})

    assert result.returncode == 0, result.stderr
    memories = {memory.id: memory for memory in store.load_all()}
    assert memories["memory-compute"].status == "stale"
    assert memories["memory-compute"].stale_reasons == {"symbol:service.py:compute": "changed"}
    assert memories["memory-charge"].status == "active"
    assert memories["memory-charge"].evidence[0].fingerprint == "stored-fingerprint"


def test_prompt_hook_attributes_a_staged_rename_to_its_destination(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    # Read as a status entry, this source path would claim the status of tracked.txt.
    (repository / "zz tracked.txt").write_text("keep\n", encoding="utf-8")
    _run_git(repository, "add", "zz tracked.txt")
    _run_git(repository, "commit", "--quiet", "-m", "add notes")
    _run_git(repository, "mv", "zz tracked.txt", "zzz.txt")

    result = _run_hook(
        "UserPromptSubmit", repository, {"turn_id": "turn-1", "cwd": str(repository)}
    )

    assert result.returncode == 0, result.stderr
    baseline = _only_task(repository)["baseline"]
    assert isinstance(baseline, dict)
    assert "zz tracked.txt" not in baseline
    assert baseline["zzz.txt"] == {
        "status": "R ",
        "sha256": "f660a7996deacfbc7560e4240054a8ad82eb02fe25a95064257e07084bcacb85",
    }
    assert baseline["tracked.txt"]["status"] == " M"

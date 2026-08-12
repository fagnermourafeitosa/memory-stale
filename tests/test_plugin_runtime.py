import json
import os
import subprocess
from pathlib import Path
from typing import cast

from memory_stale.lifecycle import Memory
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer

PLUGIN_ROOT = Path(__file__).parents[1]


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


def _hook_command(event: str) -> str:
    config = cast(
        dict[str, object],
        json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")),
    )
    hooks = config["hooks"]
    assert isinstance(hooks, dict)
    groups = hooks[event]
    assert isinstance(groups, list)
    group = groups[0]
    assert isinstance(group, dict)
    handlers = group["hooks"]
    assert isinstance(handlers, list)
    handler = handlers[0]
    assert isinstance(handler, dict)
    command = handler["command"]
    assert isinstance(command, str)
    return command


def _run_hook(
    event: str, repository: Path, payload: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    environment["PLUGIN_DATA"] = str(PLUGIN_ROOT)
    return subprocess.run(
        _hook_command(event),
        cwd=repository,
        env=environment,
        input=json.dumps(payload),
        shell=True,
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
            "additionalContext": "",
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
                {"service.py:compute": signature},
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
    assert store.load_all()[0].status == "stale"
    assert store.load_all()[0].stale_reasons == {"service.py:compute": "changed"}


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
                {"auth.py:login": "sig"},
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

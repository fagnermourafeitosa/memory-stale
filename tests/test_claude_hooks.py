import io
import json
import subprocess
from pathlib import Path

from memory_stale.claude_adapter import (
    run_post_tool_use,
    run_stop,
    run_user_prompt_submit,
)
from memory_stale.codex_adapter import run_stop as run_codex_stop
from memory_stale.codex_adapter import run_user_prompt_submit as run_codex_user_prompt_submit
from memory_stale.memory_store import MemoryStore


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    return repository


def _claude_payload(repository: Path, event: str, **fields: object) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "prompt_id": "prompt-1",
        "cwd": str(repository),
        "hook_event_name": event,
        **fields,
    }


def _run(function: object, payload: dict[str, object]) -> dict[str, object]:
    output = io.StringIO()
    exit_code = function(io.StringIO(json.dumps(payload)), output)  # type: ignore[operator]
    assert exit_code == 0
    return json.loads(output.getvalue()) if output.getvalue() else {}


def test_claude_prompt_injects_shared_memory_context(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    output = io.StringIO()

    exit_code = run_user_prompt_submit(
        io.StringIO(
            json.dumps(
                {
                    "session_id": "session-1",
                    "prompt_id": "prompt-1",
                    "cwd": str(repository),
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Update authentication",
                }
            )
        ),
        output,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "Memory Stale completion requirement:\n"
                "If this task changes supported code, call memory.capture before the final response "
                "once per coherent change. The claim must describe what the resulting code does or "
                "guarantees, and its evidence must cover the relevant changed locations. Automatic "
                "provenance does not replace semantic capture."
            ),
        }
    }
    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    assert len(task_files) == 1
    assert json.loads(task_files[0].read_text(encoding="utf-8"))["turn_id"] == (
        "claude:session-1:prompt-1:main"
    )


def test_claude_post_tool_use_records_the_shared_task_ledger(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _run(
        run_user_prompt_submit, _claude_payload(repository, "UserPromptSubmit", prompt="Change app")
    )

    response = _run(
        run_post_tool_use,
        _claude_payload(
            repository,
            "PostToolUse",
            tool_name="Write",
            tool_use_id="tool-7",
            tool_input={"file_path": "app.py", "content": "new"},
            tool_response={"ignored": True},
        ),
    )

    assert response == {}
    task_path = next((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    assert json.loads(task_path.read_text(encoding="utf-8"))["ledger"] == [
        {
            "tool_name": "Write",
            "tool_use_id": "tool-7",
            "tool_input": {"file_path": "app.py", "content": "new"},
        }
    ]


def test_claude_stop_reconciles_with_the_shared_lifecycle(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "service.py"
    source.write_text("def enabled() -> bool:\n    return False\n", encoding="utf-8")
    _run(
        run_user_prompt_submit,
        _claude_payload(repository, "UserPromptSubmit", prompt="Enable service"),
    )
    source.write_text("def enabled() -> bool:\n    return True\n", encoding="utf-8")

    response = _run(run_stop, _claude_payload(repository, "Stop"))

    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                "Memory Stale semantic capture missing for changed locations: service.py:enabled. "
                "Automatic provenance was stored."
            ),
        }
    }
    assert [memory.claim for memory in MemoryStore(repository).load_all()] == [
        "Automatic change record: changed symbol service.py:enabled."
    ]


def test_claude_prompt_ids_are_isolated_within_one_session(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _run(
        run_user_prompt_submit,
        _claude_payload(repository, "UserPromptSubmit", prompt_id="prompt-1", prompt="First"),
    )
    _run(
        run_user_prompt_submit,
        _claude_payload(repository, "UserPromptSubmit", prompt_id="prompt-2", prompt="Second"),
    )

    turns = {
        json.loads(path.read_text(encoding="utf-8"))["turn_id"]
        for path in (repository / ".git" / "memory-stale" / "tasks").glob("*.json")
    }

    assert turns == {"claude:session-1:prompt-1:main", "claude:session-1:prompt-2:main"}


def test_claude_subagent_task_is_isolated_from_the_main_agent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _run(run_user_prompt_submit, _claude_payload(repository, "UserPromptSubmit", prompt="Main"))
    _run(
        run_user_prompt_submit,
        _claude_payload(repository, "UserPromptSubmit", prompt="Subagent", agent_id="agent-2"),
    )

    turns = {
        json.loads(path.read_text(encoding="utf-8"))["turn_id"]
        for path in (repository / ".git" / "memory-stale" / "tasks").glob("*.json")
    }

    assert turns == {"claude:session-1:prompt-1:main", "claude:session-1:prompt-1:agent-2"}


def test_claude_missing_prompt_id_skips_lifecycle_work_without_a_message(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    response = _run(
        run_user_prompt_submit,
        {
            "session_id": "session-1",
            "cwd": str(repository),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "No prompt identity",
        },
    )

    assert response == {}
    assert not (repository / ".git" / "memory-stale" / "tasks").exists()


def test_claude_malformed_payload_and_non_git_directory_are_non_blocking(tmp_path: Path) -> None:
    malformed = _run(
        run_user_prompt_submit,
        {"prompt_id": "prompt-1", "cwd": str(tmp_path), "hook_event_name": "UserPromptSubmit"},
    )
    outside_repository = _run(
        run_user_prompt_submit,
        _claude_payload(tmp_path, "UserPromptSubmit", prompt="No repository"),
    )

    malformed_message = malformed["systemMessage"]
    assert isinstance(malformed_message, str)
    assert "session_id must be a non-empty string" in malformed_message
    assert outside_repository == {
        "systemMessage": "Memory Stale is inactive: cwd is not inside a Git repository."
    }


def test_claude_active_stop_does_not_reconcile_or_delete_the_task(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _run(run_user_prompt_submit, _claude_payload(repository, "UserPromptSubmit", prompt="Work"))

    response = _run(run_stop, _claude_payload(repository, "Stop", stop_hook_active=True))

    assert response == {}
    assert len(list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))) == 1


def test_claude_and_codex_reconcile_an_equivalent_change_identically(tmp_path: Path) -> None:
    codex_repository = _repository(tmp_path / "codex")
    claude_repository = _repository(tmp_path / "claude")
    for repository in (codex_repository, claude_repository):
        (repository / "jobs.py").write_text("def retry() -> int:\n    return 1\n", encoding="utf-8")

    _run(
        run_codex_user_prompt_submit,
        {"turn_id": "codex-turn", "cwd": str(codex_repository), "prompt": "Update retry"},
    )
    _run(
        run_user_prompt_submit,
        _claude_payload(claude_repository, "UserPromptSubmit", prompt="Update retry"),
    )
    for repository in (codex_repository, claude_repository):
        (repository / "jobs.py").write_text("def retry() -> int:\n    return 2\n", encoding="utf-8")

    _run(run_codex_stop, {"turn_id": "codex-turn", "cwd": str(codex_repository)})
    _run(run_stop, _claude_payload(claude_repository, "Stop"))

    assert [memory.claim for memory in MemoryStore(codex_repository).load_all()] == [
        memory.claim for memory in MemoryStore(claude_repository).load_all()
    ]

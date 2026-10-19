"""Non-blocking hook contract shared by the Claude, Codex, and Antigravity adapters."""

import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import pytest

from memory_stale import antigravity_adapter, claude_adapter, codex_adapter

Hook = Callable[[TextIO, TextIO], int]
CONFIG = Path(".agents/skills/.agent-memory/config.toml")
INACTIVE = {"systemMessage": "Memory Stale is inactive: cwd is not inside a Git repository."}


def _repository(tmp_path: Path, name: str = "repo") -> Path:
    repository = tmp_path / name
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    return repository


def _outside(tmp_path: Path) -> Path:
    directory = tmp_path / "plain"
    directory.mkdir()
    return directory


def _invoke(hook: Hook, payload: object) -> str:
    output = io.StringIO()
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    assert hook(io.StringIO(raw), output) == 0
    return output.getvalue()


def _json(hook: Hook, payload: object) -> dict[str, object]:
    text = _invoke(hook, payload)
    assert text.endswith("\n")
    return json.loads(text)  # type: ignore[no-any-return]


def _tasks(repository: Path) -> list[Path]:
    return sorted((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))


def _corrupt_only_task(repository: Path) -> None:
    [task] = _tasks(repository)
    task.write_text("not json", encoding="utf-8")


def _break_config(repository: Path) -> None:
    path = repository / CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("context_budget = 0\n", encoding="utf-8")


# Claude Code ---------------------------------------------------------------------------


def _claude(cwd: Path, event: str, **fields: object) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "prompt_id": "prompt-1",
        "cwd": str(cwd),
        "hook_event_name": event,
        **fields,
    }


@pytest.mark.parametrize(
    ("hook", "event", "expected"),
    [
        (
            claude_adapter.run_user_prompt_submit,
            "Stop",
            "Memory Stale UserPromptSubmit failed: ValueError: "
            "hook_event_name must be UserPromptSubmit",
        ),
        (
            claude_adapter.run_post_tool_use,
            "UserPromptSubmit",
            "Memory Stale PostToolUse failed: ValueError: hook_event_name must be PostToolUse",
        ),
    ],
    ids=["prompt", "post-tool"],
)
def test_claude_rejects_a_payload_for_another_event(
    tmp_path: Path, hook: Hook, event: str, expected: str
) -> None:
    repository = _repository(tmp_path)

    assert _json(hook, _claude(repository, event, prompt="x")) == {"systemMessage": expected}
    assert _tasks(repository) == []


def test_claude_reports_an_empty_subagent_id_instead_of_merging_tasks(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    response = _json(
        claude_adapter.run_user_prompt_submit,
        _claude(repository, "UserPromptSubmit", prompt="Work", agent_id=""),
    )

    assert response == {
        "systemMessage": "Memory Stale UserPromptSubmit failed: ValueError: "
        "agent_id must be a non-empty string when provided"
    }
    assert _tasks(repository) == []


def test_claude_events_without_a_prompt_id_skip_silently(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    post_tool = _claude(repository, "PostToolUse", tool_name="Edit", tool_use_id="t1")
    del post_tool["prompt_id"]
    stop = _claude(repository, "Stop")
    del stop["prompt_id"]

    assert _invoke(claude_adapter.run_post_tool_use, post_tool) == ""
    assert _json(claude_adapter.run_stop, stop) == {}


def test_claude_events_outside_git_stay_silent_after_the_prompt(tmp_path: Path) -> None:
    plain = _outside(tmp_path)

    assert _invoke(
        claude_adapter.run_post_tool_use,
        _claude(plain, "PostToolUse", tool_name="Edit", tool_use_id="t1"),
    ) == ("")
    assert _json(claude_adapter.run_stop, _claude(plain, "Stop")) == {}


def test_claude_reports_internal_failures_without_blocking(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _invoke(
        claude_adapter.run_user_prompt_submit, _claude(repository, "UserPromptSubmit", prompt="x")
    )
    _corrupt_only_task(repository)

    post_tool = _json(
        claude_adapter.run_post_tool_use,
        _claude(repository, "PostToolUse", tool_name="Edit", tool_use_id="t1"),
    )
    stop = _json(claude_adapter.run_stop, _claude(repository, "Stop"))

    assert str(post_tool["systemMessage"]).startswith(
        "Memory Stale PostToolUse failed: JSONDecodeError: "
    )
    assert str(stop["systemMessage"]).startswith("Memory Stale Stop failed: JSONDecodeError: ")


def test_claude_reports_invalid_project_configuration_at_prompt_time(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _break_config(repository)

    response = _json(
        claude_adapter.run_user_prompt_submit, _claude(repository, "UserPromptSubmit", prompt="x")
    )

    assert response == {
        "systemMessage": "Memory Stale UserPromptSubmit failed: ConfigError: "
        "context_budget must be a positive integer"
    }


# Codex ---------------------------------------------------------------------------------


def test_codex_reports_a_missing_turn_id(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    response = _json(codex_adapter.run_user_prompt_submit, {"cwd": str(repository)})

    assert response == {
        "systemMessage": "Memory Stale UserPromptSubmit failed: ValueError: "
        "turn_id must be a non-empty string"
    }
    assert _tasks(repository) == []


def test_codex_events_outside_git_never_block(tmp_path: Path) -> None:
    plain = _outside(tmp_path)
    turn = {"turn_id": "turn-1", "cwd": str(plain)}

    assert _json(codex_adapter.run_user_prompt_submit, turn) == INACTIVE
    assert (
        _invoke(codex_adapter.run_post_tool_use, {**turn, "tool_name": "Edit", "tool_use_id": "t"})
        == ""
    )
    assert _json(codex_adapter.run_stop, turn) == {}


def test_codex_reports_internal_failures_without_blocking(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    turn = {"turn_id": "turn-1", "cwd": str(repository)}
    _invoke(codex_adapter.run_user_prompt_submit, turn)
    _corrupt_only_task(repository)

    post_tool = _json(
        codex_adapter.run_post_tool_use, {**turn, "tool_name": "Edit", "tool_use_id": "t1"}
    )
    stop = _json(codex_adapter.run_stop, turn)

    assert str(post_tool["systemMessage"]).startswith(
        "Memory Stale PostToolUse failed: JSONDecodeError: "
    )
    assert str(stop["systemMessage"]).startswith("Memory Stale Stop failed: JSONDecodeError: ")


# Antigravity ---------------------------------------------------------------------------


def _antigravity(cwd: Path, **fields: object) -> dict[str, object]:
    return {"conversationId": "conversation-1", "workspacePaths": [str(cwd)], **fields}


@pytest.mark.parametrize(
    ("hook", "empty"),
    [
        (antigravity_adapter.run_pre_invocation, {"injectSteps": []}),
        (antigravity_adapter.run_post_tool_use, {}),
        (antigravity_adapter.run_stop, {}),
    ],
    ids=["pre-invocation", "post-tool", "stop"],
)
def test_antigravity_events_outside_git_return_their_empty_response(
    tmp_path: Path, hook: Hook, empty: dict[str, object]
) -> None:
    plain = _outside(tmp_path)

    response = _json(hook, _antigravity(plain, toolCall={"name": "edit", "args": {}}))

    assert response == empty


@pytest.mark.parametrize(
    "tool_call",
    [None, "edit", {"args": {}}, {"name": ""}],
    ids=["missing", "not-an-object", "no-name", "blank-name"],
)
def test_antigravity_partial_tool_events_leave_the_ledger_untouched(
    tmp_path: Path, tool_call: object
) -> None:
    repository = _repository(tmp_path)
    _invoke(antigravity_adapter.run_pre_invocation, _antigravity(repository, prompt="x"))
    [task] = _tasks(repository)
    before = task.read_text(encoding="utf-8")
    payload = _antigravity(repository)
    if tool_call is not None:
        payload["toolCall"] = tool_call

    assert _json(antigravity_adapter.run_post_tool_use, payload) == {}
    assert task.read_text(encoding="utf-8") == before


def test_antigravity_post_tool_without_conversation_is_a_noop(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    response = _json(
        antigravity_adapter.run_post_tool_use,
        {"workspacePaths": [str(repository)], "toolCall": {"name": "edit"}},
    )

    assert response == {}
    assert _tasks(repository) == []


@pytest.mark.parametrize(
    ("hook", "event"),
    [
        (antigravity_adapter.run_pre_invocation, "PreInvocation"),
        (antigravity_adapter.run_post_tool_use, "PostToolUse"),
        (antigravity_adapter.run_stop, "Stop"),
    ],
    ids=["pre-invocation", "post-tool", "stop"],
)
def test_antigravity_reports_malformed_json_without_blocking(hook: Hook, event: str) -> None:
    response = _json(hook, "{not json")

    assert str(response["systemMessage"]).startswith(
        f"Memory Stale {event} failed: JSONDecodeError: "
    )


def test_antigravity_reports_internal_failures_without_blocking(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _invoke(antigravity_adapter.run_pre_invocation, _antigravity(repository, prompt="x"))
    _corrupt_only_task(repository)

    post_tool = _json(
        antigravity_adapter.run_post_tool_use,
        _antigravity(repository, toolCall={"name": "edit", "args": {}}),
    )
    stop = _json(antigravity_adapter.run_stop, _antigravity(repository))

    assert str(post_tool["systemMessage"]).startswith(
        "Memory Stale PostToolUse failed: JSONDecodeError: "
    )
    assert str(stop["systemMessage"]).startswith("Memory Stale Stop failed: JSONDecodeError: ")


def test_antigravity_prefers_the_first_workspace_path_over_cwd(tmp_path: Path) -> None:
    workspace = _repository(tmp_path, "workspace")
    other = _repository(tmp_path, "other")

    _invoke(
        antigravity_adapter.run_pre_invocation,
        {"conversationId": "c", "workspacePaths": [str(workspace)], "cwd": str(other)},
    )

    assert len(_tasks(workspace)) == 1
    assert _tasks(other) == []


def test_antigravity_falls_back_to_cwd_without_workspace_paths(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    _invoke(
        antigravity_adapter.run_pre_invocation,
        {"conversation_id": "c", "workspacePaths": [], "cwd": str(repository)},
    )

    assert len(_tasks(repository)) == 1


def test_antigravity_falls_back_to_the_process_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    monkeypatch.chdir(repository)

    _invoke(antigravity_adapter.run_pre_invocation, {"conversationId": "c", "workspacePaths": [""]})

    assert len(_tasks(repository)) == 1

"""Claude Code lifecycle payload adapter for the shared Memory Stale runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO, cast

from memory_stale.hook_runtime import (
    NotGitRepositoryError,
    finish_task,
    record_tool_activity,
    semantic_capture_missing_message,
    start_task,
)


def _read_payload(stream: TextIO) -> dict[str, object]:
    return cast(dict[str, object], json.load(stream))


def _required_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _turn_id(payload: dict[str, object]) -> str | None:
    session_id = _required_string(payload, "session_id")
    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        return None
    agent_id = payload.get("agent_id")
    if agent_id is not None and (not isinstance(agent_id, str) or not agent_id):
        raise ValueError("agent_id must be a non-empty string when provided")
    return f"claude:{session_id}:{prompt_id}:{agent_id if isinstance(agent_id, str) else 'main'}"


def _write_json(value: dict[str, object], output_stream: TextIO) -> None:
    json.dump(value, output_stream)
    output_stream.write("\n")


def _write_failure(event: str, error: Exception, output_stream: TextIO) -> None:
    _write_json(
        {"systemMessage": f"Memory Stale {event} failed: {type(error).__name__}: {error}"},
        output_stream,
    )


def run_user_prompt_submit(
    input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout
) -> int:
    try:
        payload = _read_payload(input_stream)
        if _required_string(payload, "hook_event_name") != "UserPromptSubmit":
            raise ValueError("hook_event_name must be UserPromptSubmit")
        turn_id = _turn_id(payload)
        if turn_id is None:
            _write_json({}, output_stream)
            return 0
        try:
            context = start_task(
                Path(_required_string(payload, "cwd")),
                turn_id,
                _required_string(payload, "prompt"),
            )
        except NotGitRepositoryError:
            _write_json(
                {"systemMessage": "Memory Stale is inactive: cwd is not inside a Git repository."},
                output_stream,
            )
            return 0
        _write_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            },
            output_stream,
        )
    except Exception as error:
        _write_failure("UserPromptSubmit", error, output_stream)
    return 0


def run_post_tool_use(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    try:
        payload = _read_payload(input_stream)
        if _required_string(payload, "hook_event_name") != "PostToolUse":
            raise ValueError("hook_event_name must be PostToolUse")
        turn_id = _turn_id(payload)
        if turn_id is None:
            return 0
        try:
            record_tool_activity(
                Path(_required_string(payload, "cwd")),
                turn_id,
                _required_string(payload, "tool_name"),
                _required_string(payload, "tool_use_id"),
                payload.get("tool_input"),
            )
        except NotGitRepositoryError:
            return 0
    except Exception as error:
        _write_failure("PostToolUse", error, output_stream)
    return 0


def run_stop(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    try:
        payload = _read_payload(input_stream)
        if payload.get("stop_hook_active") is True:
            _write_json({}, output_stream)
            return 0
        turn_id = _turn_id(payload)
        if turn_id is None:
            _write_json({}, output_stream)
            return 0
        try:
            uncovered = finish_task(Path(_required_string(payload, "cwd")), turn_id)
        except NotGitRepositoryError:
            _write_json({}, output_stream)
            return 0
        response: dict[str, object] = (
            {
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": semantic_capture_missing_message(uncovered),
                }
            }
            if uncovered
            else {}
        )
        _write_json(response, output_stream)
    except Exception as error:
        _write_failure("Stop", error, output_stream)
    return 0

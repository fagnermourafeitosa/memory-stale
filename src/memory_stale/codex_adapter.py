"""Codex lifecycle payload adapter for the shared Memory Stale runtime."""

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


def _write_json(value: dict[str, object], output_stream: TextIO) -> None:
    json.dump(value, output_stream)
    output_stream.write("\n")


def _write_failure(event: str, error: Exception, output_stream: TextIO) -> None:
    _write_json(
        {"systemMessage": f"Memory Stale {event} failed: {type(error).__name__}: {error}"},
        output_stream,
    )


def _coverage_message(uncovered: list[str]) -> dict[str, object]:
    return {"systemMessage": (semantic_capture_missing_message(uncovered))} if uncovered else {}


def run_user_prompt_submit(
    input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout
) -> int:
    try:
        payload = _read_payload(input_stream)
        prompt = payload.get("prompt")
        try:
            context = start_task(
                Path(_required_string(payload, "cwd")),
                _required_string(payload, "turn_id"),
                prompt if isinstance(prompt, str) else "",
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
        try:
            record_tool_activity(
                Path(_required_string(payload, "cwd")),
                _required_string(payload, "turn_id"),
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
        try:
            uncovered = finish_task(
                Path(_required_string(payload, "cwd")), _required_string(payload, "turn_id")
            )
        except NotGitRepositoryError:
            _write_json({}, output_stream)
            return 0
        _write_json(_coverage_message(uncovered or []), output_stream)
    except Exception as error:
        _write_failure("Stop", error, output_stream)
    return 0

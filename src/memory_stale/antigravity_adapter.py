"""Antigravity lifecycle payload adapter for the shared Memory Stale runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO, cast

from memory_stale.hook_runtime import (
    NotGitRepositoryError,
    finish_task,
    record_tool_activity,
    start_task,
)


def _read_payload(stream: TextIO) -> dict[str, object]:
    return cast(dict[str, object], json.load(stream))


def _resolve_repository(payload: dict[str, object]) -> Path:
    workspace_paths = payload.get("workspacePaths")
    if isinstance(workspace_paths, list) and workspace_paths:
        first = workspace_paths[0]
        if isinstance(first, str) and first:
            return Path(first)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def _turn_id(payload: dict[str, object]) -> str | None:
    conversation_id = payload.get("conversationId") or payload.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    return f"antigravity:{conversation_id}"


def _write_json(value: dict[str, object], output_stream: TextIO) -> None:
    json.dump(value, output_stream)
    output_stream.write("\n")


def _write_failure(event: str, error: Exception, output_stream: TextIO) -> None:
    _write_json(
        {"systemMessage": f"Memory Stale {event} failed: {type(error).__name__}: {error}"},
        output_stream,
    )


def run_pre_invocation(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _turn_id(payload)
        if turn_id is None:
            _write_json({"injectSteps": []}, output_stream)
            return 0
        prompt = (
            payload.get("prompt") or payload.get("userPrompt") or payload.get("user_prompt") or ""
        )
        prompt_text = prompt if isinstance(prompt, str) else ""
        repository = _resolve_repository(payload)
        try:
            context = start_task(repository, turn_id, prompt_text)
        except NotGitRepositoryError:
            _write_json({"injectSteps": []}, output_stream)
            return 0
        _write_json(
            {
                "injectSteps": [
                    {
                        "ephemeralMessage": context,
                    }
                ]
            },
            output_stream,
        )
    except Exception as error:
        _write_failure("PreInvocation", error, output_stream)
    return 0


def run_post_tool_use(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _turn_id(payload)
        if turn_id is None:
            _write_json({}, output_stream)
            return 0
        tool_call = payload.get("toolCall")
        if not isinstance(tool_call, dict):
            _write_json({}, output_stream)
            return 0
        tool_name = tool_call.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            _write_json({}, output_stream)
            return 0
        step_idx = payload.get("stepIdx", 0)
        tool_use_id = f"step-{step_idx}"
        tool_input = tool_call.get("args")
        repository = _resolve_repository(payload)
        try:
            record_tool_activity(repository, turn_id, tool_name, tool_use_id, tool_input)
        except NotGitRepositoryError:
            _write_json({}, output_stream)
            return 0
        _write_json({}, output_stream)
    except Exception as error:
        _write_failure("PostToolUse", error, output_stream)
    return 0


def run_stop(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _turn_id(payload)
        if turn_id is None:
            _write_json({}, output_stream)
            return 0
        repository = _resolve_repository(payload)
        try:
            finish_task(repository, turn_id)
        except NotGitRepositoryError:
            _write_json({}, output_stream)
            return 0
        _write_json({}, output_stream)
    except Exception as error:
        _write_failure("Stop", error, output_stream)
    return 0

"""Thin adapters for Codex lifecycle hooks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO, TypedDict, cast


class FileSnapshot(TypedDict):
    status: str
    sha256: str | None


class LedgerEntry(TypedDict):
    tool_name: str
    tool_use_id: str
    tool_input: object


class TaskState(TypedDict):
    turn_id: str
    repository: str
    baseline: dict[str, FileSnapshot]
    ledger: list[LedgerEntry]
    captures: list[object]


class ChangedPath(TypedDict):
    path: str
    before: FileSnapshot | None
    after: FileSnapshot | None


class NotGitRepositoryError(RuntimeError):
    """Raised when a hook runs outside a Git working tree."""


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _repository_root(cwd: Path) -> Path:
    try:
        root = _git(cwd, "rev-parse", "--show-toplevel").strip()
    except subprocess.CalledProcessError as error:
        raise NotGitRepositoryError from error
    return Path(root).resolve()


def _task_directory(repository: Path) -> Path:
    git_directory = Path(_git(repository, "rev-parse", "--absolute-git-dir").strip())
    return git_directory / "memory-stale" / "tasks"


def _file_status(repository: Path, relative_path: str) -> str:
    status = _git(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        relative_path,
    )
    return status[:2] if status else "  "


def _snapshot(repository: Path) -> dict[str, FileSnapshot]:
    paths = _git(
        repository,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    ).split("\0")
    snapshot: dict[str, FileSnapshot] = {}
    for relative_path in paths:
        if not relative_path:
            continue
        path = repository / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        snapshot[relative_path] = {
            "status": _file_status(repository, relative_path),
            "sha256": digest,
        }
    return snapshot


def _atomic_json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _task_path(repository: Path, turn_id: str) -> Path:
    task_name = hashlib.sha256(turn_id.encode("utf-8")).hexdigest()
    return _task_directory(repository) / f"{task_name}.json"


def _read_task(path: Path) -> TaskState:
    return cast(TaskState, json.loads(path.read_text(encoding="utf-8")))


def _changes_since(
    baseline: dict[str, FileSnapshot], current: dict[str, FileSnapshot]
) -> list[ChangedPath]:
    changes: list[ChangedPath] = []
    for path in sorted(baseline.keys() | current.keys()):
        before = baseline.get(path)
        after = current.get(path)
        if before != after:
            changes.append({"path": path, "before": before, "after": after})
    return changes


def _run_lifecycle(
    repository: Path,
    changes: list[ChangedPath],
    _ledger: list[LedgerEntry],
    captures: list[object],
) -> None:
    from memory_stale.lifecycle import RefEvidence, reconcile
    from memory_stale.memory_store import MemoryStore
    from memory_stale.symbol_index import InvalidSyntaxError, SymbolIndexer, SymbolNotFoundError

    store = MemoryStore(repository)
    memories = store.load_all()
    changed_paths = {change["path"] for change in changes}
    indexer = SymbolIndexer(repository)
    evidence: dict[str, RefEvidence] = {}
    for memory in memories:
        for ref, expected in memory.signatures.items():
            path_text = ref.rpartition(":")[0]
            if path_text not in changed_paths:
                evidence[ref] = RefEvidence(expected)
                continue
            try:
                evidence[ref] = RefEvidence(indexer.signature(ref))
            except SymbolNotFoundError as error:
                reason = "file_missing" if "file not found" in str(error) else "symbol_missing"
                evidence[ref] = RefEvidence(None, reason)
            except (InvalidSyntaxError, RuntimeError):
                evidence[ref] = RefEvidence(None, "unresolvable")
    capture_mappings = [
        cast(Mapping[str, object], item) for item in captures if isinstance(item, dict)
    ]
    store.write_all(reconcile(memories, capture_mappings, evidence))


def _read_payload(stream: TextIO) -> dict[str, object]:
    return cast(dict[str, object], json.load(stream))


def _required_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _write_failure(event: str, error: Exception, output_stream: TextIO) -> None:
    json.dump(
        {"systemMessage": (f"Memory Stale {event} failed: {type(error).__name__}: {error}")},
        output_stream,
    )
    output_stream.write("\n")


def run_user_prompt_submit(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _required_string(payload, "turn_id")
        try:
            repository = _repository_root(Path(_required_string(payload, "cwd")))
        except NotGitRepositoryError:
            json.dump(
                {
                    "systemMessage": (
                        "Memory Stale is inactive: cwd is not inside a Git repository."
                    )
                },
                output_stream,
            )
            output_stream.write("\n")
            return 0
        state: TaskState = {
            "turn_id": turn_id,
            "repository": str(repository),
            "baseline": _snapshot(repository),
            "ledger": [],
            "captures": [],
        }
        _atomic_json_write(_task_path(repository, turn_id), state)
        from memory_stale.memory_store import MemoryStore
        from memory_stale.retrieval import retrieve

        prompt = payload.get("prompt")
        context = retrieve(
            MemoryStore(repository).load_all(), prompt if isinstance(prompt, str) else "", 1500
        )
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            },
            output_stream,
        )
        output_stream.write("\n")
    except Exception as error:
        _write_failure("UserPromptSubmit", error, output_stream)
    return 0


def run_post_tool_use(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _required_string(payload, "turn_id")
        try:
            repository = _repository_root(Path(_required_string(payload, "cwd")))
        except NotGitRepositoryError:
            return 0
        task_path = _task_path(repository, turn_id)
        if not task_path.is_file():
            return 0
        state = _read_task(task_path)
        state["ledger"].append(
            {
                "tool_name": _required_string(payload, "tool_name"),
                "tool_use_id": _required_string(payload, "tool_use_id"),
                "tool_input": payload.get("tool_input"),
            }
        )
        _atomic_json_write(task_path, state)
    except Exception as error:
        _write_failure("PostToolUse", error, output_stream)
    return 0


def run_stop(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    try:
        payload = _read_payload(input_stream)
        turn_id = _required_string(payload, "turn_id")
        try:
            repository = _repository_root(Path(_required_string(payload, "cwd")))
        except NotGitRepositoryError:
            json.dump({}, output_stream)
            output_stream.write("\n")
            return 0
        task_path = _task_path(repository, turn_id)
        if not task_path.is_file():
            json.dump({}, output_stream)
            output_stream.write("\n")
            return 0
        state = _read_task(task_path)
        changes = _changes_since(state["baseline"], _snapshot(repository))
        _run_lifecycle(repository, changes, state["ledger"], state["captures"])
        task_path.unlink()
        json.dump({}, output_stream)
        output_stream.write("\n")
    except Exception as error:
        _write_failure("Stop", error, output_stream)
    return 0

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

from memory_stale.evidence import EvidenceError
from memory_stale.symbol_index import SymbolIndexer, SymbolIndexError


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
    sources: dict[str, str]
    symbols: dict[str, dict[str, str]]
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


def _source_snapshot(repository: Path) -> dict[str, str]:
    index = SymbolIndexer(repository)
    sources: dict[str, str] = {}
    for path in _snapshot(repository):
        signature = _source_signature(index, path)
        if signature is not None:
            sources[path] = signature
    return sources


def _source_signature(index: SymbolIndexer, path: str) -> str | None:
    try:
        return index.source_signature(path)
    except SymbolIndexError:
        return None


def _symbol_snapshot(repository: Path) -> dict[str, dict[str, str]]:
    index = SymbolIndexer(repository)
    symbols: dict[str, dict[str, str]] = {}
    for path in _snapshot(repository):
        resolved = _source_symbols(index, path)
        if resolved is not None:
            symbols[path] = resolved
    return symbols


def _source_symbols(index: SymbolIndexer, path: str) -> dict[str, str] | None:
    try:
        return index.source_symbols(path)
    except SymbolIndexError:
        return None


def _automatic_captures(
    baseline: dict[str, str],
    current: dict[str, str],
    baseline_symbols: dict[str, dict[str, str]] | None,
    current_symbols: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    captures: list[dict[str, object]] = []
    for path, fingerprint in sorted(current.items()):
        if baseline.get(path) == fingerprint:
            continue
        previous_symbols = baseline_symbols.get(path, {}) if baseline_symbols is not None else None
        symbols = current_symbols.get(path, {})
        if previous_symbols is not None:
            changed_symbols = [
                (locator, signature, "added" if locator not in previous_symbols else "changed")
                for locator, signature in sorted(symbols.items())
                if previous_symbols.get(locator) != signature
            ]
            for locator, signature, action in changed_symbols:
                captures.append(
                    {
                        "kind": "operation",
                        "claim": f"Automatic change record: {action} symbol {locator}.",
                        "evidence": [
                            {
                                "type": "symbol",
                                "role": "primary",
                                "locator": locator,
                                "fingerprint": signature,
                            }
                        ],
                        "durability_reason": (
                            f"Keeps the current implementation of {locator} available for exact-symbol retrieval."
                        ),
                        "schema_version": 4,
                    }
                )
            if changed_symbols or previous_symbols != symbols:
                continue
        captures.append(
            {
                "kind": "operation",
                "claim": f"Automatic change record: {path} changed in this task.",
                "evidence": [
                    {
                        "type": "source",
                        "role": "primary",
                        "locator": path,
                        "fingerprint": fingerprint,
                    }
                ],
                "durability_reason": (
                    f"Keeps the current implementation of {path} available for exact-path retrieval."
                ),
                "schema_version": 4,
            }
        )
    return captures


def _run_lifecycle(
    repository: Path,
    changes: list[ChangedPath],
    _ledger: list[LedgerEntry],
    captures: list[object],
) -> None:
    from memory_stale.evidence import resolve_stored_item
    from memory_stale.lifecycle import RefEvidence, reconcile
    from memory_stale.memory_store import MemoryStore

    store = MemoryStore(repository)
    memories = store.load_all()
    changed_paths = {change["path"] for change in changes}
    evidence: dict[str, RefEvidence] = {}
    for memory in memories:
        if memory.status != "active":
            continue
        for item in memory.evidence:
            path_text = _evidence_file(item.type, item.locator)
            if path_text not in changed_paths:
                evidence[item.key] = RefEvidence(item.fingerprint)
                continue
            try:
                evidence[item.key] = RefEvidence(resolve_stored_item(repository, item))
            except EvidenceError as error:
                evidence[item.key] = RefEvidence(None, _evidence_error_reason(error))
    capture_mappings = [
        cast(Mapping[str, object], item) for item in captures if isinstance(item, dict)
    ]
    store.write_all(reconcile(memories, capture_mappings, evidence))


def _evidence_file(item_type: str, locator: str) -> str:
    if item_type in {"symbol", "test"}:
        return locator.rpartition(":")[0]
    if item_type in {"config", "schema"}:
        return locator.partition("#")[0]
    return locator


def _evidence_error_reason(error: EvidenceError) -> str:
    message = str(error)
    if "file not found" in message:
        return "file_missing"
    if "locator not found" in message or "symbol not found" in message:
        return "locator_missing"
    return "unresolvable"


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
            "sources": _source_snapshot(repository),
            "symbols": _symbol_snapshot(repository),
            "ledger": [],
            "captures": [],
        }
        _atomic_json_write(_task_path(repository, turn_id), state)
        from memory_stale.memory_store import MemoryStore
        from memory_stale.reporting import load_config
        from memory_stale.retrieval import retrieve

        prompt = payload.get("prompt")
        context = retrieve(
            MemoryStore(repository).load_all(),
            prompt if isinstance(prompt, str) else "",
            load_config(repository).context_budget,
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
        previous_symbols = state.get("symbols")
        symbol_baseline = (
            previous_symbols
            if isinstance(previous_symbols, dict)
            and all(isinstance(value, dict) for value in previous_symbols.values())
            else None
        )
        captures = [
            *state["captures"],
            *_automatic_captures(
                state["sources"],
                _source_snapshot(repository),
                symbol_baseline,
                _symbol_snapshot(repository),
            ),
        ]
        _run_lifecycle(repository, changes, state["ledger"], captures)
        task_path.unlink()
        json.dump({}, output_stream)
        output_stream.write("\n")
    except Exception as error:
        _write_failure("Stop", error, output_stream)
    return 0

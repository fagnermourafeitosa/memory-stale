"""Thin adapters for Codex lifecycle hooks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

from memory_stale.evidence import EvidenceError
from memory_stale.project_paths import evidence_path, is_ignored_project_path
from memory_stale.symbol_index import SymbolIndexer, SymbolIndexError

SEMANTIC_CAPTURE_PROTOCOL = (
    "Memory Stale completion requirement:\n"
    "If this task changes supported code, call memory.capture before the final response "
    "once per coherent change. The claim must describe what the resulting code does or "
    "guarantees, and its evidence must cover the relevant changed locations. Automatic "
    "provenance does not replace semantic capture."
)


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
        if not relative_path or is_ignored_project_path(relative_path):
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
        if is_ignored_project_path(path):
            continue
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
    observed_at = datetime.now(timezone.utc).isoformat()
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
                        "schema_version": 5,
                        "observed_at": observed_at,
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
                "schema_version": 5,
                "observed_at": observed_at,
            }
        )
    return captures


def _uncovered_automatic_locations(
    automatic_captures: list[dict[str, object]], explicit_captures: list[object]
) -> list[str]:
    covered_symbols: set[str] = set()
    covered_paths: set[str] = set()
    for capture in explicit_captures:
        if not isinstance(capture, dict):
            continue
        evidence = capture.get("evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            locator = item.get("locator")
            if not isinstance(item_type, str) or not isinstance(locator, str):
                continue
            covered_paths.add(evidence_path(item_type, locator))
            if item_type in {"symbol", "test"}:
                covered_symbols.add(locator)

    uncovered: set[str] = set()
    for capture in automatic_captures:
        evidence = capture.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != 1:
            continue
        item = evidence[0]
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        locator = item.get("locator")
        if not isinstance(item_type, str) or not isinstance(locator, str):
            continue
        if (item_type == "symbol" and locator not in covered_symbols) or (
            item_type == "source" and locator not in covered_paths
        ):
            uncovered.add(locator)
    return sorted(uncovered)


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
            path_text = evidence_path(item.type, item.locator)
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


def _evidence_error_reason(error: EvidenceError) -> str:
    message = str(error)
    if "file not found" in message:
        return "file_missing"
    if "locator not found" in message or "symbol not found" in message:
        return "locator_missing"
    return "unresolvable"


def start_task(cwd: Path, turn_id: str, prompt: str) -> str:
    """Persist a task baseline and return active memory context for any host."""
    repository = _repository_root(cwd)
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

    context = retrieve(
        MemoryStore(repository).load_all(), prompt, load_config(repository).context_budget
    )
    return f"{SEMANTIC_CAPTURE_PROTOCOL}\n\n{context}" if context else SEMANTIC_CAPTURE_PROTOCOL


def record_tool_activity(
    cwd: Path, turn_id: str, tool_name: str, tool_use_id: str, tool_input: object
) -> None:
    """Append an observed tool invocation to a task without host-specific parsing."""
    repository = _repository_root(cwd)
    task_path = _task_path(repository, turn_id)
    if not task_path.is_file():
        return
    state = _read_task(task_path)
    state["ledger"].append(
        {"tool_name": tool_name, "tool_use_id": tool_use_id, "tool_input": tool_input}
    )
    _atomic_json_write(task_path, state)


def finish_task(cwd: Path, turn_id: str) -> list[str] | None:
    """Reconcile a task and return uncovered automatic locations, if it exists."""
    repository = _repository_root(cwd)
    task_path = _task_path(repository, turn_id)
    if not task_path.is_file():
        return None
    state = _read_task(task_path)
    changes = _changes_since(state["baseline"], _snapshot(repository))
    previous_symbols = state.get("symbols")
    symbol_baseline = (
        previous_symbols
        if isinstance(previous_symbols, dict)
        and all(isinstance(value, dict) for value in previous_symbols.values())
        else None
    )
    automatic_captures = _automatic_captures(
        state["sources"],
        _source_snapshot(repository),
        symbol_baseline,
        _symbol_snapshot(repository),
    )
    uncovered = _uncovered_automatic_locations(automatic_captures, state["captures"])
    _run_lifecycle(repository, changes, state["ledger"], [*state["captures"], *automatic_captures])
    task_path.unlink()
    return uncovered


def semantic_capture_missing_message(uncovered: list[str]) -> str:
    """Render the shared semantic-coverage diagnostic for a host adapter."""
    return (
        "Memory Stale semantic capture missing for changed locations: "
        f"{', '.join(uncovered)}. Automatic provenance was stored."
    )

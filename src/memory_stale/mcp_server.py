"""Local stdio MCP server for Memory Stale."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO, cast

from memory_stale.dream import dream
from memory_stale.evidence import EvidenceError, EvidenceGraph, parse_graph, resolve_item
from memory_stale.hook_runtime import _atomic_json_write, _repository_root, _snapshot
from memory_stale.memory_store import MemoryStore
from memory_stale.reporting import write_report

KINDS = {"behavior", "contract", "constraint", "architecture", "operation"}


def _tool_result(text: str, *, error: bool = False) -> dict[str, object]:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _active_task(repository: Path) -> Path:
    git_dir = Path(
        __import__("subprocess")
        .run(
            ["git", "-C", str(repository), "rev-parse", "--absolute-git-dir"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    tasks = list((git_dir / "memory-stale" / "tasks").glob("*.json"))
    if len(tasks) != 1:
        raise ValueError("memory.capture requires exactly one active turn")
    return tasks[0]


def _string(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _capture(arguments: dict[str, object], cwd: Path) -> dict[str, object]:
    kind = _string(arguments, "kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(sorted(KINDS))}")
    claim = _string(arguments, "claim")
    durability_reason = _string(arguments, "durability_reason")
    graph = parse_graph(arguments.get("evidence"))
    repository = _repository_root(cwd)
    observed_commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    task_path = _active_task(repository)
    task = cast(dict[str, object], json.loads(task_path.read_text(encoding="utf-8")))
    baseline = cast(dict[str, object], task["baseline"])
    current = _snapshot(repository)
    evidence = []
    primary_changed = False
    for index, (item_type, role, locator) in enumerate(graph.items):
        try:
            path_text = _evidence_path(item_type, locator)
            if role == "primary" and baseline.get(path_text) != current.get(path_text):
                primary_changed = True
            item = resolve_item(repository, item_type, role, locator)
        except (EvidenceError, ValueError) as error:
            raise ValueError(f"evidence[{index}]: {error}") from error
        evidence.append(
            {
                "type": item.type,
                "role": item.role,
                "locator": item.locator,
                "fingerprint": item.fingerprint,
            }
        )
    if not primary_changed:
        raise ValueError("at least one primary evidence item must change in this turn")
    candidate = {
        "kind": kind,
        "claim": claim,
        "evidence": evidence,
        "supported_by": list(graph.supported_by),
        "dependencies": [{"from": edge.source, "to": edge.target} for edge in graph.dependencies],
        "durability_reason": durability_reason,
        "schema_version": 4,
        "observed_commit": observed_commit,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    captures = cast(list[object], task.setdefault("captures", []))
    key = (kind, " ".join(claim.casefold().split()), _graph_identity(graph))
    for existing in captures:
        if isinstance(existing, dict):
            existing_key = (
                existing.get("kind"),
                " ".join(str(existing.get("claim", "")).casefold().split()),
                _capture_graph_key(existing),
            )
            if existing_key == key:
                return _tool_result("Capture already staged for this turn.")
    captures.append(candidate)
    _atomic_json_write(task_path, task)
    return _tool_result("Capture staged for lifecycle validation.")


def _capture_graph_key(capture: dict[str, object]) -> tuple[object, ...]:
    graph = parse_graph(capture.get("evidence"))
    return _graph_identity(graph)


def _graph_identity(graph: EvidenceGraph) -> tuple[object, ...]:
    return (tuple(sorted(graph.items)), graph.supported_by, graph.dependencies)


def _evidence_path(item_type: str, locator: str) -> str:
    if item_type in {"symbol", "test"}:
        path_text, separator, _symbol = locator.rpartition(":")
        if not separator or not path_text:
            raise ValueError(f"invalid symbol locator: {locator}")
        return path_text
    path_text, separator, _pointer = locator.partition("#")
    if not separator or not path_text:
        raise ValueError(f"invalid document locator: {locator}")
    return path_text


def _dispatch(request: dict[str, object], cwd: Path) -> dict[str, object] | None:
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        return None
    if method == "initialize":
        result: object = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "memory-stale", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "memory.capture",
                    "description": (
                        "Stage durable code-anchored project memory. Active means "
                        "recorded evidence is unchanged; stale requires revalidation."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "required": ["kind", "claim", "evidence", "durability_reason"],
                        "properties": {
                            "kind": {"type": "string", "enum": sorted(KINDS)},
                            "claim": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["type", "role", "locator"],
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["symbol", "config", "schema", "test"],
                                        },
                                        "role": {
                                            "type": "string",
                                            "enum": ["primary", "supporting"],
                                        },
                                        "locator": {"type": "string"},
                                    },
                                    "additionalProperties": True,
                                },
                            },
                            "durability_reason": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "memory.dream",
                    "description": "Audit project memory whose evidence requires revalidation.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "name": "memory.report",
                    "description": "Generate the project memory HTML report.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            ]
        }
    elif method == "tools/call":
        params = request.get("params")
        if isinstance(params, dict) and params.get("name") == "memory.report":
            repository = _repository_root(cwd)
            path = write_report(repository, MemoryStore(repository).load_all(), requested=True)
            result = _tool_result(f"Report written to {path}")
        elif isinstance(params, dict) and params.get("name") == "memory.dream":
            summary = dream(_repository_root(cwd))
            result = _tool_result(
                json.dumps(
                    {
                        "audited": summary.audited,
                        "marked_stale": summary.marked_stale,
                        "errors": summary.errors,
                    },
                    sort_keys=True,
                )
            )
        elif not isinstance(params, dict) or params.get("name") != "memory.capture":
            result = _tool_result("Unknown tool.", error=True)
        else:
            arguments = params.get("arguments")
            try:
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                result = _capture(cast(dict[str, object], arguments), cwd)
            except Exception as error:
                result = _tool_result(str(error), error=True)
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> int:
    cwd = Path.cwd()
    for line in input_stream:
        request = cast(dict[str, object], json.loads(line))
        response = _dispatch(request, cwd)
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

PLUGIN_ROOT = Path(__file__).parents[1]


def _git(repository: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True)


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.test")
    _git(repository, "config", "user.name", "Test")
    (repository / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    _git(repository, "add", "auth.py")
    _git(repository, "commit", "--quiet", "-m", "baseline")
    return repository


def _start_turn(repository: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PLUGIN_DATA": str(PLUGIN_ROOT / ".venv" / "plugin-test-data"),
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(PLUGIN_ROOT / ".venv"),
        }
    )
    config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    result = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        input=json.dumps({"turn_id": "turn-1", "cwd": str(repository)}),
        shell=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _rpc(server: subprocess.Popen[str], request: dict[str, object]) -> dict[str, object]:
    assert server.stdin is not None
    assert server.stdout is not None
    server.stdin.write(json.dumps(request) + "\n")
    server.stdin.flush()
    return cast(dict[str, object], json.loads(server.stdout.readline()))


def test_capture_stages_candidate_without_persisting_memory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text(
        "def login():\n    return validate_mfa()\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PLUGIN_ROOT / "src")
    server = subprocess.Popen(
        [sys.executable, "-m", "memory_stale.mcp_server"],
        cwd=repository,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        response = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {
                        "kind": "behavior",
                        "claim": "Login validates MFA before creating a session.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Future authentication changes must preserve MFA.",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    assert response["id"] == 1
    result = response["result"]
    assert isinstance(result, dict)
    assert result["isError"] is False
    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task = json.loads(task_files[0].read_text(encoding="utf-8"))
    assert len(task["captures"]) == 1
    capture = task["captures"][0]
    assert capture["kind"] == "behavior"
    assert capture["claim"] == "Login validates MFA before creating a session."
    assert capture["evidence"][0]["locator"] == "auth.py:login"
    assert capture["durability_reason"] == "Future authentication changes must preserve MFA."
    fingerprint = capture["evidence"][0]["fingerprint"]
    assert fingerprint.startswith("v2:")
    assert len(fingerprint) == 67
    assert not (repository / ".agents" / "skills" / ".agent-memory" / "memories").exists()

    environment = os.environ.copy()
    environment.update(
        {
            "PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PLUGIN_DATA": str(PLUGIN_ROOT / ".venv" / "plugin-test-data"),
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(PLUGIN_ROOT / ".venv"),
        }
    )
    config = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    stop_command = config["hooks"]["Stop"][0]["hooks"][0]["command"]
    stopped = subprocess.run(
        stop_command,
        cwd=repository,
        env=environment,
        input=json.dumps({"turn_id": "turn-1", "cwd": str(repository)}),
        shell=True,
        capture_output=True,
        text=True,
    )
    assert stopped.returncode == 0, stopped.stderr
    memories = list((repository / ".agents" / "skills" / ".agent-memory" / "memories").glob("*.md"))
    assert len(memories) == 1
    assert "Login validates MFA before creating a session." in memories[0].read_text(
        encoding="utf-8"
    )


def test_capture_rejects_invalid_or_unchanged_refs_and_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PLUGIN_ROOT / "src")
    server = subprocess.Popen(
        [sys.executable, "-m", "memory_stale.mcp_server"],
        cwd=repository,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_arguments: dict[str, object] = {
        "kind": "behavior",
        "claim": "Login returns whether authentication succeeds.",
        "evidence": [{"type": "symbol", "role": "primary", "locator": "auth.py:login"}],
        "durability_reason": "Callers depend on the boolean contract.",
    }
    try:
        initialized = _rpc(
            server, {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}}
        )
        listed = _rpc(server, {"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}})
        missing = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {"name": "memory.capture", "arguments": {}},
            },
        )
        unknown = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {"name": "other", "arguments": {}},
            },
        )
        unchanged = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "memory.capture", "arguments": base_arguments},
            },
        )
        (repository / "auth.py").write_text("def login():\n    return False\n", encoding="utf-8")
        invalid = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {**base_arguments, "kind": "note"},
                },
            },
        )
        first = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "memory.capture", "arguments": base_arguments},
            },
        )
        duplicate = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {
                        **base_arguments,
                        "claim": "  LOGIN returns whether authentication succeeds. ",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    assert "serverInfo" in cast(dict[str, object], initialized["result"])
    tools = cast(dict[str, object], listed["result"])["tools"]
    assert isinstance(tools, list) and tools[0]["name"] == "memory.capture"
    for response in (missing, unknown, unchanged, invalid):
        result = response["result"]
        assert isinstance(result, dict)
        assert result["isError"] is True
    for response in (first, duplicate):
        result = response["result"]
        assert isinstance(result, dict)
        assert result["isError"] is False
    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task = json.loads(task_files[0].read_text(encoding="utf-8"))
    assert len(task["captures"]) == 1

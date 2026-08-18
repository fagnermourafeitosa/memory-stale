import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

RUNTIME_ROOT = Path(__file__).parents[1]


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
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(RUNTIME_ROOT / ".venv"),
        }
    )
    result = subprocess.run(
        [
            "sh",
            str(RUNTIME_ROOT / "scripts" / "run-python.sh"),
            str(RUNTIME_ROOT / "hooks" / "user_prompt_submit.py"),
        ],
        cwd=repository,
        env=environment,
        input=json.dumps({"turn_id": "turn-1", "cwd": str(repository)}),
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
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "retrieval_terms": ["MFA"],
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
    assert capture["retrieval_terms"] == ["MFA"]
    fingerprint = capture["evidence"][0]["fingerprint"]
    assert fingerprint.startswith("v2:")
    assert len(fingerprint) == 67
    assert not (repository / ".agents" / "skills" / ".agent-memory" / "memories").exists()

    environment = os.environ.copy()
    environment.update(
        {
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(RUNTIME_ROOT / ".venv"),
        }
    )
    stopped = subprocess.run(
        [
            "sh",
            str(RUNTIME_ROOT / "scripts" / "run-python.sh"),
            str(RUNTIME_ROOT / "hooks" / "stop.py"),
        ],
        cwd=repository,
        env=environment,
        input=json.dumps({"turn_id": "turn-1", "cwd": str(repository)}),
        capture_output=True,
        text=True,
    )
    assert stopped.returncode == 0, stopped.stderr
    memories = list((repository / ".agents" / "skills" / ".agent-memory" / "memories").glob("*.md"))
    assert len(memories) == 2
    assert any(
        "Login validates MFA before creating a session." in memory.read_text(encoding="utf-8")
        for memory in memories
    )


def test_capture_rejects_invalid_or_unchanged_refs_and_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
    assert tools[0]["description"] == (
        "Required once per coherent supported-code change. Stage a claim describing what the "
        "resulting code does or guarantees, anchored to typed evidence. Optional retrieval_terms "
        "are host-declared lexical vocabulary, not evidence. Active means recorded evidence is "
        "unchanged; stale requires revalidation."
    )
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


def test_capture_rejects_invalid_retrieval_terms(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text("def login():\n    return False\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
    server = subprocess.Popen(
        [sys.executable, "-m", "memory_stale.mcp_server"],
        cwd=repository,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    arguments: dict[str, object] = {
        "kind": "behavior",
        "claim": "Login returns the authentication result.",
        "evidence": [{"type": "symbol", "role": "primary", "locator": "auth.py:login"}],
        "durability_reason": "Callers depend on the authentication outcome.",
    }
    try:
        responses = [
            _rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "memory.capture",
                        "arguments": {**arguments, "retrieval_terms": ["   "]},
                    },
                },
            ),
            _rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "memory.capture",
                        "arguments": {**arguments, "retrieval_terms": ["MFA", "mfa"]},
                    },
                },
            ),
            _rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "memory.capture",
                        "arguments": {
                            **arguments,
                            "retrieval_terms": [
                                "one",
                                "two",
                                "three",
                                "four",
                                "five",
                                "six",
                                "seven",
                                "eight",
                                "nine",
                            ],
                        },
                    },
                },
            ),
            _rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "memory.capture",
                        "arguments": {**arguments, "retrieval_terms": ["x" * 81]},
                    },
                },
            ),
        ]
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    for response in responses:
        assert cast(dict[str, object], response["result"])["isError"] is True


def test_capture_rejects_source_evidence_reserved_for_automatic_capture(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "kind": "operation",
                        "claim": "Auth source changed.",
                        "evidence": [{"type": "source", "role": "primary", "locator": "auth.py"}],
                        "durability_reason": "The automatic lifecycle owns source evidence.",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    result = response["result"]
    assert isinstance(result, dict)
    assert result["isError"] is True
    content = result["content"]
    assert isinstance(content, list)
    assert content[0]["text"] == "source evidence is reserved for automatic capture"


def test_capture_rejects_evidence_inside_the_agents_directory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    installed_runtime = repository / ".agents" / "skills" / "memory-stale" / "runtime.py"
    installed_runtime.parent.mkdir(parents=True)
    installed_runtime.write_text("def run() -> int:\n    return 1\n", encoding="utf-8")
    _start_turn(repository)
    installed_runtime.write_text("def run() -> int:\n    return 2\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "claim": "The installed runtime returns the current protocol result.",
                        "evidence": [
                            {
                                "type": "symbol",
                                "role": "primary",
                                "locator": ".agents/skills/memory-stale/runtime.py:run",
                            }
                        ],
                        "durability_reason": "The installed hook depends on this behavior.",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    result = cast(dict[str, object], response["result"])
    assert result["isError"] is True
    content = cast(list[dict[str, str]], result["content"])
    assert content[0]["text"] == "evidence inside .agents is ignored"
    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task = json.loads(task_files[0].read_text(encoding="utf-8"))
    assert task["captures"] == []


def test_capture_rejects_reserved_and_locator_only_claims(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text("def login():\n    return False\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "kind": "operation",
                        "claim": "Automatic change record: changed symbol auth.py:login.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Authentication behavior changed.",
                    },
                },
            },
        )
        locator_response = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {
                        "kind": "operation",
                        "claim": "auth.py:login",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Authentication behavior changed.",
                    },
                },
            },
        )
        history_response = _rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {
                        "kind": "operation",
                        "claim": "auth.py changed in this task.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Authentication behavior changed.",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    for rejected in (response, locator_response, history_response):
        result = cast(dict[str, object], rejected["result"])
        assert result["isError"] is True
        content = cast(list[dict[str, str]], result["content"])
        assert (
            content[0]["text"] == "claim must describe what the resulting code does or guarantees"
        )
    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task = json.loads(task_files[0].read_text(encoding="utf-8"))
    assert task["captures"] == []


def test_report_writes_html_only_after_an_explicit_mcp_request(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    config_directory = repository / ".agents" / "skills" / ".agent-memory"
    config_directory.mkdir(parents=True)
    (config_directory / "config.toml").write_text(
        'report_path = "health/memory.html"\n', encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                "params": {"name": "memory.report", "arguments": {}},
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    result = cast(dict[str, object], response["result"])
    assert result["isError"] is False
    assert (repository / "health" / "memory.html").is_file()


def test_capture_with_language_stages_candidate(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text(
        "def login():\n    return validate_mfa()\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "claim": "Autenticação valida segundo fator de segurança.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Segurança exige validação consistente.",
                        "retrieval_terms": ["MFA"],
                        "language": "pt",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    result = cast(dict[str, object], response["result"])
    assert result["isError"] is False
    task_file = next((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task_data = json.loads(task_file.read_text(encoding="utf-8"))
    assert len(task_data["captures"]) == 1
    assert task_data["captures"][0]["language"] == "pt"


def test_capture_records_target_signature_for_inertial_reconciliation(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _start_turn(repository)
    (repository / "auth.py").write_text(
        "def login():\n    return validate_mfa()\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(RUNTIME_ROOT / "src")
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
                        "claim": "Auth login returns boolean success.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "auth.py:login"}
                        ],
                        "durability_reason": "Contract",
                    },
                },
            },
        )
    finally:
        assert server.stdin is not None
        server.stdin.close()
        server.wait(timeout=5)

    result = cast(dict[str, object], response["result"])
    assert result["isError"] is False
    task_file = next((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    task_data = json.loads(task_file.read_text(encoding="utf-8"))
    assert len(task_data["captures"]) == 1
    capture = task_data["captures"][0]
    assert "target_signature" in capture
    assert isinstance(capture["target_signature"], str)
    assert len(capture["target_signature"]) == 64

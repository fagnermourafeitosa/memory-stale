import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

SOURCE_ROOT = Path(__file__).parents[1]


def test_installation_creates_a_project_local_skill_and_hook_configuration(tmp_path: Path) -> None:
    source = tmp_path / "source" / "memory-stale"
    shutil.copytree(
        SOURCE_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".coverage*", ".mypy_cache", ".pytest_cache", ".ruff_cache"
        ),
    )
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)

    installation = subprocess.run(
        ["sh", str(source / "scripts" / "install-project.sh"), str(repository)],
        cwd=source,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 0, installation.stderr
    installed_skill = repository / ".agents" / "skills" / "memory-stale"
    assert (installed_skill / "SKILL.md").is_file()
    assert (installed_skill / "src" / "memory_stale" / "mcp_server.py").is_file()
    assert not (repository / ".codex-plugin").exists()

    hooks = json.loads((repository / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    assert set(hooks["hooks"]) == {"UserPromptSubmit", "PostToolUse", "Stop"}
    mcp = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
    assert set(mcp["mcpServers"]) == {"memory-stale"}

    command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    environment = os.environ.copy()
    payload = json.dumps({"turn_id": "local-install", "cwd": str(repository), "prompt": "test"})
    prompt = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        input=payload,
        shell=True,
        capture_output=True,
        text=True,
    )

    assert prompt.returncode == 0, prompt.stderr
    assert json.loads(prompt.stdout)["hookSpecificOutput"]["additionalContext"] == ""
    runtime = repository / ".git" / "memory-stale" / "runtime"
    assert (runtime / ".venv" / "bin" / "python").is_file()
    assert (runtime / "uv-cache").is_dir()
    assert not (source / ".venv").exists()


def test_installed_local_mcp_and_stop_hook_persist_a_memory_in_the_target_project(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "memory-stale"
    shutil.copytree(
        SOURCE_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".coverage*", ".mypy_cache", ".pytest_cache", ".ruff_cache"
        ),
    )
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "memory-stale@example.test"], cwd=repository, check=True
    )
    subprocess.run(["git", "config", "user.name", "Memory Stale"], cwd=repository, check=True)
    subject = repository / "service.py"
    subject.write_text(
        "def login(password: str) -> bool:\n    return password == 'old'\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "service.py"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=repository, check=True)
    subprocess.run(
        ["sh", str(source / "scripts" / "install-project.sh"), str(repository)],
        cwd=source,
        check=True,
    )
    hooks = json.loads((repository / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    prompt_command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    stop_command = hooks["hooks"]["Stop"][0]["hooks"][0]["command"]
    environment = os.environ.copy()
    prompt_payload = json.dumps({"turn_id": "capture", "cwd": str(repository), "prompt": "login"})
    prompt = subprocess.run(
        prompt_command,
        cwd=repository,
        env=environment,
        input=prompt_payload,
        shell=True,
        capture_output=True,
        text=True,
    )
    assert prompt.returncode == 0, prompt.stderr

    subject.write_text(
        "def login(password: str) -> bool:\n    return password == 'new'\n", encoding="utf-8"
    )
    mcp = cast(
        dict[str, object], json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
    )
    server_config = cast(
        dict[str, object], cast(dict[str, object], mcp["mcpServers"])["memory-stale"]
    )
    arguments = cast(list[str], server_config["args"])
    server = subprocess.Popen(
        [cast(str, server_config["command"]), *arguments],
        cwd=repository,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert server.stdin is not None and server.stdout is not None
    server.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory.capture",
                    "arguments": {
                        "kind": "behavior",
                        "claim": "Login accepts the new password.",
                        "evidence": [
                            {"type": "symbol", "role": "primary", "locator": "service.py:login"}
                        ],
                        "durability_reason": "Authentication behavior affects callers.",
                    },
                },
            }
        )
        + "\n"
    )
    server.stdin.flush()
    response = json.loads(server.stdout.readline())
    server.stdin.close()
    server.wait(timeout=10)
    assert response["result"]["isError"] is False

    stopped = subprocess.run(
        stop_command,
        cwd=repository,
        env=environment,
        input=json.dumps({"turn_id": "capture", "cwd": str(repository)}),
        shell=True,
        capture_output=True,
        text=True,
    )
    assert stopped.returncode == 0, stopped.stderr
    memories = list((repository / ".agents" / "skills" / ".agent-memory" / "memories").glob("*.md"))
    assert len(memories) == 2
    explicit_memory = next(
        memory
        for memory in memories
        if "Login accepts the new password." in memory.read_text(encoding="utf-8")
    )
    assert "status: active" in explicit_memory.read_text(encoding="utf-8")


def test_installation_preserves_unrelated_project_codex_configuration(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    (repository / ".codex").mkdir()
    (repository / ".codex" / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo keep"}]}]}}),
        encoding="utf-8",
    )
    (repository / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"existing": {"command": "existing-command"}}}),
        encoding="utf-8",
    )

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 0, installation.stderr
    hooks = json.loads((repository / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    stop_hooks = hooks["hooks"]["Stop"]
    assert stop_hooks[0]["hooks"][0]["command"] == "echo keep"
    assert len(stop_hooks) == 2
    mcp = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["existing"] == {"command": "existing-command"}
    assert "memory-stale" in mcp["mcpServers"]


def test_installation_rejects_a_conflicting_memory_stale_mcp_server(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    mcp_path = repository / ".mcp.json"
    original = {"mcpServers": {"memory-stale": {"command": "other-server"}}}
    mcp_path.write_text(json.dumps(original), encoding="utf-8")

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 1
    assert "different 'memory-stale' MCP server" in installation.stderr
    assert json.loads(mcp_path.read_text(encoding="utf-8")) == original
    assert not (repository / ".agents" / "skills" / "memory-stale").exists()

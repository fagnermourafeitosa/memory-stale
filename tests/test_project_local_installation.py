import json
import os
import shutil
import subprocess
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1]


def _codex_environment(command_directory: Path, script: str) -> dict[str, str]:
    command_directory.mkdir()
    codex_command = command_directory / "codex"
    codex_command.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    codex_command.chmod(0o755)
    return {**os.environ, "PATH": f"{command_directory}{os.pathsep}{os.environ['PATH']}"}


def test_installation_registers_the_installed_mcp_server_with_codex(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    command_directory = tmp_path / "commands"
    captured_arguments = tmp_path / "codex-arguments"
    environment = {
        **_codex_environment(
            command_directory, 'printf \'%s\\n\' "$@" > "$MEMORY_STALE_CODEX_ARGUMENTS"'
        ),
        "MEMORY_STALE_CODEX_ARGUMENTS": str(captured_arguments),
    }

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 0, installation.stderr
    assert captured_arguments.read_text(encoding="utf-8").splitlines() == [
        "mcp",
        "add",
        "memory-stale",
        "--",
        "sh",
        str(repository / ".agents" / "skills" / "memory-stale" / "scripts" / "run-python.sh"),
        "-m",
        "memory_stale.mcp_server",
    ]


def test_installation_creates_default_durable_memory_configuration(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=_codex_environment(tmp_path / "commands", ":"),
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 0, installation.stderr
    configuration = repository / ".agents" / "skills" / ".agent-memory" / "config.toml"
    assert configuration.read_text(encoding="utf-8") == (
        "# Maximum number of tokens of active memory injected into task context.\n"
        "context_budget = 1500\n\n"
        "# Generate the optional HTML health report after each completed turn.\n"
        "auto_report = false\n\n"
        "# Repository-relative path used when an HTML report is requested.\n"
        'report_path = "memory-report.html"\n'
    )
    assert not (repository / "memory-report.html").exists()


def test_reinstallation_preserves_custom_durable_memory_configuration(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    environment = _codex_environment(tmp_path / "commands", ":")
    command = ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)]

    first_installation = subprocess.run(
        command,
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert first_installation.returncode == 0, first_installation.stderr
    configuration = repository / ".agents" / "skills" / ".agent-memory" / "config.toml"
    configuration.write_text("context_budget = 700\n", encoding="utf-8")

    reinstallation = subprocess.run(
        command,
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert reinstallation.returncode == 0, reinstallation.stderr
    assert configuration.read_text(encoding="utf-8") == "context_budget = 700\n"


def test_installation_reports_a_failed_mcp_registration(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    environment = _codex_environment(
        tmp_path / "commands", "printf '%s\\n' 'registration denied' >&2\nexit 12"
    )

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 1
    assert (
        "could not register the memory-stale MCP server: registration denied" in installation.stderr
    )
    assert "Memory Stale installed locally" not in installation.stdout


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
        env=_codex_environment(tmp_path / "commands", ":"),
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
    claude_settings = json.loads(
        (repository / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert set(claude_settings["hooks"]) == {"UserPromptSubmit", "PostToolUse", "Stop"}
    assert (repository / ".claude" / "skills" / "memory-stale" / "SKILL.md").is_file()
    assert (
        json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][
            "memory-stale"
        ]["command"]
        == "sh"
    )

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
    assert json.loads(prompt.stdout)["hookSpecificOutput"]["additionalContext"] == (
        "Memory Stale completion requirement:\n"
        "If this task changes supported code, call memory.capture before the final response "
        "once per coherent change. The claim must describe what the resulting code does or "
        "guarantees, and its evidence must cover the relevant changed locations. Automatic "
        "provenance does not replace semantic capture."
    )
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
        env=_codex_environment(tmp_path / "commands", ":"),
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
    server = subprocess.Popen(
        [
            "sh",
            str(repository / ".agents" / "skills" / "memory-stale" / "scripts" / "run-python.sh"),
            "-m",
            "memory_stale.mcp_server",
        ],
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
    persisted = explicit_memory.read_text(encoding="utf-8")
    assert "status: stable" in persisted
    assert "memory_stale:" in persisted
    assert "  status: active" in persisted


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
        env=_codex_environment(tmp_path / "commands", ":"),
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
    assert mcp["mcpServers"]["memory-stale"]["command"] == "sh"


def test_installation_rejects_an_incompatible_project_mcp_registration(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    mcp_path = repository / ".mcp.json"
    original = {"mcpServers": {"memory-stale": {"command": "other-server"}}}
    mcp_path.write_text(json.dumps(original), encoding="utf-8")

    installation = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=_codex_environment(tmp_path / "commands", ":"),
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 1
    assert "already registers an incompatible memory-stale server" in installation.stderr
    assert json.loads(mcp_path.read_text(encoding="utf-8")) == original
    assert (repository / ".agents" / "skills" / "memory-stale").exists()


def test_installation_merges_claude_settings_and_is_idempotent(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    settings_path = repository / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(git status)"]},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo keep"}]}]},
            }
        ),
        encoding="utf-8",
    )
    environment = _codex_environment(tmp_path / "commands", ":")

    first = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        ["sh", str(SOURCE_ROOT / "scripts" / "install-project.sh"), str(repository)],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["permissions"] == {"allow": ["Bash(git status)"]}
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo keep"
    assert set(settings["hooks"]) == {"UserPromptSubmit", "PostToolUse", "Stop"}
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1
    assert len(settings["hooks"]["PostToolUse"]) == 1
    assert len(settings["hooks"]["Stop"]) == 2
    mcp = json.loads((repository / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["memory-stale"] == {
        "command": "sh",
        "args": [
            str(repository / ".agents" / "skills" / "memory-stale" / "scripts" / "run-python.sh"),
            "-m",
            "memory_stale.mcp_server",
        ],
    }
    assert (repository / ".claude" / "skills" / "memory-stale" / "SKILL.md").is_file()


def test_claude_only_installation_does_not_invoke_codex(tmp_path: Path) -> None:
    repository = tmp_path / "target"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    environment = _codex_environment(tmp_path / "commands", "exit 99")

    installation = subprocess.run(
        [
            "sh",
            str(SOURCE_ROOT / "scripts" / "install-project.sh"),
            str(repository),
            "--host",
            "claude",
        ],
        cwd=SOURCE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert installation.returncode == 0, installation.stderr
    assert not (repository / ".codex" / "hooks.json").exists()
    assert (repository / ".claude" / "settings.json").is_file()
    assert (repository / ".mcp.json").is_file()

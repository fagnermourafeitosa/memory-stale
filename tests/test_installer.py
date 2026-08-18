import json
import subprocess
from pathlib import Path

from scripts.install_project import install, main


def _create_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "-C", str(repository), "init", "--quiet"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
    return repository


def test_installer_cli_requires_harness_argument(tmp_path: Path, capsys: object) -> None:
    repository = _create_repository(tmp_path)
    source = Path(__file__).parents[1]

    exit_code = main([str(source), str(repository)])
    assert exit_code == 2

    exit_code_legacy_host = main([str(source), str(repository), "--host", "codex"])
    assert exit_code_legacy_host == 2

    exit_code_invalid = main([str(source), str(repository), "--harness", "all"])
    assert exit_code_invalid == 2


def test_installer_configures_antigravity_artifacts(tmp_path: Path) -> None:
    repository = _create_repository(tmp_path)
    source = Path(__file__).parents[1]

    install(source, repository, "antigravity")

    # Verify skill and runtime copied
    skill_file = repository / ".agents" / "skills" / "memory-stale" / "SKILL.md"
    assert skill_file.exists()
    assert (repository / ".agents" / "skills" / ".agent-memory" / "config.toml").exists()

    # Verify .agents/hooks.json
    hooks_file = repository / ".agents" / "hooks.json"
    assert hooks_file.exists()
    hooks_config = json.loads(hooks_file.read_text(encoding="utf-8"))
    assert "memory-stale" in hooks_config
    agent_hooks = hooks_config["memory-stale"]
    assert "PreInvocation" in agent_hooks
    assert "PostToolUse" in agent_hooks
    assert "Stop" in agent_hooks

    # Verify plugin and MCP config
    plugin_json = repository / ".agents" / "plugins" / "memory-stale" / "plugin.json"
    assert plugin_json.exists()
    plugin_data = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert plugin_data["name"] == "memory-stale"

    mcp_config = repository / ".agents" / "plugins" / "memory-stale" / "mcp_config.json"
    assert mcp_config.exists()
    mcp_data = json.loads(mcp_config.read_text(encoding="utf-8"))
    assert "mcpServers" in mcp_data
    assert "memory-stale" in mcp_data["mcpServers"]

"""Install Memory Stale as a target repository's local Codex integration."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

HOOK_COMMANDS: dict[str, list[dict[str, object]]] = {
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CODEX_PROJECT_ROOT:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CODEX_PROJECT_ROOT:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/user_prompt_submit.py"'
                    ),
                    "timeout": 10,
                    "statusMessage": "Loading active project memory",
                    "additionalContextLimit": 1500,
                }
            ]
        }
    ],
    "PostToolUse": [
        {
            "matcher": "^(Bash|apply_patch|Edit|Write)$",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CODEX_PROJECT_ROOT:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CODEX_PROJECT_ROOT:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/post_tool_use.py"'
                    ),
                    "timeout": 10,
                    "statusMessage": "Recording workspace changes",
                }
            ],
        }
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CODEX_PROJECT_ROOT:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CODEX_PROJECT_ROOT:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/stop.py"'
                    ),
                    "timeout": 30,
                    "statusMessage": "Reconciling project memory",
                }
            ]
        }
    ],
}
MCP_SERVER = {
    "command": "sh",
    "args": [".agents/skills/memory-stale/scripts/run-python.sh", "-m", "memory_stale.mcp_server"],
}


class InstallationError(RuntimeError):
    """Raised when target-local installation cannot proceed safely."""


def _read_json(path: Path, expected_key: str) -> dict[str, object]:
    if not path.exists():
        return {expected_key: {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InstallationError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict) or not isinstance(value.get(expected_key), dict):
        raise InstallationError(f"{path} must contain an object named {expected_key!r}")
    return cast(dict[str, object], value)


def _atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(json.dumps(value, indent=2) + "\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _target_repository(target: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InstallationError(f"{target} is not inside a Git working tree")
    return Path(result.stdout.strip()).resolve()


def _configuration(source: Path, repository: Path) -> tuple[dict[str, object], dict[str, object]]:
    hooks_path = repository / ".codex" / "hooks.json"
    mcp_path = repository / ".mcp.json"
    hooks = _read_json(hooks_path, "hooks")
    mcp = _read_json(mcp_path, "mcpServers")
    hook_groups = cast(dict[str, object], hooks["hooks"])
    for event, additions in HOOK_COMMANDS.items():
        existing = hook_groups.get(event, [])
        if not isinstance(existing, list):
            raise InstallationError(f"{hooks_path} hooks.{event} must be an array")
        hook_groups[event] = [*existing, *additions]
    servers = cast(dict[str, object], mcp["mcpServers"])
    existing_server = servers.get("memory-stale")
    if existing_server is not None and existing_server != MCP_SERVER:
        raise InstallationError(
            f"{mcp_path} already registers a different 'memory-stale' MCP server; resolve it first"
        )
    servers["memory-stale"] = MCP_SERVER
    return hooks, mcp


def _copy_artifacts(source: Path, repository: Path) -> None:
    destination = repository / ".agents" / "skills" / "memory-stale"
    if destination.exists():
        raise InstallationError(
            f"{destination} already exists; remove or upgrade the project-local installation explicitly"
        )
    destination.mkdir(parents=True)
    shutil.copy2(source / "skills" / "memory-stale" / "SKILL.md", destination / "SKILL.md")
    shutil.copytree(source / "src", destination / "src")
    shutil.copytree(source / "hooks", destination / "hooks")
    shutil.copytree(
        source / "scripts", destination / "scripts", ignore=shutil.ignore_patterns("install-*")
    )
    shutil.copy2(source / "pyproject.toml", destination / "pyproject.toml")
    shutil.copy2(source / "uv.lock", destination / "uv.lock")


def install(source: Path, target: Path) -> Path:
    repository = _target_repository(target)
    destination = repository / ".agents" / "skills" / "memory-stale"
    if destination.exists():
        raise InstallationError(
            f"{destination} already exists; remove or upgrade the project-local installation explicitly"
        )
    hooks, mcp = _configuration(source, repository)
    _copy_artifacts(source, repository)
    _atomic_write_json(repository / ".codex" / "hooks.json", hooks)
    _atomic_write_json(repository / ".mcp.json", mcp)
    return repository


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print("usage: install-project.sh <target-git-repository>", file=sys.stderr)
        return 2
    source = Path(arguments[0]).resolve()
    target = Path(arguments[1]).resolve()
    try:
        repository = install(source, target)
    except InstallationError as error:
        print(f"Memory Stale installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Memory Stale installed locally in {repository}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

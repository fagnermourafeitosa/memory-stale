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

CLAUDE_HOOK_COMMANDS: dict[str, list[dict[str, object]]] = {
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/claude_user_prompt_submit.py"'
                    ),
                    "timeout": 10,
                }
            ]
        }
    ],
    "PostToolUse": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/claude_post_tool_use.py"'
                    ),
                    "timeout": 10,
                }
            ]
        }
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        'sh "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/skills/memory-stale/'
                        'scripts/run-python.sh" "${CLAUDE_PROJECT_DIR:-$PWD}/.agents/'
                        'skills/memory-stale/hooks/claude_stop.py"'
                    ),
                    "timeout": 30,
                }
            ]
        }
    ],
}

DEFAULT_MEMORY_CONFIG = """# Maximum number of tokens of active memory injected into task context.
context_budget = 1500

# Maximum number of highest-ranked active memories injected per task.
top_k = 5

# Generate the optional HTML health report after each completed turn.
auto_report = false

# Repository-relative path used when an HTML report is requested.
report_path = \"memory-report.html\"
"""


class InstallationError(RuntimeError):
    """Raised when target-local installation cannot proceed safely."""


def _read_json(path: Path, expected_key: str) -> dict[str, object]:
    if not path.exists():
        return {expected_key: {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InstallationError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise InstallationError(f"{path} must contain a JSON object")
    if expected_key not in value:
        value[expected_key] = {}
    if not isinstance(value[expected_key], dict):
        raise InstallationError(f"{path} must contain an object named {expected_key!r}")
    return cast(dict[str, object], value)


def _atomic_write_json(path: Path, value: dict[str, object]) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2) + "\n")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _write_default_memory_config(repository: Path) -> None:
    _atomic_write_text(
        repository / ".agents" / "skills" / ".agent-memory" / "config.toml",
        DEFAULT_MEMORY_CONFIG,
    )


def _target_repository(target: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InstallationError(f"{target} is not inside a Git working tree")
    return Path(result.stdout.strip()).resolve()


def _merge_hooks(
    configuration: dict[str, object],
    additions_by_event: dict[str, list[dict[str, object]]],
    path: Path,
) -> dict[str, object]:
    hook_groups = cast(dict[str, object], configuration["hooks"])
    for event, additions in additions_by_event.items():
        existing = hook_groups.get(event, [])
        if not isinstance(existing, list):
            raise InstallationError(f"{path} hooks.{event} must be an array")
        hook_groups[event] = [*existing, *(item for item in additions if item not in existing)]
    return configuration


def _codex_configuration(repository: Path) -> dict[str, object]:
    hooks_path = repository / ".codex" / "hooks.json"
    return _merge_hooks(_read_json(hooks_path, "hooks"), HOOK_COMMANDS, hooks_path)


def _claude_configuration(repository: Path) -> dict[str, object]:
    settings_path = repository / ".claude" / "settings.json"
    return _merge_hooks(_read_json(settings_path, "hooks"), CLAUDE_HOOK_COMMANDS, settings_path)


def _mcp_configuration(repository: Path) -> dict[str, object]:
    configuration = _read_json(repository / ".mcp.json", "mcpServers")
    servers = cast(dict[str, object], configuration["mcpServers"])
    bootstrap = repository / ".agents" / "skills" / "memory-stale" / "scripts" / "run-python.sh"
    server = {"command": "sh", "args": [str(bootstrap), "-m", "memory_stale.mcp_server"]}
    existing = servers.get("memory-stale")
    if existing is None:
        servers["memory-stale"] = server
    elif existing != server:
        raise InstallationError(".mcp.json already registers an incompatible memory-stale server")
    return configuration


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


def _copy_claude_skill(source: Path, repository: Path) -> None:
    claude_skill = repository / ".claude" / "skills" / "memory-stale"
    claude_skill.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        source / "claude" / "skills" / "memory-stale" / "SKILL.md", claude_skill / "SKILL.md"
    )


def _register_mcp(repository: Path) -> None:
    bootstrap = repository / ".agents" / "skills" / "memory-stale" / "scripts" / "run-python.sh"
    try:
        result = subprocess.run(
            [
                "codex",
                "mcp",
                "add",
                "memory-stale",
                "--",
                "sh",
                str(bootstrap),
                "-m",
                "memory_stale.mcp_server",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise InstallationError(
            "Codex CLI is required to register the memory-stale MCP server"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Codex CLI failure"
        raise InstallationError(f"could not register the memory-stale MCP server: {detail}")


def install(source: Path, target: Path, hosts: frozenset[str]) -> Path:
    repository = _target_repository(target)
    destination = repository / ".agents" / "skills" / "memory-stale"
    first_install = not destination.exists()
    if first_install:
        _copy_artifacts(source, repository)
        _write_default_memory_config(repository)
    if "codex" in hosts:
        _atomic_write_json(repository / ".codex" / "hooks.json", _codex_configuration(repository))
    if "claude" in hosts:
        _copy_claude_skill(source, repository)
        _atomic_write_json(
            repository / ".claude" / "settings.json", _claude_configuration(repository)
        )
        _atomic_write_json(repository / ".mcp.json", _mcp_configuration(repository))
    if first_install and "codex" in hosts:
        _register_mcp(repository)
    return repository


def main(arguments: list[str]) -> int:
    if len(arguments) == 2:
        source_text, target_text = arguments
        hosts = frozenset({"codex", "claude"})
    elif (
        len(arguments) == 4
        and arguments[2] == "--host"
        and arguments[3]
        in {
            "codex",
            "claude",
            "both",
        }
    ):
        source_text, target_text = arguments[:2]
        hosts = (
            frozenset({"codex", "claude"}) if arguments[3] == "both" else frozenset({arguments[3]})
        )
    else:
        print(
            "usage: install-project.sh <target-git-repository> [--host codex|claude|both]",
            file=sys.stderr,
        )
        return 2
    source = Path(source_text).resolve()
    target = Path(target_text).resolve()
    try:
        repository = install(source, target, hosts)
    except InstallationError as error:
        print(f"Memory Stale installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Memory Stale installed locally in {repository}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

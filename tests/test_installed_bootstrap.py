import json
import os
import shutil
import subprocess
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1]


def test_fresh_installed_plugin_bootstraps_isolated_runtime(tmp_path: Path) -> None:
    plugin = tmp_path / "installed" / "memory-stale"
    shutil.copytree(
        SOURCE_ROOT,
        plugin,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".coverage*", ".mypy_cache", ".pytest_cache", ".ruff_cache"
        ),
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    plugin_data = tmp_path / "plugin-data"
    config = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    environment = os.environ.copy()
    environment.update({"PLUGIN_ROOT": str(plugin), "PLUGIN_DATA": str(plugin_data)})
    payload = json.dumps({"turn_id": "turn-install", "cwd": str(repository), "prompt": "test"})

    first = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        input=payload,
        shell=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        input=payload,
        shell=True,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"] == ""
    assert (plugin_data / ".venv" / "bin" / "python").is_file()
    assert (plugin_data / "uv-cache").is_dir()
    assert not (plugin / ".venv").exists()

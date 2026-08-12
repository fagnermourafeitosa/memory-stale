import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast


class PluginHarness:
    def __init__(self, root: Path, plugin_root: Path) -> None:
        self.root = root
        self.plugin_root = plugin_root
        root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "harness@example.test")
        self.git("config", "user.name", "Harness")
        self._hooks = json.loads(
            (plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def hook(self, event: str, turn_id: str, **fields: object) -> dict[str, object] | None:
        command = self._hooks[event][0]["hooks"][0]["command"]
        environment = os.environ.copy()
        environment.update(
            {"PLUGIN_ROOT": str(self.plugin_root), "PLUGIN_DATA": str(self.plugin_root)}
        )
        result = subprocess.run(
            command,
            cwd=self.root,
            env=environment,
            input=json.dumps({"turn_id": turn_id, "cwd": str(self.root), **fields}),
            shell=True,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return cast(dict[str, object], json.loads(result.stdout)) if result.stdout else None

    def capture(self, **arguments: object) -> dict[str, object]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.plugin_root / "src")
        server = subprocess.Popen(
            [sys.executable, "-m", "memory_stale.mcp_server"],
            cwd=self.root,
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
                    "params": {"name": "memory.capture", "arguments": arguments},
                }
            )
            + "\n"
        )
        server.stdin.flush()
        response = cast(dict[str, object], json.loads(server.stdout.readline()))
        server.stdin.close()
        server.wait(timeout=5)
        return response

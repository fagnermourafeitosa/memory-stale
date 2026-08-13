import json
import os
import subprocess
from pathlib import Path
from typing import cast


class LocalHarness:
    def __init__(self, root: Path, runtime_root: Path) -> None:
        self.root = root
        self.runtime_root = runtime_root
        root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "harness@example.test")
        self.git("config", "user.name", "Harness")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def hook(self, event: str, turn_id: str, **fields: object) -> dict[str, object] | None:
        scripts = {
            "UserPromptSubmit": "user_prompt_submit.py",
            "PostToolUse": "post_tool_use.py",
            "Stop": "stop.py",
        }
        environment = os.environ.copy()
        environment.update(
            {
                "MEMORY_STALE_SKIP_SYNC": "1",
                "MEMORY_STALE_PROJECT_ENVIRONMENT": str(self.runtime_root / ".venv"),
            }
        )
        result = subprocess.run(
            [
                "sh",
                str(self.runtime_root / "scripts" / "run-python.sh"),
                str(self.runtime_root / "hooks" / scripts[event]),
            ],
            cwd=self.root,
            env=environment,
            input=json.dumps({"turn_id": turn_id, "cwd": str(self.root), **fields}),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return cast(dict[str, object], json.loads(result.stdout)) if result.stdout else None

    def capture(self, **arguments: object) -> dict[str, object]:
        environment = os.environ.copy()
        environment.update(
            {
                "MEMORY_STALE_SKIP_SYNC": "1",
                "MEMORY_STALE_PROJECT_ENVIRONMENT": str(self.runtime_root / ".venv"),
            }
        )
        server = subprocess.Popen(
            [
                "sh",
                str(self.runtime_root / "scripts" / "run-python.sh"),
                "-m",
                "memory_stale.mcp_server",
            ],
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

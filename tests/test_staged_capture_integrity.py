"""A corrupt staged capture never produces a partial memory write at stop time."""

import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from memory_stale.codex_adapter import run_stop, run_user_prompt_submit

EVIDENCE = {
    "type": "symbol",
    "role": "primary",
    "locator": "auth.py:login",
    "fingerprint": "v2:" + "1" * 64,
}
SUPPORT = {
    "type": "symbol",
    "role": "supporting",
    "locator": "auth.py:token",
    "fingerprint": "v2:" + "2" * 64,
}
EDGE = {"from": "symbol:auth.py:login", "to": "symbol:auth.py:token"}

Mutation = Callable[[dict[str, object]], None]


def _capture() -> dict[str, object]:
    return {
        "kind": "behavior",
        "claim": "Login validates MFA before creating a session.",
        "durability_reason": "Security reviews rely on it.",
        "evidence": [dict(EVIDENCE), dict(SUPPORT)],
        "supported_by": ["symbol:auth.py:login"],
        "dependencies": [dict(EDGE)],
        "dependency_extractor_version": "static-v1",
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda c: c.update(evidence="auth.py:login"), "capture evidence must be an array"),
        (lambda c: c.update(evidence=["auth.py:login"]), "capture evidence item must be an object"),
        (
            lambda c: c.update(evidence=[{**EVIDENCE, "fingerprint": ""}]),
            "capture evidence item is invalid",
        ),
        (lambda c: c.update(evidence=[SUPPORT]), "capture evidence requires a primary item"),
        (
            lambda c: c.update(evidence=[EVIDENCE, {**EVIDENCE, "role": "supporting"}]),
            "capture evidence must not contain duplicate locators",
        ),
        (lambda c: c.update(supported_by=[]), "capture supported_by must be a non-empty array"),
        (
            lambda c: c.update(supported_by=["symbol:auth.py:ghost"]),
            "capture supported_by has unknown or duplicate evidence",
        ),
        (lambda c: c.update(dependencies={}), "capture dependencies must be an array"),
        (lambda c: c.update(dependencies=["login->token"]), "capture dependency must be an object"),
        (
            lambda c: c.update(dependencies=[{**EDGE, "weight": 1}]),
            "capture dependency has unsupported fields",
        ),
        (
            lambda c: c.update(dependencies=[{**EDGE, "to": "symbol:auth.py:ghost"}]),
            "capture dependency has an unknown node",
        ),
        (
            lambda c: c.update(dependencies=[{**EDGE, "relationship": "imports"}]),
            "capture dependency has an invalid relationship",
        ),
        (
            lambda c: c.update(dependencies=[{**EDGE, "origin": "guessed"}]),
            "capture dependency has an invalid origin",
        ),
        (
            lambda c: c.update(dependencies=[EDGE, EDGE]),
            "capture dependencies must not contain duplicates",
        ),
        (lambda c: c.update(retrieval_terms="mfa"), "retrieval_terms must be an array"),
        (lambda c: c.update(retrieval_terms=[7]), "retrieval_terms must contain only strings"),
    ],
    ids=[
        "evidence-not-array",
        "evidence-item-not-object",
        "evidence-item-blank-field",
        "no-primary",
        "duplicate-locator",
        "empty-supported-by",
        "unknown-supported-by",
        "dependencies-not-array",
        "dependency-not-object",
        "dependency-extra-field",
        "dependency-unknown-node",
        "dependency-bad-relationship",
        "dependency-bad-origin",
        "duplicate-dependency",
        "terms-not-array",
        "terms-not-strings",
    ],
)
def test_stop_rejects_a_corrupt_staged_capture_without_writing_memories(
    tmp_path: Path, mutate: Mutation, message: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    turn = {"turn_id": "turn-1", "cwd": str(repository), "prompt": "Harden login"}
    run_user_prompt_submit(io.StringIO(json.dumps(turn)), io.StringIO())
    [task_path] = (repository / ".git" / "memory-stale" / "tasks").glob("*.json")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    capture = _capture()
    mutate(capture)
    task["captures"] = [capture]
    task_path.write_text(json.dumps(task), encoding="utf-8")
    output = io.StringIO()

    assert run_stop(io.StringIO(json.dumps(turn)), output) == 0

    assert json.loads(output.getvalue()) == {
        "systemMessage": f"Memory Stale Stop failed: ValueError: {message}"
    }
    assert not (repository / ".agents" / "skills" / ".agent-memory" / "memories").exists()

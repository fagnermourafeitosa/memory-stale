import io
import json
import subprocess
from pathlib import Path

from memory_stale.antigravity_adapter import (
    run_post_tool_use,
    run_pre_invocation,
    run_stop,
)
from memory_stale.claude_adapter import run_user_prompt_submit as run_claude_user_prompt_submit
from memory_stale.codex_adapter import run_user_prompt_submit as run_codex_user_prompt_submit
from memory_stale.memory_store import MemoryStore


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    return repository


def _antigravity_payload(repository: Path, **fields: object) -> dict[str, object]:
    return {
        "conversationId": "conv-1234",
        "workspacePaths": [str(repository)],
        "cwd": str(repository),
        **fields,
    }


def _run(function: object, payload: dict[str, object]) -> dict[str, object]:
    output = io.StringIO()
    exit_code = function(io.StringIO(json.dumps(payload)), output)  # type: ignore[operator]
    assert exit_code == 0
    return json.loads(output.getvalue()) if output.getvalue() else {}


def test_antigravity_pre_invocation_injects_ephemeral_memory_context(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    output = io.StringIO()

    exit_code = run_pre_invocation(
        io.StringIO(
            json.dumps(
                {
                    "conversationId": "conv-1234",
                    "workspacePaths": [str(repository)],
                    "prompt": "Update authentication flow",
                }
            )
        ),
        output,
    )

    assert exit_code == 0
    response = json.loads(output.getvalue())
    assert "injectSteps" in response
    assert len(response["injectSteps"]) == 1
    assert "ephemeralMessage" in response["injectSteps"][0]
    ephemeral = response["injectSteps"][0]["ephemeralMessage"]
    assert "Memory Stale completion requirement:" in ephemeral
    assert "call memory.capture before the final response" in ephemeral

    task_files = list((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    assert len(task_files) == 1
    assert json.loads(task_files[0].read_text(encoding="utf-8"))["turn_id"] == (
        "antigravity:conv-1234"
    )


def test_antigravity_post_tool_use_records_task_ledger(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _run(
        run_pre_invocation,
        _antigravity_payload(repository, prompt="Edit app.py"),
    )

    response = _run(
        run_post_tool_use,
        _antigravity_payload(
            repository,
            stepIdx=3,
            toolCall={
                "name": "replace_file_content",
                "args": {"TargetFile": str(repository / "app.py"), "ReplacementContent": "new"},
            },
        ),
    )

    assert response == {}
    task_path = next((repository / ".git" / "memory-stale" / "tasks").glob("*.json"))
    assert json.loads(task_path.read_text(encoding="utf-8"))["ledger"] == [
        {
            "tool_name": "replace_file_content",
            "tool_use_id": "step-3",
            "tool_input": {
                "TargetFile": str(repository / "app.py"),
                "ReplacementContent": "new",
            },
        }
    ]


def test_antigravity_stop_reconciles_provenance_and_marks_stale(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    source = repository / "service.py"
    source.write_text("def enabled() -> bool:\n    return False\n", encoding="utf-8")
    _run(
        run_pre_invocation,
        _antigravity_payload(repository, prompt="Enable service"),
    )
    source.write_text("def enabled() -> bool:\n    return True\n", encoding="utf-8")

    response = _run(run_stop, _antigravity_payload(repository))

    assert response == {}
    assert [memory.claim for memory in MemoryStore(repository).load_all()] == [
        "Automatic change record: changed symbol service.py:enabled."
    ]


def test_antigravity_missing_conversation_id_is_non_blocking_noop(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    response = _run(
        run_pre_invocation,
        {"workspacePaths": [str(repository)], "prompt": "No conversation identity"},
    )

    assert response == {"injectSteps": []}
    assert not (repository / ".git" / "memory-stale" / "tasks").exists()


def test_antigravity_outside_git_repository_is_non_blocking(tmp_path: Path) -> None:
    response = _run(
        run_pre_invocation,
        {"conversationId": "conv-nogit", "workspacePaths": [str(tmp_path)], "prompt": "Outside"},
    )

    assert response == {"injectSteps": []}


def test_all_three_harnesses_produce_identical_provenance(tmp_path: Path) -> None:
    agy_repo = _repository(tmp_path / "antigravity")
    codex_repo = _repository(tmp_path / "codex")
    claude_repo = _repository(tmp_path / "claude")

    for repo in (agy_repo, codex_repo, claude_repo):
        (repo / "jobs.py").write_text("def run() -> int:\n    return 1\n", encoding="utf-8")

    _run(run_pre_invocation, _antigravity_payload(agy_repo, prompt="Update run"))
    _run(
        run_codex_user_prompt_submit,
        {"turn_id": "codex-turn", "cwd": str(codex_repo), "prompt": "Update run"},
    )
    _run(
        run_claude_user_prompt_submit,
        {
            "session_id": "s1",
            "prompt_id": "p1",
            "cwd": str(claude_repo),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Update run",
        },
    )

    for repo in (agy_repo, codex_repo, claude_repo):
        (repo / "jobs.py").write_text("def run() -> int:\n    return 2\n", encoding="utf-8")

    _run(run_stop, _antigravity_payload(agy_repo))
    from memory_stale.claude_adapter import run_stop as run_claude_stop
    from memory_stale.codex_adapter import run_stop as run_codex_stop

    _run(run_codex_stop, {"turn_id": "codex-turn", "cwd": str(codex_repo)})
    _run(
        run_claude_stop,
        {
            "session_id": "s1",
            "prompt_id": "p1",
            "cwd": str(claude_repo),
            "hook_event_name": "Stop",
        },
    )

    agy_claims = [m.claim for m in MemoryStore(agy_repo).load_all()]
    codex_claims = [m.claim for m in MemoryStore(codex_repo).load_all()]
    claude_claims = [m.claim for m in MemoryStore(claude_repo).load_all()]

    assert agy_claims == codex_claims == claude_claims

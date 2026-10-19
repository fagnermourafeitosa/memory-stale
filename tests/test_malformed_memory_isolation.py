import io
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from memory_stale.antigravity_adapter import run_pre_invocation
from memory_stale.claude_adapter import run_stop, run_user_prompt_submit
from memory_stale.codex_adapter import run_user_prompt_submit as run_codex_user_prompt_submit
from memory_stale.dream import dream
from memory_stale.evidence import EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.mcp_server import serve
from memory_stale.memory_store import MemoryStore
from memory_stale.symbol_index import SymbolIndexer

MEMORIES = Path(".agents/skills/.agent-memory/memories")
INVALID_YAML = "---\ntype: [unclosed\n---\n\nBroken claim.\n"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    (repository / "billing.py").write_text(
        "def invoice_total():\n    return 42\n", encoding="utf-8"
    )
    return repository


def _store_valid_memory(repository: Path) -> None:
    signature = SymbolIndexer(repository).signature("billing.py:invoice_total")
    MemoryStore(repository).write_all(
        [
            Memory(
                "invoice-total",
                "behavior",
                "active",
                "Invoice totals are always forty-two.",
                "Billing relies on this constant.",
                (EvidenceItem("symbol", "primary", "billing.py:invoice_total", signature),),
            )
        ]
    )


def _write_malformed(repository: Path, name: str, content: str) -> Path:
    path = repository / MEMORIES / name
    path.write_text(content, encoding="utf-8")
    return path


def _claude(function: object, repository: Path, event: str, **fields: object) -> dict[str, object]:
    output = io.StringIO()
    payload = {
        "session_id": "session-1",
        "prompt_id": "prompt-1",
        "cwd": str(repository),
        "hook_event_name": event,
        **fields,
    }
    assert function(io.StringIO(json.dumps(payload)), output) == 0  # type: ignore[operator]
    text = output.getvalue()
    return cast(dict[str, object], json.loads(text)) if text.strip() else {}


def _claude_prompt(repository: Path, prompt: str) -> dict[str, object]:
    return _claude(run_user_prompt_submit, repository, "UserPromptSubmit", prompt=prompt)


def test_prompt_injects_valid_memories_and_warns_about_a_malformed_file(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    _write_malformed(repository, "broken.md", INVALID_YAML)

    response = _claude_prompt(repository, "How are invoice totals computed?")

    assert "systemMessage" not in response
    context = response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]
    assert "Invoice totals are always forty-two." in context
    assert (
        "Memory Stale skipped .agents/skills/.agent-memory/memories/broken.md: "
        "invalid YAML front matter"
    ) in context.splitlines()


def test_turn_leaves_a_malformed_memory_file_byte_identical(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    broken = _write_malformed(repository, "broken.md", INVALID_YAML)
    _claude_prompt(repository, "Change billing")
    (repository / "billing.py").write_text(
        "def invoice_total():\n    return 43\n", encoding="utf-8"
    )

    _claude(run_stop, repository, "Stop")

    assert broken.read_bytes() == INVALID_YAML.encode("utf-8")


def _change_billing_in_one_turn(repository: Path) -> dict[str, object]:
    _claude_prompt(repository, "Change billing")
    (repository / "billing.py").write_text(
        "def invoice_total():\n    return 43\n", encoding="utf-8"
    )
    return _claude(run_stop, repository, "Stop")


def _memory_files(repository: Path) -> list[str]:
    return sorted(path.name for path in (repository / MEMORIES).glob("*.md"))


def test_stop_persists_the_turn_capture_while_a_malformed_file_exists(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    _write_malformed(repository, "broken.md", INVALID_YAML)

    response = _change_billing_in_one_turn(repository)

    assert "systemMessage" not in response
    assert "skipped" not in json.dumps(response)
    memories = {memory.claim: memory.status for memory in MemoryStore(repository).load_all()}
    assert memories == {
        "Invoice totals are always forty-two.": "stale",
        "Automatic change record: changed symbol billing.py:invoice_total.": "active",
    }
    assert list((repository / ".git" / "memory-stale" / "tasks").glob("*.json")) == []


def test_fixed_memory_file_rejoins_the_store_without_warning(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    valid = repository / MEMORIES / "invoice-total.md"
    original = valid.read_text(encoding="utf-8")
    valid.write_text(original.replace("---", "--", 1), encoding="utf-8")
    assert "Memory Stale skipped" in json.dumps(_claude_prompt(repository, "invoice totals"))

    valid.write_text(original, encoding="utf-8")
    response = _claude_prompt(repository, "How are invoice totals computed?")

    context = response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]
    assert "Invoice totals are always forty-two." in context
    assert "Memory Stale skipped" not in context


def test_colliding_write_preserves_the_malformed_file(tmp_path: Path) -> None:
    oracle = _repository(tmp_path / "oracle")
    _change_billing_in_one_turn(oracle)
    [automatic_file] = _memory_files(oracle)
    repository = _repository(tmp_path / "subject")
    _store_valid_memory(repository)
    broken = _write_malformed(repository, automatic_file, INVALID_YAML)

    _change_billing_in_one_turn(repository)

    assert broken.read_bytes() == INVALID_YAML.encode("utf-8")
    assert [memory.claim for memory in MemoryStore(repository).load_all()] == [
        "Invoice totals are always forty-two."
    ]


def test_store_with_only_malformed_files_behaves_as_empty_with_warnings(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / MEMORIES).mkdir(parents=True)
    _write_malformed(repository, "a.md", INVALID_YAML)
    _write_malformed(repository, "b.md", "no front matter at all\n")

    response = _claude_prompt(repository, "anything")

    context = response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]
    assert context.splitlines()[-2:] == [
        "Memory Stale skipped .agents/skills/.agent-memory/memories/a.md: "
        "invalid YAML front matter",
        "Memory Stale skipped .agents/skills/.agent-memory/memories/b.md: missing front matter",
    ]


def _valid_text(repository: Path) -> str:
    _store_valid_memory(repository)
    path = repository / MEMORIES / "invoice-total.md"
    text = path.read_text(encoding="utf-8")
    path.unlink()
    return text


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda text: text.replace("status: active\n", "status: retired\n", 1), "invalid status"),
        (
            lambda text: text.replace("type: Memory Stale Claim", "type: Note", 1),
            "invalid OKF type",
        ),
        (
            lambda text: text.replace("role: primary", "role: supporting"),
            "missing primary evidence",
        ),
        (
            lambda text: text.replace("stale_reasons: null", "stale_reasons:\n    ghost: changed"),
            "stale reason references unknown evidence",
        ),
        (lambda text: "---\n- just\n- a list\n---\n\nClaim.\n", "invalid front matter"),
        (
            lambda text: "---\nkind: behavior\nstatus: active\n---\n\nClaim.\n",
            "invalid legacy signatures",
        ),
    ],
    ids=["status", "okf-type", "no-primary", "stale-reason", "not-a-mapping", "legacy"],
)
def test_prompt_warning_names_the_schema_violation(
    tmp_path: Path, mutate: Callable[[str], str], reason: str
) -> None:
    repository = _repository(tmp_path)
    _write_malformed(repository, "bad.md", mutate(_valid_text(repository)))

    response = _claude_prompt(repository, "invoice totals")

    context = response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]
    assert f"Memory Stale skipped .agents/skills/.agent-memory/memories/bad.md: {reason}" in (
        context.splitlines()
    )


def test_prompt_warning_names_non_utf8_content(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / MEMORIES).mkdir(parents=True)
    (repository / MEMORIES / "latin.md").write_bytes(b"---\ntitle: caf\xe9\n---\n\nClaim.\n")

    response = _claude_prompt(repository, "anything")

    assert (
        "Memory Stale skipped .agents/skills/.agent-memory/memories/latin.md: "
        "invalid UTF-8 encoding"
    ) in response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_prompt_warning_names_an_unreadable_file(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    locked = _write_malformed(repository, "locked.md", _valid_text(repository))
    locked.chmod(0)
    try:
        response = _claude_prompt(repository, "anything")
    finally:
        locked.chmod(0o644)

    assert (
        "Memory Stale skipped .agents/skills/.agent-memory/memories/locked.md: "
        "unreadable file: Permission denied"
    ) in response["hookSpecificOutput"]["additionalContext"]  # type: ignore[index]


def test_dream_audits_valid_memories_and_lists_the_malformed_file(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    broken = _write_malformed(repository, "broken.md", INVALID_YAML)
    (repository / "billing.py").write_text(
        "def invoice_total():\n    return 43\n", encoding="utf-8"
    )

    summary = dream(repository)

    assert summary.marked_stale == ["invoice-total"]
    assert summary.errors == [
        ".agents/skills/.agent-memory/memories/broken.md: invalid YAML front matter"
    ]
    assert broken.read_bytes() == INVALID_YAML.encode("utf-8")


def test_report_lists_unreadable_memory_files_beside_valid_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    _store_valid_memory(repository)
    _write_malformed(repository, "broken.md", INVALID_YAML)
    monkeypatch.chdir(repository)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "memory.report", "arguments": {}},
    }
    output = io.StringIO()

    serve(io.StringIO(json.dumps(request) + "\n"), output)

    assert json.loads(output.getvalue())["result"]["isError"] is False
    report = (repository / "memory-report.html").read_text(encoding="utf-8")
    assert "Invoice totals are always forty-two." in report
    assert (
        "<h2>Unreadable memory files</h2><ul><li>"
        "<code>.agents/skills/.agent-memory/memories/broken.md</code>: "
        "invalid YAML front matter</li></ul>"
    ) in report


def test_every_harness_injects_the_same_isolated_context(tmp_path: Path) -> None:
    contexts = []
    for harness in ("claude", "codex", "antigravity"):
        repository = _repository(tmp_path / harness)
        _store_valid_memory(repository)
        _write_malformed(repository, "broken.md", INVALID_YAML)
        prompt = "How are invoice totals computed?"
        if harness == "claude":
            response = _claude_prompt(repository, prompt)
            contexts.append(response["hookSpecificOutput"]["additionalContext"])  # type: ignore[index]
            continue
        output = io.StringIO()
        if harness == "codex":
            payload: dict[str, object] = {
                "turn_id": "turn-1",
                "cwd": str(repository),
                "prompt": prompt,
            }
            run_codex_user_prompt_submit(io.StringIO(json.dumps(payload)), output)
            contexts.append(
                json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
            )
        else:
            payload = {
                "conversationId": "conversation-1",
                "workspacePaths": [str(repository)],
                "prompt": prompt,
            }
            run_pre_invocation(io.StringIO(json.dumps(payload)), output)
            contexts.append(json.loads(output.getvalue())["injectSteps"][0]["ephemeralMessage"])

    assert contexts[0] == contexts[1] == contexts[2]
    assert "Invoice totals are always forty-two." in contexts[0]
    assert "Memory Stale skipped .agents/skills/.agent-memory/memories/broken.md" in contexts[0]

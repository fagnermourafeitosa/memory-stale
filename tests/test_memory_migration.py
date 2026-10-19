"""Legacy memory files keep working and migrate to the current format through the lifecycle."""

import io
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

from memory_stale.claude_adapter import run_user_prompt_submit
from memory_stale.dream import dream
from memory_stale.symbol_index import SymbolIndexer

MEMORIES = Path(".agents/skills/.agent-memory/memories")


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    (repository / "jobs.py").write_text(
        "def retry():\n    return 3\n\n\ndef backoff():\n    return 2\n", encoding="utf-8"
    )
    (repository / MEMORIES).mkdir(parents=True)
    return repository


def _legacy_file(repository: Path, name: str, front_matter: dict[str, object], claim: str) -> Path:
    path = repository / MEMORIES / name
    path.write_text(
        f"---\n{yaml.safe_dump(front_matter, sort_keys=False)}---\n\n{claim}\n", encoding="utf-8"
    )
    return path


def _front_matter(path: Path) -> dict[str, object]:
    _opening, front_matter, _claim = path.read_text(encoding="utf-8").split("---", 2)
    return cast(dict[str, object], yaml.safe_load(front_matter))


def _fingerprint(repository: Path, locator: str) -> str:
    return SymbolIndexer(repository).signature(locator)


def _v3(repository: Path) -> dict[str, object]:
    return {
        "schema_version": 3,
        "revision_id": "retry-v3",
        "claim_id": "retry-claim",
        "kind": "behavior",
        "status": "active",
        "durability_reason": "Workers depend on three retries.",
        "evidence": [
            {
                "type": "symbol",
                "role": "primary",
                "locator": "jobs.py:retry",
                "fingerprint": _fingerprint(repository, "jobs.py:retry"),
            }
        ],
        "observed_commit": "abc123",
        "observed_at": "2026-08-01T10:00:00+00:00",
    }


def _v4(repository: Path) -> dict[str, object]:
    return {
        "schema_version": 4,
        "revision_id": "backoff-v4",
        "kind": "behavior",
        "status": "stale",
        "durability_reason": "Backoff pacing is an SLA.",
        "evidence": [
            {
                "type": "symbol",
                "role": "primary",
                "locator": "jobs.py:backoff",
                "fingerprint": "v2:" + "0" * 64,
            },
            {
                "type": "symbol",
                "role": "supporting",
                "locator": "jobs.py:retry",
                "fingerprint": _fingerprint(repository, "jobs.py:retry"),
            },
        ],
        "supported_by": ["symbol:jobs.py:backoff"],
        "dependencies": [{"from": "symbol:jobs.py:backoff", "to": "symbol:jobs.py:retry"}],
        "stale_reasons": {"symbol:jobs.py:backoff": "changed"},
        "observed_at": "2026-08-02T10:00:00+00:00",
    }


def test_v3_memory_is_rewritten_as_v5_without_losing_its_meaning(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    legacy = _legacy_file(repository, "legacy-name.md", _v3(repository), "Jobs retry three times.")

    summary = dream(repository)

    assert summary.errors == []
    assert not legacy.exists()
    migrated = _front_matter(repository / MEMORIES / "retry-v3.md")
    extension = cast(dict[str, object], migrated["memory_stale"])
    assert extension["schema_version"] == 5
    assert extension["claim_id"] == "retry-claim"
    assert extension["status"] == "active"
    assert extension["observed_commit"] == "abc123"
    assert extension["observed_at"] == "2026-08-01T10:00:00+00:00"
    assert migrated["title"] == "Jobs retry three times."
    assert migrated["sources"] == [{"id": "symbol:jobs.py:retry", "resource": "jobs.py:retry"}]


def test_v4_memory_keeps_its_graph_and_stale_reasons(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _legacy_file(repository, "backoff-v4.md", _v4(repository), "Backoff doubles each attempt.")

    dream(repository)

    migrated = _front_matter(repository / MEMORIES / "backoff-v4.md")
    extension = cast(dict[str, object], migrated["memory_stale"])
    assert extension["schema_version"] == 5
    assert extension["claim_id"] == "backoff-v4"
    assert extension["status"] == "stale"
    assert extension["supported_by"] == ["symbol:jobs.py:backoff"]
    assert extension["dependencies"] == [
        {"from": "symbol:jobs.py:backoff", "to": "symbol:jobs.py:retry"}
    ]
    assert extension["stale_reasons"] == {"symbol:jobs.py:backoff": "changed"}
    roles = {item["source_id"]: item["role"] for item in extension["evidence"]}  # type: ignore[attr-defined]
    assert roles == {"symbol:jobs.py:backoff": "primary", "symbol:jobs.py:retry": "supporting"}


def test_migration_is_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _legacy_file(repository, "a.md", _v3(repository), "Jobs retry three times.")
    _legacy_file(repository, "b.md", _v4(repository), "Backoff doubles each attempt.")
    dream(repository)
    first = {path.name: path.read_bytes() for path in (repository / MEMORIES).glob("*.md")}

    dream(repository)

    second = {path.name: path.read_bytes() for path in (repository / MEMORIES).glob("*.md")}
    assert sorted(first) == ["backoff-v4.md", "retry-v3.md"]
    assert second == first


def test_prompt_retrieves_a_legacy_memory_before_any_migration(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _legacy_file(repository, "a.md", _v3(repository), "Jobs retry three times.")
    payload = {
        "session_id": "s",
        "prompt_id": "p",
        "cwd": str(repository),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "How many times do jobs retry?",
    }
    output = io.StringIO()

    run_user_prompt_submit(io.StringIO(json.dumps(payload)), output)

    context = json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert "Jobs retry three times." in context
    assert "Memory Stale skipped" not in context


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda data: data.update(evidence=[]), "invalid evidence"),
        (lambda data: data.update(evidence=["jobs.py:retry"]), "invalid evidence item"),
        (
            lambda data: data.update(evidence=[data["evidence"][0], data["evidence"][0]]),
            "duplicate evidence item",
        ),
        (lambda data: data.update(supported_by="symbol:jobs.py:backoff"), "invalid supported_by"),
        (
            lambda data: data.update(supported_by=["symbol:jobs.py:backoff"] * 2),
            "duplicate supported_by",
        ),
        (lambda data: data.update(dependencies={}), "invalid dependencies"),
        (lambda data: data.update(dependencies=[{"from": "x"}]), "invalid dependency"),
        (
            lambda data: data.update(dependencies=[data["dependencies"][0]] * 2),
            "duplicate dependency",
        ),
        (
            lambda data: data.update(
                dependencies=[{"from": "symbol:jobs.py:backoff", "to": "symbol:ghost.py:x"}]
            ),
            "dependency references unknown evidence",
        ),
        (lambda data: data.update(kind=7), "invalid kind"),
        (lambda data: data.update(observed_at=7), "invalid observed_at"),
    ],
    ids=[
        "empty-evidence",
        "evidence-not-object",
        "duplicate-evidence",
        "supported-by-not-list",
        "duplicate-supported-by",
        "dependencies-not-list",
        "dependency-missing-target",
        "duplicate-dependency",
        "dangling-dependency",
        "kind-not-string",
        "observed-at-not-string",
    ],
)
def test_invalid_legacy_memory_is_isolated_and_preserved(
    tmp_path: Path, mutate: object, reason: str
) -> None:
    repository = _repository(tmp_path)
    data = _v4(repository)
    mutate(data)  # type: ignore[operator]
    broken = _legacy_file(repository, "broken.md", data, "Backoff doubles each attempt.")
    before = broken.read_bytes()

    summary = dream(repository)

    assert summary.errors == [f".agents/skills/.agent-memory/memories/broken.md: {reason}"]
    assert broken.read_bytes() == before

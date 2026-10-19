"""Config and schema evidence captured through MCP and audited by the lifecycle."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from memory_stale.codex_adapter import run_stop, run_user_prompt_submit
from memory_stale.dream import dream
from memory_stale.mcp_server import serve
from memory_stale.memory_store import MemoryStore

SETTINGS_JSON = '{"payments": {"retries": 3, "gateway": "stripe"}, "regions": ["eu", "us"]}\n'


def _git(repository: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True)


def _repository(tmp_path: Path, files: dict[str, str]) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "test@example.test")
    _git(repository, "config", "user.name", "Test")
    for name, content in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "baseline")
    return repository


def _turn(repository: Path) -> dict[str, str]:
    turn = {"turn_id": "turn-1", "cwd": str(repository), "prompt": "Tune payments"}
    run_user_prompt_submit(io.StringIO(json.dumps(turn)), io.StringIO())
    return turn


def _capture(
    repository: Path, monkeypatch: pytest.MonkeyPatch, evidence: list[dict[str, str]]
) -> dict[str, object]:
    monkeypatch.chdir(repository)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memory.capture",
            "arguments": {
                "kind": "behavior",
                "claim": "Payments retry a failed charge three times before giving up.",
                "evidence": evidence,
                "durability_reason": "Support playbooks depend on the retry count.",
            },
        },
    }
    output = io.StringIO()
    serve(io.StringIO(json.dumps(request) + "\n"), output)
    return json.loads(output.getvalue())["result"]  # type: ignore[no-any-return]


def _error_text(result: dict[str, object]) -> str:
    assert result["isError"] is True
    return str(result["content"][0]["text"])  # type: ignore[index]


def _capture_and_stop(
    repository: Path, monkeypatch: pytest.MonkeyPatch, evidence_type: str, locator: str
) -> None:
    turn = _turn(repository)
    path = repository / locator.partition("#")[0]
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = _capture(
        repository, monkeypatch, [{"type": evidence_type, "role": "primary", "locator": locator}]
    )
    assert result["isError"] is False, result
    run_stop(io.StringIO(json.dumps(turn)), io.StringIO())


def _statuses(repository: Path) -> dict[str, str]:
    return {
        memory.claim: memory.status
        for memory in MemoryStore(repository).load_all()
        if not memory.claim.startswith("Automatic change record")
    }


CLAIM = "Payments retry a failed charge three times before giving up."


@pytest.mark.parametrize(
    ("name", "content", "locator", "semantic_edit", "cosmetic_edit"),
    [
        (
            "settings.json",
            SETTINGS_JSON,
            "settings.json#/payments/retries",
            '{"payments": {"retries": 5, "gateway": "stripe"}, "regions": ["eu", "us"]}\n',
            '{\n  "regions": ["eu", "us"],\n  "payments": {"gateway": "adyen", "retries": 3}\n}\n',
        ),
        (
            "settings.yaml",
            "payments:\n  retries: 3\n  gateway: stripe\n",
            "settings.yaml#/payments/retries",
            "payments:\n  retries: 4\n  gateway: stripe\n",
            "# tuned by ops\npayments:\n    gateway: adyen\n    retries: 3\n",
        ),
        (
            "settings.toml",
            "[payments]\nretries = 3\ngateway = 'stripe'\n",
            "settings.toml#/payments/retries",
            "[payments]\nretries = 6\ngateway = 'stripe'\n",
            '[payments]\ngateway = "adyen"  # ops\nretries   =   3\n',
        ),
    ],
    ids=["json", "yaml", "toml"],
)
def test_config_memory_goes_stale_only_when_its_node_value_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    content: str,
    locator: str,
    semantic_edit: str,
    cosmetic_edit: str,
) -> None:
    repository = _repository(tmp_path, {name: content})
    _capture_and_stop(repository, monkeypatch, "config", locator)
    assert _statuses(repository) == {CLAIM: "active"}

    (repository / name).write_text(cosmetic_edit, encoding="utf-8")
    assert dream(repository).marked_stale == []
    assert _statuses(repository) == {CLAIM: "active"}

    (repository / name).write_text(semantic_edit, encoding="utf-8")
    assert len(dream(repository).marked_stale) == 1
    assert _statuses(repository) == {CLAIM: "stale"}


def test_schema_memory_tracks_one_openapi_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = (
        "openapi: 3.1.0\npaths:\n  /charges:\n    post:\n      responses:\n"
        "        '201': {description: created}\n"
    )
    repository = _repository(tmp_path, {"api/openapi.yaml": spec})
    _capture_and_stop(
        repository, monkeypatch, "schema", "api/openapi.yaml#/paths/~1charges/post/responses/201"
    )

    (repository / "api/openapi.yaml").write_text(
        spec.replace("created", "charge created"), encoding="utf-8"
    )

    assert len(dream(repository).marked_stale) == 1
    assert _statuses(repository) == {CLAIM: "stale"}


def test_config_locator_addresses_array_items_by_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path, {"settings.json": SETTINGS_JSON})
    _capture_and_stop(repository, monkeypatch, "config", "settings.json#/regions/1")

    (repository / "settings.json").write_text(
        SETTINGS_JSON.replace('"us"', '"ap"'), encoding="utf-8"
    )

    assert len(dream(repository).marked_stale) == 1


@pytest.mark.parametrize(
    ("files", "evidence_type", "locator", "message"),
    [
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#/payments/timeout",
            "evidence[0]: evidence locator not found: settings.json#/payments/timeout",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#/regions/01",
            "evidence[0]: evidence locator not found: settings.json#/regions/01",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#/regions/9",
            "evidence[0]: evidence locator not found: settings.json#/regions/9",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#/payments/retries/deeper",
            "evidence[0]: evidence locator not found: settings.json#/payments/retries/deeper",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json",
            "invalid document locator: settings.json",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#payments",
            "evidence[0]: document locator must use path#/exact/node: settings.json#payments",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "config",
            "settings.json#/payments~2x",
            "evidence[0]: invalid JSON pointer in evidence locator: settings.json#/payments~2x",
        ),
        (
            {"settings.json": SETTINGS_JSON},
            "schema",
            "settings.json#/payments",
            "evidence[0]: schema locator must target a JSON Schema or OpenAPI document: settings.json",
        ),
        (
            {"schema.toml": "openapi = '3.1.0'\n"},
            "schema",
            "schema.toml#/openapi",
            "evidence[0]: unsupported schema format: .toml",
        ),
        (
            {"settings.ini": "[payments]\nretries=3\n"},
            "config",
            "settings.ini#/payments",
            "evidence[0]: unsupported config format: .ini",
        ),
        (
            {"settings.json": "{broken\n"},
            "config",
            "settings.json#/payments",
            "evidence[0]: invalid document:",
        ),
    ],
    ids=[
        "missing-key",
        "leading-zero-index",
        "index-out-of-range",
        "scalar-has-no-children",
        "no-pointer",
        "relative-pointer",
        "bad-escape",
        "not-a-schema",
        "toml-schema",
        "unsupported-format",
        "unparsable",
    ],
)
def test_capture_rejects_imprecise_document_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
    evidence_type: str,
    locator: str,
    message: str,
) -> None:
    repository = _repository(tmp_path, files)
    _turn(repository)
    for name, content in files.items():
        (repository / name).write_text(content + "\n", encoding="utf-8")

    result = _capture(
        repository, monkeypatch, [{"type": evidence_type, "role": "primary", "locator": locator}]
    )

    assert message in _error_text(result)
    assert not (repository / ".agents/skills/.agent-memory/memories").exists()


@pytest.mark.parametrize(
    "locator",
    ["../outside.json#/a", "/etc/hosts.json#/a"],
    ids=["parent-directory", "absolute"],
)
def test_capture_rejects_document_evidence_outside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, locator: str
) -> None:
    repository = _repository(tmp_path, {"settings.json": SETTINGS_JSON})
    _turn(repository)

    result = _capture(
        repository, monkeypatch, [{"type": "config", "role": "primary", "locator": locator}]
    )

    assert "must stay inside the repository" in _error_text(result)

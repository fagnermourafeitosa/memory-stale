"""Typed, deterministic evidence resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import tomli
import yaml

from memory_stale.symbol_index import SymbolIndexer, SymbolIndexError

EVIDENCE_TYPES = frozenset({"symbol", "config", "schema", "test"})
EVIDENCE_ROLES = frozenset({"primary", "supporting"})


class EvidenceError(ValueError):
    """Raised when typed evidence cannot be represented or resolved precisely."""


@dataclass(frozen=True, order=True)
class EvidenceItem:
    """A fingerprinted source that supports one memory revision."""

    type: str
    role: str
    locator: str
    fingerprint: str

    @property
    def key(self) -> str:
        return f"{self.type}:{self.locator}"


def parse_items(value: object) -> tuple[tuple[str, str, str], ...]:
    """Validate MCP evidence input before resolving any item."""
    if not isinstance(value, list) or not value:
        raise EvidenceError("evidence is required")
    parsed: list[tuple[str, str, str]] = []
    keys: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise EvidenceError("evidence items must be objects")
        if set(raw) != {"type", "role", "locator"}:
            raise EvidenceError("evidence items require only type, role, and locator")
        item_type = _required(raw, "type")
        role = _required(raw, "role")
        locator = _required(raw, "locator")
        if item_type not in EVIDENCE_TYPES:
            raise EvidenceError(f"unsupported evidence type: {item_type}")
        if role not in EVIDENCE_ROLES:
            raise EvidenceError(f"unsupported evidence role: {role}")
        key = (item_type, locator)
        if key in keys:
            raise EvidenceError(f"duplicate evidence item: {item_type}:{locator}")
        keys.add(key)
        parsed.append((item_type, role, locator))
    if not any(role == "primary" for _item_type, role, _locator in parsed):
        raise EvidenceError("evidence requires at least one primary item")
    return tuple(parsed)


def resolve_item(repository: Path, item_type: str, role: str, locator: str) -> EvidenceItem:
    """Resolve one exact evidence locator into its canonical fingerprint."""
    if item_type not in EVIDENCE_TYPES or role not in EVIDENCE_ROLES:
        raise EvidenceError(f"invalid evidence item: {item_type}:{role}")
    if item_type in {"symbol", "test"}:
        try:
            fingerprint = SymbolIndexer(repository).signature(locator)
        except SymbolIndexError as error:
            raise EvidenceError(str(error)) from error
    else:
        fingerprint = _document_fingerprint(repository, item_type, locator)
    return EvidenceItem(item_type, role, locator, fingerprint)


def resolve_stored_item(repository: Path, item: EvidenceItem) -> str:
    """Resolve persisted evidence without changing its role or identity."""
    return resolve_item(repository, item.type, item.role, item.locator).fingerprint


def _required(raw: dict[object, object], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"evidence {field} is required")
    return value


def _document_fingerprint(repository: Path, item_type: str, locator: str) -> str:
    path_text, pointer = _document_locator(locator)
    path = _safe_path(repository, path_text)
    allowed = {".json", ".yaml", ".yml", ".toml"}
    if item_type == "schema":
        allowed -= {".toml"}
    if path.suffix.lower() not in allowed:
        raise EvidenceError(f"unsupported {item_type} format: {path.suffix or '<none>'}")
    if not path.is_file():
        raise EvidenceError(f"evidence file not found: {path_text}")
    document = _parse_document(path)
    if item_type == "schema" and not _is_schema_document(document):
        raise EvidenceError(
            f"schema locator must target a JSON Schema or OpenAPI document: {path_text}"
        )
    node = _select_pointer(document, pointer, locator)
    canonical = json.dumps(_json_value(node, locator), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _document_locator(locator: str) -> tuple[str, str]:
    path_text, separator, pointer = locator.partition("#")
    if not separator or not path_text or not pointer or not pointer.startswith("/"):
        raise EvidenceError(f"document locator must use path#/exact/node: {locator}")
    return path_text, pointer


def _safe_path(repository: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise EvidenceError(f"evidence path must stay inside the repository: {path_text}")
    return repository / path


def _parse_document(path: Path) -> object:
    try:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".toml":
            with path.open("rb") as stream:
                return tomli.load(stream)
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise EvidenceError(f"invalid document: {path}") from error


def _is_schema_document(document: object) -> bool:
    return isinstance(document, dict) and (
        isinstance(document.get("$schema"), str) or isinstance(document.get("openapi"), str)
    )


def _select_pointer(document: object, pointer: str, locator: str) -> object:
    current = document
    for raw_segment in pointer[1:].split("/"):
        segment = _unescape_pointer(raw_segment, locator)
        if isinstance(current, dict):
            if segment not in current:
                raise EvidenceError(f"evidence locator not found: {locator}")
            current = current[segment]
        elif isinstance(current, list):
            if not segment.isdigit() or (len(segment) > 1 and segment.startswith("0")):
                raise EvidenceError(f"evidence locator not found: {locator}")
            index = int(segment)
            if index >= len(current):
                raise EvidenceError(f"evidence locator not found: {locator}")
            current = current[index]
        else:
            raise EvidenceError(f"evidence locator not found: {locator}")
    return current


def _unescape_pointer(segment: str, locator: str) -> str:
    result = ""
    index = 0
    while index < len(segment):
        if segment[index] != "~":
            result += segment[index]
            index += 1
            continue
        if index + 1 == len(segment) or segment[index + 1] not in {"0", "1"}:
            raise EvidenceError(f"invalid JSON pointer in evidence locator: {locator}")
        result += "~" if segment[index + 1] == "0" else "/"
        index += 2
    return result


def _json_value(value: object, locator: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise EvidenceError(f"non-canonical value in evidence locator: {locator}")
        return value
    if isinstance(value, list):
        return [_json_value(item, locator) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        mapping = cast(dict[str, object], value)
        return {key: _json_value(item, locator) for key, item in mapping.items()}
    raise EvidenceError(f"non-canonical value in evidence locator: {locator}")

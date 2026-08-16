"""Deterministic project evidence path policy."""

from __future__ import annotations

from pathlib import PurePosixPath


def is_ignored_project_path(path_text: str) -> bool:
    """Return whether a repository-relative path is operational infrastructure."""
    return PurePosixPath(path_text).parts[:1] == (".agents",)


def evidence_path(item_type: str, locator: str) -> str:
    """Return the repository-relative file portion of an evidence locator."""
    if item_type in {"symbol", "test"}:
        return locator.rpartition(":")[0]
    if item_type in {"config", "schema"}:
        return locator.partition("#")[0]
    return locator

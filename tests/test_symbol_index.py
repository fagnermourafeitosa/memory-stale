from pathlib import Path

import pytest

from memory_stale.evidence import resolve_item
from memory_stale.symbol_index import (
    InvalidSyntaxError,
    SymbolIndexer,
    SymbolNotFoundError,
    UnsupportedLanguageError,
)

CASES = [
    (
        "sample.py",
        "def compute():\n    return 1\n",
        "# note\ndef compute():\n  return 1\n",
        "def compute():\n    return 2\n",
    ),
    (
        "sample.js",
        "function compute() { return 1; }\n",
        "// note\nfunction compute() {\n return 1;\n}\n",
        "function compute() { return 2; }\n",
    ),
    (
        "sample.ts",
        "function compute(): number { return 1; }\n",
        "// note\nfunction compute(): number {\n return 1;\n}\n",
        "function compute(): number { return 2; }\n",
    ),
    (
        "sample.go",
        "package sample\nfunc compute() int { return 1 }\n",
        "package sample\n// note\nfunc compute() int {\n return 1\n}\n",
        "package sample\nfunc compute() int { return 2 }\n",
    ),
    (
        "Sample.java",
        "class Sample { int compute() { return 1; } }\n",
        "class Sample { // note\n int compute() {\n  return 1;\n }\n}\n",
        "class Sample { int compute() { return 2; } }\n",
    ),
    (
        "sample.kt",
        "fun compute(): Int { return 1 }\n",
        "// note\nfun compute(): Int {\n return 1\n}\n",
        "fun compute(): Int { return 2 }\n",
    ),
    (
        "sample.rs",
        "fn compute() -> i32 { 1 }\n",
        "// note\nfn compute() -> i32 {\n 1\n}\n",
        "fn compute() -> i32 { 2 }\n",
    ),
]


@pytest.mark.parametrize(("filename", "initial", "trivia", "semantic"), CASES)
def test_symbol_signatures_ignore_trivia_but_detect_semantic_changes(
    tmp_path: Path, filename: str, initial: str, trivia: str, semantic: str
) -> None:
    path = tmp_path / filename
    path.write_text(initial, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    first = indexer.signature(f"{filename}:compute")

    path.write_text(trivia, encoding="utf-8")
    assert indexer.signature(f"{filename}:compute") == first

    path.write_text(semantic, encoding="utf-8")
    assert indexer.signature(f"{filename}:compute") != first


@pytest.mark.parametrize(("filename", "initial", "trivia", "semantic"), CASES)
def test_test_evidence_uses_each_supported_structural_grammar(
    tmp_path: Path, filename: str, initial: str, trivia: str, semantic: str
) -> None:
    path = tmp_path / filename
    path.write_text(initial, encoding="utf-8")
    first = resolve_item(tmp_path, "test", "supporting", f"{filename}:compute").fingerprint

    path.write_text(trivia, encoding="utf-8")
    assert resolve_item(tmp_path, "test", "supporting", f"{filename}:compute").fingerprint == first

    path.write_text(semantic, encoding="utf-8")
    assert resolve_item(tmp_path, "test", "supporting", f"{filename}:compute").fingerprint != first


def test_unsupported_language_is_rejected_without_file_fallback(tmp_path: Path) -> None:
    (tmp_path / "sample.rb").write_text("def compute = 1\n", encoding="utf-8")

    with pytest.raises(UnsupportedLanguageError, match="unsupported language"):
        SymbolIndexer(tmp_path).signature("sample.rb:compute")


def test_missing_invalid_and_qualified_symbols_are_unambiguous(tmp_path: Path) -> None:
    indexer = SymbolIndexer(tmp_path)
    with pytest.raises(SymbolNotFoundError, match="file not found"):
        indexer.signature("missing.py:compute")
    (tmp_path / "broken.py").write_text("def compute(:\n", encoding="utf-8")
    with pytest.raises(InvalidSyntaxError, match="invalid syntax"):
        indexer.signature("broken.py:compute")
    (tmp_path / "service.py").write_text(
        "class Service:\n    def compute(self):\n        return 1\n", encoding="utf-8"
    )
    assert indexer.signature("service.py:Service.compute")

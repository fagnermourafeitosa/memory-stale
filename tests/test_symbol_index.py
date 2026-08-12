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


@pytest.mark.parametrize(
    ("filename", "literal_source", "expression_source"),
    [
        ("service.py", "def compute():\n    return 1\n", "def compute():\n    return 2 - 1\n"),
        (
            "service.js",
            "function compute() { return 1; }\n",
            "function compute() { return 2 - 1; }\n",
        ),
        (
            "service.ts",
            "function compute(): number { return 1; }\n",
            "function compute(): number { return 2 - 1; }\n",
        ),
        (
            "service.go",
            "package service\nfunc compute() int { return 1 }\n",
            "package service\nfunc compute() int { return 2 - 1 }\n",
        ),
        (
            "Service.java",
            "class Service { int compute() { return 1; } }\n",
            "class Service { int compute() { return 2 - 1; } }\n",
        ),
        (
            "service.kt",
            "fun compute(): Int { return 1 }\n",
            "fun compute(): Int { return 2 - 1 }\n",
        ),
        ("service.rs", "fn compute() -> i32 { 1 }\n", "fn compute() -> i32 { 2 - 1 }\n"),
    ],
)
def test_symbol_signature_preserves_a_closed_literal_subtraction(
    tmp_path: Path, filename: str, literal_source: str, expression_source: str
) -> None:
    path = tmp_path / filename
    path.write_text(literal_source, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    literal_signature = indexer.signature(f"{filename}:compute")

    path.write_text(expression_source, encoding="utf-8")

    assert indexer.signature(f"{filename}:compute") == literal_signature


def test_symbol_signature_preserves_neutral_python_integer_addition(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text("def compute():\n    return 1\n", encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    literal_signature = indexer.signature("service.py:compute")

    path.write_text("def compute():\n    return 1 + 0\n", encoding="utf-8")

    assert indexer.signature("service.py:compute") == literal_signature


def test_symbol_signature_preserves_double_python_boolean_negation(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text("def compute():\n    return True\n", encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    literal_signature = indexer.signature("service.py:compute")

    path.write_text("def compute():\n    return not not True\n", encoding="utf-8")

    assert indexer.signature("service.py:compute") == literal_signature


def test_symbol_signature_preserves_single_python_tuple_item_selection(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text("def compute():\n    return 1\n", encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    literal_signature = indexer.signature("service.py:compute")

    path.write_text("def compute():\n    return (1,)[0]\n", encoding="utf-8")

    assert indexer.signature("service.py:compute") == literal_signature


def test_symbol_signature_preserves_python_literal_conditional(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text("def compute():\n    return 1\n", encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    literal_signature = indexer.signature("service.py:compute")

    path.write_text("def compute():\n    return 1 if True else 2\n", encoding="utf-8")

    assert indexer.signature("service.py:compute") == literal_signature


@pytest.mark.parametrize(
    ("filename", "original_source", "renamed_source"),
    [
        (
            "service.py",
            "def increment(x):\n    result = x + 1\n    return result\n",
            "def increment(x):\n    value = x + 1\n    return value\n",
        ),
        (
            "service.js",
            "function increment(x) { const result = x + 1; return result; }\n",
            "function increment(x) { const value = x + 1; return value; }\n",
        ),
        (
            "service.ts",
            "function increment(x: number): number { const result = x + 1; return result; }\n",
            "function increment(x: number): number { const value = x + 1; return value; }\n",
        ),
        (
            "service.go",
            "package service\nfunc increment(x int) int { result := x + 1; return result }\n",
            "package service\nfunc increment(x int) int { value := x + 1; return value }\n",
        ),
        (
            "Service.java",
            "class Service { int increment(int x) { int result = x + 1; return result; } }\n",
            "class Service { int increment(int x) { int value = x + 1; return value; } }\n",
        ),
        (
            "service.kt",
            "fun increment(x: Int): Int { val result = x + 1; return result }\n",
            "fun increment(x: Int): Int { val value = x + 1; return value }\n",
        ),
        (
            "service.rs",
            "fn increment(x: i32) -> i32 { let result = x + 1; result }\n",
            "fn increment(x: i32) -> i32 { let value = x + 1; value }\n",
        ),
    ],
)
def test_symbol_signature_preserves_strictly_local_binding_renames(
    tmp_path: Path, filename: str, original_source: str, renamed_source: str
) -> None:
    path = tmp_path / filename
    path.write_text(original_source, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    original_signature = indexer.signature(f"{filename}:increment")

    path.write_text(renamed_source, encoding="utf-8")

    assert indexer.signature(f"{filename}:increment") == original_signature


def test_symbol_signature_keeps_captured_python_binding_names_significant(tmp_path: Path) -> None:
    path = tmp_path / "service.py"
    path.write_text(
        "def compute():\n"
        "    result = 1\n"
        "    def nested():\n"
        "        return result\n"
        "    return nested()\n",
        encoding="utf-8",
    )
    indexer = SymbolIndexer(tmp_path)
    original_signature = indexer.signature("service.py:compute")

    path.write_text(
        "def compute():\n"
        "    value = 1\n"
        "    def nested():\n"
        "        return value\n"
        "    return nested()\n",
        encoding="utf-8",
    )

    assert indexer.signature("service.py:compute") != original_signature


@pytest.mark.parametrize(
    ("original_source", "changed_source"),
    [
        ("def compute():\n    return 1\n", "def compute():\n    return 2 - 0\n"),
        ("def compute():\n    return 1\n", "def compute():\n    return identity(1)\n"),
        ("def compute(result):\n    return result\n", "def compute(value):\n    return value\n"),
        (
            "def compute(item):\n    result = item.result\n    return result\n",
            "def compute(item):\n    value = item.value\n    return value\n",
        ),
    ],
)
def test_symbol_signature_keeps_unsupported_or_observable_python_changes_significant(
    tmp_path: Path, original_source: str, changed_source: str
) -> None:
    path = tmp_path / "service.py"
    path.write_text(original_source, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    original_signature = indexer.signature("service.py:compute")

    path.write_text(changed_source, encoding="utf-8")

    assert indexer.signature("service.py:compute") != original_signature


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

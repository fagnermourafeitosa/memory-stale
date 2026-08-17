from pathlib import Path

import pytest

from memory_stale.evidence import resolve_item
from memory_stale.symbol_index import (
    InvalidSyntaxError,
    StaticDependency,
    SymbolIndexer,
    SymbolNotFoundError,
    UnsupportedLanguageError,
)


@pytest.mark.parametrize(
    ("filename", "source", "caller", "dependency"),
    [
        (
            "service.py",
            "def policy():\n    return True\n\n\ndef login():\n    return policy()\n",
            "login",
            "policy",
        ),
        (
            "service.js",
            "function policy(){return true;} function login(){return policy();}\n",
            "login",
            "policy",
        ),
        (
            "service.ts",
            "function policy(): boolean{return true;} "
            "function login(): boolean{return policy();}\n",
            "login",
            "policy",
        ),
        (
            "service.go",
            "package service\nfunc policy() bool{return true}\n"
            "func login() bool{return policy()}\n",
            "login",
            "policy",
        ),
        (
            "Service.java",
            "class Service { static boolean policy(){return true;} "
            "static boolean login(){return policy();}}\n",
            "Service.login",
            "Service.policy",
        ),
        (
            "service.kt",
            "fun policy(): Boolean = true\nfun login(): Boolean = policy()\n",
            "login",
            "policy",
        ),
        (
            "service.rs",
            "fn policy() -> bool { true } fn login() -> bool { policy() }\n",
            "login",
            "policy",
        ),
    ],
)
def test_direct_call_dependencies_are_resolved_in_each_supported_grammar(
    tmp_path: Path, filename: str, source: str, caller: str, dependency: str
) -> None:
    (tmp_path / filename).write_text(source, encoding="utf-8")

    assert SymbolIndexer(tmp_path).static_dependencies(f"{filename}:{caller}") == (
        StaticDependency("calls", f"{filename}:{dependency}"),
    )


@pytest.mark.parametrize(
    ("filename", "source", "reader", "declaration"),
    [
        ("limits.py", "LIMIT = 3\n\ndef retry():\n    return LIMIT\n", "retry", "LIMIT"),
        (
            "limits.js",
            "const LIMIT=3; function retry(){return LIMIT;}\n",
            "retry",
            "LIMIT",
        ),
        (
            "limits.ts",
            "const LIMIT:number=3; function retry():number{return LIMIT;}\n",
            "retry",
            "LIMIT",
        ),
        (
            "limits.go",
            "package limits\nconst LIMIT=3\nfunc retry() int{return LIMIT}\n",
            "retry",
            "LIMIT",
        ),
        (
            "Limits.java",
            "class Limits { static final int LIMIT=3; static int retry(){return LIMIT;}}\n",
            "Limits.retry",
            "Limits.LIMIT",
        ),
        (
            "limits.kt",
            "const val LIMIT: Int = 3\nfun retry(): Int = LIMIT\n",
            "retry",
            "LIMIT",
        ),
        (
            "limits.rs",
            "const LIMIT:i32=3; fn retry()->i32{LIMIT}\n",
            "retry",
            "LIMIT",
        ),
    ],
)
def test_named_read_dependencies_are_resolved_in_each_supported_grammar(
    tmp_path: Path, filename: str, source: str, reader: str, declaration: str
) -> None:
    (tmp_path / filename).write_text(source, encoding="utf-8")

    assert SymbolIndexer(tmp_path).static_dependencies(f"{filename}:{reader}") == (
        StaticDependency("reads", f"{filename}:{declaration}"),
    )


@pytest.mark.parametrize(
    ("caller_file", "dependency_file", "caller_source", "dependency_source"),
    [
        (
            "app.js",
            "policy.js",
            'import { allow as permitted } from "./policy.js"; '
            "export function login(){return permitted();}\n",
            "export function allow(){return true;}\n",
        ),
        (
            "app.ts",
            "policy.ts",
            'import { allow as permitted } from "./policy"; '
            "export function login():boolean{return permitted();}\n",
            "export function allow():boolean{return true;}\n",
        ),
    ],
)
def test_relative_named_import_calls_resolve_only_one_repository_symbol(
    tmp_path: Path,
    caller_file: str,
    dependency_file: str,
    caller_source: str,
    dependency_source: str,
) -> None:
    (tmp_path / caller_file).write_text(caller_source, encoding="utf-8")
    (tmp_path / dependency_file).write_text(dependency_source, encoding="utf-8")

    assert SymbolIndexer(tmp_path).static_dependencies(f"{caller_file}:login") == (
        StaticDependency("calls", f"{dependency_file}:allow"),
    )


def test_ambiguous_python_import_does_not_create_a_dependency(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (tmp_path / "policy.py").write_text("def allow():\n    return True\n", encoding="utf-8")
    (package / "policy.py").write_text("def allow():\n    return False\n", encoding="utf-8")
    (package / "app.py").write_text(
        "from policy import allow\n\ndef login():\n    return allow()\n",
        encoding="utf-8",
    )

    assert SymbolIndexer(tmp_path).static_dependencies("package/app.py:login") == ()


def test_dynamic_receiver_does_not_create_a_dependency(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "def login(policy):\n    return policy.allow()\n",
        encoding="utf-8",
    )

    assert SymbolIndexer(tmp_path).static_dependencies("app.py:login") == ()


@pytest.mark.parametrize(
    ("filename", "source", "locator"),
    [
        ("app.py", "def login(policy):\n    return policy.allow()\n", "login"),
        ("app.js", "function login(policy){return policy.allow();}\n", "login"),
        (
            "app.ts",
            "interface Policy { allow(): boolean } "
            "function login(policy:Policy):boolean{return policy.allow();}\n",
            "login",
        ),
        (
            "app.go",
            "package app\ntype Policy interface { Allow() bool }\n"
            "func login(policy Policy) bool{return policy.Allow()}\n",
            "login",
        ),
        (
            "App.java",
            "interface Policy { boolean allow(); } "
            "class App { static boolean login(Policy policy){return policy.allow();}}\n",
            "App.login",
        ),
        (
            "app.kt",
            "interface Policy { fun allow(): Boolean; }\n"
            "fun login(policy: Policy): Boolean = policy.allow()\n",
            "login",
        ),
        (
            "app.rs",
            "trait Policy { fn allow(&self)->bool; } "
            "fn login<T:Policy>(policy:T)->bool{policy.allow()}\n",
            "login",
        ),
    ],
)
def test_dynamic_receivers_are_omitted_in_each_supported_grammar(
    tmp_path: Path, filename: str, source: str, locator: str
) -> None:
    (tmp_path / filename).write_text(source, encoding="utf-8")

    assert SymbolIndexer(tmp_path).static_dependencies(f"{filename}:{locator}") == ()


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

SYMBOL_CASES = [
    ("sample.py", "sample.py:compute"),
    ("sample.js", "sample.js:compute"),
    ("sample.ts", "sample.ts:compute"),
    ("sample.go", "sample.go:compute"),
    ("Sample.java", "Sample.java:Sample.compute"),
    ("sample.kt", "sample.kt:compute"),
    ("sample.rs", "sample.rs:compute"),
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
def test_source_signatures_ignore_trivia_but_detect_semantic_changes(
    tmp_path: Path, filename: str, initial: str, trivia: str, semantic: str
) -> None:
    path = tmp_path / filename
    path.write_text(initial, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    first = indexer.source_signature(filename)

    path.write_text(trivia, encoding="utf-8")
    assert indexer.source_signature(filename) == first

    path.write_text(semantic, encoding="utf-8")
    assert indexer.source_signature(filename) != first


@pytest.mark.parametrize(
    ("filename", "initial", "trivia", "semantic", "locator"),
    [(*case, locator) for case, (_symbol_file, locator) in zip(CASES, SYMBOL_CASES, strict=True)],
)
def test_source_symbol_snapshots_ignore_trivia_but_detect_semantic_changes(
    tmp_path: Path, filename: str, initial: str, trivia: str, semantic: str, locator: str
) -> None:
    path = tmp_path / filename
    path.write_text(initial, encoding="utf-8")
    indexer = SymbolIndexer(tmp_path)
    first = indexer.source_symbols(filename)

    assert first[locator] == indexer.signature(locator)

    path.write_text(trivia, encoding="utf-8")
    assert indexer.source_symbols(filename) == first

    path.write_text(semantic, encoding="utf-8")
    assert indexer.source_symbols(filename)[locator] != first[locator]


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

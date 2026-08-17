"""Tree-sitter symbol resolution and canonical signatures."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node, Tree
from tree_sitter_language_pack import PackConfig, get_parser, init

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
}
SYMBOL_TYPES = {
    "function_definition",
    "class_definition",
    "function_declaration",
    "method_definition",
    "class_declaration",
    "function_item",
    "struct_item",
    "method_declaration",
    "type_declaration",
    "object_declaration",
}
INDEXED_SYMBOL_TYPES = SYMBOL_TYPES | {
    "assignment",
    "const_item",
    "const_spec",
    "property_declaration",
    "static_item",
    "variable_declarator",
}
SCOPE_TYPES = {"class_definition", "class_declaration", "struct_item", "object_declaration"}
COMMENT_TYPES = {"comment", "line_comment", "block_comment"}
SIGNATURE_VERSION = "v2"
MAX_NORMALIZED_INTEGER = 2**53 - 1
INTEGER_LITERAL_TYPES = {
    "integer",
    "number",
    "int_literal",
    "decimal_integer_literal",
    "integer_literal",
}
BINARY_EXPRESSION_TYPES = {"binary_operator", "binary_expression", "additive_expression"}
IDENTIFIER_TYPES = {"identifier", "simple_identifier"}
NESTED_SCOPE_TYPES = SYMBOL_TYPES | {
    "lambda",
    "arrow_function",
    "anonymous_function",
    "closure_expression",
}
SAFE_LOCAL_IDENTIFIER_PARENTS = {
    "assignment",
    "variable_declarator",
    "expression_list",
    "short_var_declaration",
    "variable_declaration",
    "let_declaration",
    "binary_operator",
    "binary_expression",
    "additive_expression",
    "return_statement",
    "jump_expression",
    "block",
}


@dataclass(frozen=True, order=True)
class StaticDependency:
    """One uniquely resolved repository-local syntax dependency."""

    relationship: str
    locator: str


class SymbolIndexError(RuntimeError):
    """Base error for symbol indexing failures."""


class UnsupportedLanguageError(SymbolIndexError):
    """Raised when a reference uses no supported grammar."""


class SymbolNotFoundError(SymbolIndexError):
    """Raised when a referenced symbol cannot be resolved."""


class InvalidSyntaxError(SymbolIndexError):
    """Raised when tree-sitter reports invalid syntax."""


class SymbolIndexer:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        package_root = Path(__file__).resolve().parents[2]
        cache = Path(
            os.environ.get(
                "MEMORY_STALE_GRAMMAR_CACHE", package_root / ".venv" / "tree-sitter-cache"
            )
        )
        init(PackConfig(cache_dir=str(cache)))

    def signature(self, ref: str) -> str:
        node, source = self._resolve(ref)
        return self._signature_for(node, source)

    def source_signature(self, path_text: str) -> str:
        """Return a comment- and format-insensitive signature for one source file."""
        tree, source = self._source_tree(path_text)
        canonical = " ".join(self._structural_tokens(tree.root_node, source))
        return f"source-v1:{self._digest(canonical)}"

    def source_symbols(self, path_text: str) -> dict[str, str]:
        """Return unambiguous named symbols in one supported source file."""
        return self._symbols(path_text, include_named_declarations=False)

    def _symbols(self, path_text: str, *, include_named_declarations: bool) -> dict[str, str]:
        tree, source = self._source_tree(path_text)
        candidates: dict[str, list[Node]] = {}

        def visit(node: Node, scope: tuple[str, ...]) -> None:
            name = (
                self._symbol_name(node, source)
                if include_named_declarations or node.type in SYMBOL_TYPES
                else None
            )
            locator = f"{path_text}:{'.'.join((*scope, name))}" if name else None
            if locator is not None:
                candidates.setdefault(locator, []).append(node)
            next_scope = (*scope, name) if name and node.type in SCOPE_TYPES else scope
            for child in node.children:
                visit(child, next_scope)

        visit(tree.root_node, ())
        return {
            locator: self._signature_for(nodes[0], source)
            for locator, nodes in sorted(candidates.items())
            if len(nodes) == 1
        }

    def static_dependencies(self, ref: str) -> tuple[StaticDependency, ...]:
        """Return conservative direct dependencies for one exact code symbol."""
        node, source = self._resolve(ref)
        path_text, _separator, symbol = ref.rpartition(":")
        caller_scope = symbol.rpartition(".")[0]
        candidates: dict[str, set[str]] = {}
        for locator in self._symbols(path_text, include_named_declarations=True):
            target_symbol = locator.rpartition(":")[2]
            target_scope, _dot, target_name = target_symbol.rpartition(".")
            if target_scope == caller_scope:
                candidates.setdefault(target_name, set()).add(locator)
        for name, locator in self._python_imported_symbols(path_text, node, source):
            candidates.setdefault(name, set()).add(locator)
        for name, locator in self._javascript_imported_symbols(path_text, node, source):
            candidates.setdefault(name, set()).add(locator)
        local_names = set(self._local_bindings(node, source))
        parameters = node.child_by_field_name("parameters")
        if parameters is not None:
            local_names.update(
                source[item.start_byte : item.end_byte].decode("utf-8")
                for item in self._walk_nodes(parameters)
                if item.type in IDENTIFIER_TYPES
            )
        dependencies: set[StaticDependency] = set()
        for candidate in self._walk_nodes(node):
            if candidate is not node and self._is_in_nested_scope(candidate, node):
                continue
            if candidate.type not in {"call", "call_expression", "method_invocation"}:
                if candidate.type not in IDENTIFIER_TYPES:
                    continue
                name = source[candidate.start_byte : candidate.end_byte].decode("utf-8")
                if name in local_names or self._is_declaration_identifier(candidate):
                    continue
                if self._is_call_callee(candidate):
                    continue
                locators = candidates.get(name, set())
                if len(locators) == 1:
                    locator = next(iter(locators))
                    if locator != ref:
                        dependencies.add(StaticDependency("reads", locator))
                continue
            callee = candidate.child_by_field_name("function") or candidate.child_by_field_name(
                "name"
            )
            if callee is None:
                callee = next(
                    (child for child in candidate.named_children if child.type in IDENTIFIER_TYPES),
                    None,
                )
            if callee is not None and callee.type in IDENTIFIER_TYPES:
                name = source[callee.start_byte : callee.end_byte].decode("utf-8")
                locators = candidates.get(name, set())
                if len(locators) == 1:
                    locator = next(iter(locators))
                    if locator != ref:
                        dependencies.add(StaticDependency("calls", locator))
        return tuple(sorted(dependencies))

    def _is_call_callee(self, node: Node) -> bool:
        parent = node.parent
        if parent is None or parent.type not in {"call", "call_expression", "method_invocation"}:
            return False
        callee = parent.child_by_field_name("function") or parent.child_by_field_name("name")
        if callee is None:
            callee = next(
                (child for child in parent.named_children if child.type in IDENTIFIER_TYPES), None
            )
        return callee == node

    def _is_declaration_identifier(self, node: Node) -> bool:
        parent = node.parent
        return bool(parent is not None and parent.child_by_field_name("name") == node)

    def _python_imported_symbols(
        self, path_text: str, node: Node, source: bytes
    ) -> tuple[tuple[str, str], ...]:
        if Path(path_text).suffix.lower() != ".py":
            return ()
        root = node
        while root.parent is not None:
            root = root.parent
        imported: list[tuple[str, str]] = []
        for statement in root.named_children:
            if statement.type != "import_from_statement":
                continue
            module_node = statement.child_by_field_name("module_name")
            name_node = statement.child_by_field_name("name")
            if module_node is None or name_node is None:
                continue
            module = source[module_node.start_byte : module_node.end_byte].decode("utf-8")
            imported_name_node = name_node.child_by_field_name("name")
            alias_node = name_node.child_by_field_name("alias")
            if imported_name_node is None:
                imported_name_node = name_node
            imported_name = source[
                imported_name_node.start_byte : imported_name_node.end_byte
            ].decode("utf-8")
            local_name = (
                source[alias_node.start_byte : alias_node.end_byte].decode("utf-8")
                if alias_node is not None
                else imported_name
            )
            relative = Path(*module.split(".")).with_suffix(".py")
            possible = {
                candidate
                for candidate in (
                    self._root / relative,
                    self._root / Path(path_text).parent / relative,
                )
                if candidate.is_file()
            }
            if len(possible) != 1:
                continue
            target_path = next(iter(possible)).relative_to(self._root).as_posix()
            target_locator = f"{target_path}:{imported_name}"
            try:
                self.signature(target_locator)
            except SymbolIndexError:
                continue
            imported.append((local_name, target_locator))
        return tuple(sorted(imported))

    def _javascript_imported_symbols(
        self, path_text: str, node: Node, source: bytes
    ) -> tuple[tuple[str, str], ...]:
        suffix = Path(path_text).suffix.lower()
        if suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            return ()
        root = node
        while root.parent is not None:
            root = root.parent
        imported: list[tuple[str, str]] = []
        for statement in root.named_children:
            if statement.type != "import_statement":
                continue
            source_node = statement.child_by_field_name("source")
            if source_node is None:
                continue
            fragment = next(
                (child for child in source_node.named_children if child.type == "string_fragment"),
                None,
            )
            if fragment is None:
                continue
            module = source[fragment.start_byte : fragment.end_byte].decode("utf-8")
            if not module.startswith(("./", "../")):
                continue
            base = (self._root / Path(path_text).parent / module).resolve()
            try:
                base.relative_to(self._root)
            except ValueError:
                continue
            possible = [base] if base.suffix else [base.with_suffix(item) for item in (suffix,)]
            matches = [candidate for candidate in possible if candidate.is_file()]
            if len(matches) != 1:
                continue
            target_path = matches[0].relative_to(self._root).as_posix()
            for specifier in self._walk_nodes(statement):
                if specifier.type != "import_specifier":
                    continue
                name_node = specifier.child_by_field_name("name")
                alias_node = specifier.child_by_field_name("alias")
                if name_node is None:
                    continue
                imported_name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
                local_name = (
                    source[alias_node.start_byte : alias_node.end_byte].decode("utf-8")
                    if alias_node is not None
                    else imported_name
                )
                target_locator = f"{target_path}:{imported_name}"
                try:
                    self.signature(target_locator)
                except SymbolIndexError:
                    continue
                imported.append((local_name, target_locator))
        return tuple(sorted(imported))

    def _signature_for(self, node: Node, source: bytes) -> str:
        local_bindings = self._local_bindings(node, source)
        canonical = " ".join(self._canonical_tokens(node, source, local_bindings))
        return f"{SIGNATURE_VERSION}:{self._digest(canonical)}"

    def legacy_signature(self, ref: str) -> str:
        """Resolve a pre-normalization structural fingerprint for stored evidence."""
        node, source = self._resolve(ref)
        canonical = " ".join(self._structural_tokens(node, source))
        return self._digest(canonical)

    def _resolve(self, ref: str) -> tuple[Node, bytes]:
        path_text, separator, symbol = ref.rpartition(":")
        if not separator or not path_text or not symbol:
            raise SymbolNotFoundError(f"invalid symbol ref: {ref}")
        path = self._root / path_text
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            raise UnsupportedLanguageError(f"unsupported language: {path.suffix or '<none>'}")
        if not path.is_file():
            raise SymbolNotFoundError(f"file not found: {path_text}")
        source = path.read_bytes()
        tree = get_parser(language).parse(source)
        if tree.root_node.has_error:
            raise InvalidSyntaxError(f"invalid syntax: {path_text}")
        node = self._find_symbol(tree.root_node, source, symbol, ())
        if node is None:
            raise SymbolNotFoundError(f"symbol not found: {ref}")
        return node, source

    def _source_tree(self, path_text: str) -> tuple[Tree, bytes]:
        path = self._root / path_text
        language = LANGUAGES.get(path.suffix.lower())
        if language is None:
            raise UnsupportedLanguageError(f"unsupported language: {path.suffix or '<none>'}")
        if not path.is_file():
            raise SymbolNotFoundError(f"file not found: {path_text}")
        source = path.read_bytes()
        tree = get_parser(language).parse(source)
        if tree.root_node.has_error:
            raise InvalidSyntaxError(f"invalid syntax: {path_text}")
        return tree, source

    def _digest(self, canonical: str) -> str:
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _find_symbol(
        self, node: Node, source: bytes, wanted: str, scope: tuple[str, ...]
    ) -> Node | None:
        name = self._symbol_name(node, source)
        if name and (name == wanted or ".".join((*scope, name)) == wanted):
            return node
        next_scope = (*scope, name) if name and node.type in SCOPE_TYPES else scope
        for child in node.children:
            found = self._find_symbol(child, source, wanted, next_scope)
            if found is not None:
                return found
        return None

    def _symbol_name(self, node: Node, source: bytes) -> str | None:
        if node.type not in INDEXED_SYMBOL_TYPES:
            return None
        if node.type == "assignment":
            if node.parent is None or node.parent.type != "module":
                return None
            left = node.child_by_field_name("left")
            if left is None or left.type not in IDENTIFIER_TYPES:
                return None
            return source[left.start_byte : left.end_byte].decode("utf-8")
        if node.type == "variable_declarator":
            declaration = node.parent
            scope = declaration.parent if declaration is not None else None
            if declaration is None or declaration.type not in {
                "field_declaration",
                "lexical_declaration",
            }:
                return None
            if scope is None or scope.type not in {"class_body", "program"}:
                return None
        elif node.type == "const_spec":
            declaration = node.parent
            scope = declaration.parent if declaration is not None else None
            if (
                declaration is None
                or declaration.type != "const_declaration"
                or scope is None
                or scope.type != "source_file"
            ):
                return None
        elif node.type == "property_declaration":
            if node.parent is None or node.parent.type not in {"source_file", "class_body"}:
                return None
            declaration = next(
                (child for child in node.named_children if child.type == "variable_declaration"),
                None,
            )
            if declaration is None:
                return None
            name_node = next(
                (child for child in declaration.named_children if child.type in IDENTIFIER_TYPES),
                None,
            )
            if name_node is None:
                return None
            return source[name_node.start_byte : name_node.end_byte].decode("utf-8")
        elif node.type in {"const_item", "static_item"}:
            if node.parent is None or node.parent.type != "source_file":
                return None
        name_node = node.child_by_field_name("name")
        if name_node is None:
            name_node = next(
                (child for child in node.named_children if "identifier" in child.type), None
            )
        if name_node is None:
            return None
        return source[name_node.start_byte : name_node.end_byte].decode("utf-8")

    def _canonical_tokens(
        self,
        node: Node,
        source: bytes,
        local_bindings: dict[str, str],
        root: Node | None = None,
    ) -> list[str]:
        if node.type in COMMENT_TYPES:
            return []
        root_node = node if root is None else root
        bindings = {} if node != root_node and node.type in NESTED_SCOPE_TYPES else local_bindings
        if node.type in IDENTIFIER_TYPES:
            token = source[node.start_byte : node.end_byte].decode("utf-8")
            if token in bindings:
                return [bindings[token]]
        conditional_tokens = self._normalized_conditional_tokens(node, source, bindings, root_node)
        if conditional_tokens is not None:
            return conditional_tokens
        tuple_item = self._normalized_tuple_item(node, source)
        if tuple_item is not None:
            return tuple_item
        normalized_integer = self._normalized_integer(node, source)
        if normalized_integer is not None:
            literal_type, value = normalized_integer
            return [f"{literal_type}:{value}"]
        normalized_boolean = self._normalized_boolean(node)
        if normalized_boolean is not None:
            boolean_type, boolean_value = normalized_boolean
            return [f"{boolean_type}:{boolean_value}"]
        if not node.children:
            token = source[node.start_byte : node.end_byte].decode("utf-8")
            return [f"{node.type}:{token}"]
        tokens = [node.type]
        for child in node.children:
            tokens.extend(self._canonical_tokens(child, source, bindings, root_node))
        return tokens

    def _structural_tokens(self, node: Node, source: bytes) -> list[str]:
        if node.type in COMMENT_TYPES:
            return []
        if not node.children:
            token = source[node.start_byte : node.end_byte].decode("utf-8")
            return [f"{node.type}:{token}"]
        tokens = [node.type]
        for child in node.children:
            tokens.extend(self._structural_tokens(child, source))
        return tokens

    def _local_bindings(self, root: Node, source: bytes) -> dict[str, str]:
        declarations: dict[str, list[Node]] = {}
        identifiers: dict[str, list[Node]] = {}
        for node in self._walk_nodes(root):
            if node is not root and self._is_in_nested_scope(node, root):
                continue
            declaration = self._local_declaration(node)
            if declaration is not None:
                name = source[declaration.start_byte : declaration.end_byte].decode("utf-8")
                declarations.setdefault(name, []).append(declaration)
            if node.type in IDENTIFIER_TYPES:
                name = source[node.start_byte : node.end_byte].decode("utf-8")
                identifiers.setdefault(name, []).append(node)
        bindings: dict[str, str] = {}
        for name, declaration_nodes in declarations.items():
            if len(declaration_nodes) != 1:
                continue
            declaration = declaration_nodes[0]
            occurrences = identifiers.get(name, [])
            if not occurrences or any(
                item.start_byte < declaration.start_byte for item in occurrences
            ):
                continue
            if any(
                self._is_in_nested_scope(item, root)
                or item.parent is None
                or item.parent.type not in SAFE_LOCAL_IDENTIFIER_PARENTS
                for item in occurrences
            ):
                continue
            bindings[name] = ""
        return {
            name: f"local:{index}"
            for index, name in enumerate(
                sorted(bindings, key=lambda binding: declarations[binding][0].start_byte)
            )
        }

    def _local_declaration(self, node: Node) -> Node | None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            return left if left is not None and left.type in IDENTIFIER_TYPES else None
        if node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            return name if name is not None and name.type in IDENTIFIER_TYPES else None
        if node.type == "short_var_declaration":
            left = node.child_by_field_name("left")
            if left is None or left.type != "expression_list" or len(left.named_children) != 1:
                return None
            name = left.named_children[0]
            return name if name.type in IDENTIFIER_TYPES else None
        if node.type == "property_declaration":
            variable = next(
                (child for child in node.named_children if child.type == "variable_declaration"),
                None,
            )
            if variable is None or len(variable.named_children) != 1:
                return None
            name = variable.named_children[0]
            return name if name.type in IDENTIFIER_TYPES else None
        if node.type == "let_declaration":
            pattern = node.child_by_field_name("pattern")
            return pattern if pattern is not None and pattern.type in IDENTIFIER_TYPES else None
        return None

    def _walk_nodes(self, node: Node) -> Iterator[Node]:
        yield node
        for child in node.children:
            yield from self._walk_nodes(child)

    def _is_in_nested_scope(self, node: Node, root: Node) -> bool:
        parent = node.parent
        while parent is not None and parent != root:
            if parent.type in NESTED_SCOPE_TYPES:
                return True
            parent = parent.parent
        return False

    def _normalized_integer(self, node: Node, source: bytes) -> tuple[str, int] | None:
        if node.type in INTEGER_LITERAL_TYPES:
            text = source[node.start_byte : node.end_byte].decode("utf-8")
            if text.isascii() and text.isdecimal() and (text == "0" or not text.startswith("0")):
                value = int(text)
                return (node.type, value) if value <= MAX_NORMALIZED_INTEGER else None
            return None
        if node.type not in BINARY_EXPRESSION_TYPES or len(node.children) != 3:
            return None
        left, operator, right = node.children
        if operator.type not in {"+", "-"}:
            return None
        left_literal = self._normalized_integer(left, source)
        right_literal = self._normalized_integer(right, source)
        if left_literal is None or right_literal is None or left_literal[0] != right_literal[0]:
            return None
        if operator.type == "+":
            if right_literal[1] == 0:
                value = left_literal[1]
            elif left_literal[1] == 0:
                value = right_literal[1]
            else:
                return None
        else:
            value = left_literal[1] - right_literal[1]
        return (
            (left_literal[0], value)
            if -MAX_NORMALIZED_INTEGER <= value <= MAX_NORMALIZED_INTEGER
            else None
        )

    def _normalized_boolean(self, node: Node) -> tuple[str, str] | None:
        if node.type == "true":
            return ("true", "True")
        if node.type == "false":
            return ("false", "False")
        if node.type != "not_operator" or len(node.children) != 2:
            return None
        first_operator, nested = node.children
        if first_operator.type != "not" or nested.type != "not_operator":
            return None
        if len(nested.children) != 2 or nested.children[0].type != "not":
            return None
        return self._normalized_boolean(nested.children[1])

    def _normalized_tuple_item(self, node: Node, source: bytes) -> list[str] | None:
        if node.type != "subscript" or len(node.children) != 4:
            return None
        tuple_node, opening_bracket, index, closing_bracket = node.children
        if opening_bracket.type != "[" or closing_bracket.type != "]":
            return None
        if self._normalized_integer(index, source) != ("integer", 0):
            return None
        if tuple_node.type != "tuple" or len(tuple_node.children) != 4:
            return None
        opening_paren, item, comma, closing_paren = tuple_node.children
        if (opening_paren.type, comma.type, closing_paren.type) != ("(", ",", ")"):
            return None
        normalized_integer = self._normalized_integer(item, source)
        if normalized_integer is not None:
            return [f"{normalized_integer[0]}:{normalized_integer[1]}"]
        normalized_boolean = self._normalized_boolean(item)
        if normalized_boolean is not None:
            return [f"{normalized_boolean[0]}:{normalized_boolean[1]}"]
        return None

    def _normalized_conditional_tokens(
        self, node: Node, source: bytes, local_bindings: dict[str, str], root: Node
    ) -> list[str] | None:
        if node.type != "conditional_expression" or len(node.children) != 5:
            return None
        consequence, if_keyword, condition, else_keyword, alternative = node.children
        if if_keyword.type != "if" or else_keyword.type != "else":
            return None
        if condition.type == "true":
            return self._canonical_tokens(consequence, source, local_bindings, root)
        if condition.type == "false":
            return self._canonical_tokens(alternative, source, local_bindings, root)
        return None

"""Tree-sitter symbol resolution and canonical signatures."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from tree_sitter import Node
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

    def _digest(self, canonical: str) -> str:
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _find_symbol(
        self, node: Node, source: bytes, wanted: str, scope: tuple[str, ...]
    ) -> Node | None:
        name_node = node.child_by_field_name("name") if node.type in SYMBOL_TYPES else None
        if name_node is None and node.type in SYMBOL_TYPES:
            name_node = next(
                (child for child in node.named_children if "identifier" in child.type), None
            )
        name = (
            source[name_node.start_byte : name_node.end_byte].decode("utf-8") if name_node else None
        )
        if name and (name == wanted or ".".join((*scope, name)) == wanted):
            return node
        next_scope = (*scope, name) if name and node.type in SCOPE_TYPES else scope
        for child in node.children:
            found = self._find_symbol(child, source, wanted, next_scope)
            if found is not None:
                return found
        return None

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

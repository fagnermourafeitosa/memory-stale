"""Tree-sitter symbol resolution and canonical signatures."""

from __future__ import annotations

import hashlib
import os
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
        plugin_root = Path(__file__).resolve().parents[2]
        cache = Path(
            os.environ.get(
                "MEMORY_STALE_GRAMMAR_CACHE", plugin_root / ".venv" / "tree-sitter-cache"
            )
        )
        init(PackConfig(cache_dir=str(cache)))

    def signature(self, ref: str) -> str:
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
        canonical = " ".join(self._canonical_tokens(node, source))
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

    def _canonical_tokens(self, node: Node, source: bytes) -> list[str]:
        if node.type in COMMENT_TYPES:
            return []
        if not node.children:
            token = source[node.start_byte : node.end_byte].decode("utf-8")
            return [f"{node.type}:{token}"]
        tokens = [node.type]
        for child in node.children:
            tokens.extend(self._canonical_tokens(child, source))
        return tokens

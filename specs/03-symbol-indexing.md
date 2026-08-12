# 03 — Multilanguage tree-sitter indexing

## Problem Statement

Memory must track symbols in every supported project without being invalidated by formatting and without an imprecise fallback.

## Solution

Create tree-sitter indexers that resolve symbols and produce canonical structural signatures.

## User Stories

1. As a developer, I want to track equivalent functions and classes across different languages.
2. As a developer, I want to edit a comment without making memory stale.
3. As a user, I want a clear error for an unsupported language.

## Implementation Decisions

- V1: TypeScript, JavaScript, Python, Go, Java, Kotlin, and Rust.
- A signature includes structure and real tokens while ignoring whitespace and comments.
- A changed, removed, or renamed symbol, or a removed file, produces an unambiguous result.
- A language without a grammar rejects capture and never degrades to a whole-file fallback.
- A common interface allows grammars to be added without changing the lifecycle.

## Testing Decisions

- Seam confirmed by continuous execution authorization: the indexer's public interface receives a Git root and a `path:symbol` ref and returns a signature or structured error; real fixtures exercise every grammar.
- Provide per-language fixtures for resolution, semantic changes, and comment or formatting changes.
- Test a missing symbol, invalid parser input, and a missing file.
- Test that trivia produces the same hash while logic, signature, identifier, or literal changes produce a different hash.

## Out of Scope

- Supporting additional languages or tolerating broken syntax.

## Further Notes

- This module does not decide whether a claim is relevant; it only establishes ref state.

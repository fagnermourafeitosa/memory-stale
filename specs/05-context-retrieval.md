# 05 — Context retrieval

## Problem Statement

Codex must receive a small number of useful memories before a task without stale context, embeddings, or the cost of another model.

## Solution

Rank active memories by structural match and BM25 within a configurable budget.

## User Stories

1. As Codex, I want to receive a related decision before changing code.
2. As a user, I want stale memory never to be treated as fact.
3. As a maintainer, I want ranking to be auditable and configurable.

## Implementation Decisions

- Filter for `active` before any ranking.
- Priority: exact path or symbol match, BM25 over claim and durability reason, then a boost for related refs.
- No embeddings in V1.
- Default budget: 1,500 tokens; configurable.
- The result is `additionalContext` from `UserPromptSubmit`.

## Testing Decisions

- Seam confirmed by continuous authorization: the public retrieval function receives a corpus, prompt, and budget and returns the exact injectable context; integration is observed through the real `UserPromptSubmit` command.
- Test stale filtering, exact match above text match, BM25 ranking, and budget truncation.
- Test an empty corpus and a prompt with no result.

## Out of Scope

- Semantic search, a vector database, and injection of the entire memory base.

## Further Notes

- The local index is derived; Markdown remains the source of truth.

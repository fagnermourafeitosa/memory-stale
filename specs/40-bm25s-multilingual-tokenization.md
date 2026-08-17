# Spec 40: BM25S and Multilingual Stemmed Tokenization

## Problem Statement

Memory Stale currently relies on naive Unicode regex splitting for word tokenization across natural language claims, durability reasons, and retrieval terms. It lacks language-specific stemming and stopword filtering. In natural language texts—such as Portuguese or English claims—words with different grammatical inflections, plurals, or conjugations (e.g., "validates" vs "validating", "autenticação" vs "autenticações") fail to match lexically unless the prompt reproduces the exact token string.

Additionally, code locators and natural language claims require different tokenization strategies: applying linguistic stemmers to code paths or symbol names risks corrupting exact code identifiers, while failing to stem natural language prose harms recall.

## Solution

Adopt the high-performance `bm25s` retrieval engine with `PyStemmer` (Snowball) support to enable language-aware stemmed tokenization for natural language fields.

1. **Host-Declared Language Metadata**: The host agent optionally supplies `language` (e.g., `"pt"`, `"en"`, `"es"`) during semantic capture via `memory.capture`. The runtime records this in the OKF Markdown frontmatter under `memory_stale.language`. Existing or untagged memories default to `"en"`.
2. **Hybrid Tokenization Pipeline**:
   - Natural language fields (`claim`, `durability_reason`, `retrieval_terms`) are tokenized and stemmed according to the memory's declared language.
   - Code locators (`evidence.locator`) are tokenized structurally (preserving path segments, file extensions, camelCase, and snake_case) without natural language stemming.
3. **Multi-Field Weighted BM25 Scoring**:
   - Separate in-memory `bm25s.BM25` index instances are evaluated per field (`claim`, `durability_reason`, `locator`, `retrieval_terms`).
   - Field scores are combined using the calibrated weights (`CLAIM_WEIGHT = 1.0`, `DURABILITY_REASON_WEIGHT = 0.5`, `LOCATOR_WEIGHT = 2.0`, `RETRIEVAL_TERMS_WEIGHT = 0.75`).
   - Exact locator matching maintains its deterministic `100.0` boost, and existing score thresholds (`MINIMUM_LEXICAL_SCORE = 0.25`, `MINIMUM_RELATIVE_SCORE = 0.5`, `top_k`, `context_budget`) remain intact.

## User Stories

1. As a Portuguese-speaking developer, I want my Portuguese queries to match inflected forms of words in stored Portuguese claims (e.g., "autenticações" matches "autenticação"), so that relevant context is retrieved without requiring identical grammar.
2. As an English-speaking developer, I want English stemming to match verb and noun variants in stored claims (e.g., "retries" matches "retry"), so that query formulation is flexible.
3. As a developer, I want code locators (e.g., `src/auth.py:AuthService.login`) to be tokenized structurally without linguistic stemming, so that code references remain exact.
4. As a host agent calling `memory.capture`, I want to supply a `language` parameter matching the user prompt, so that the memory is indexed with the appropriate stemmer.
5. As a maintainer, I want memories lacking a `language` field to default gracefully to `"en"`, so that existing memory repositories remain fully backward compatible.
6. As a maintainer, I want `UserPromptSubmit` to tokenize prompt queries against candidate document stemmers, so that multi-language repositories can retrieve matching active context.
7. As a maintainer, I want BM25 scoring across fields (`claim`, `durability_reason`, `locator`, `retrieval_terms`) to preserve their configured linear weights, so that high-value fields dominate candidate ranking.
8. As a maintainer, I want exact locator matches to continue receiving a `100.0` score boost, so that direct code references bypass lexical uncertainty.
9. As a maintainer, I want score pruning gates (`MINIMUM_LEXICAL_SCORE = 0.25` and `MINIMUM_RELATIVE_SCORE = 0.5`) to operate on aggregated BM25 scores, so that weak or noisy distractors are excluded.
10. As a maintainer, I want `bm25s` and `PyStemmer` managed through `uv` in `pyproject.toml`, keeping the isolated environment reproducible.
11. As an evaluation maintainer, I want the 100-trial repository benchmark recalibrated and documented upon implementation, so that empirical accuracy metrics remain verifiable.

## Implementation Decisions

- **Dependencies**: Add `bm25s` and `PyStemmer` to `pyproject.toml` runtime dependencies using `uv`.
- **MCP Protocol Update**: Extend the `memory.capture` tool schema with an optional `language: str = "en"` parameter (valid ISO language codes such as `"en"`, `"pt"`, `"es"`, `"fr"`, `"de"`).
- **OKF Document Schema**: Add `language` under the `memory_stale` extension in the YAML frontmatter of memory files. When missing from disk, deserialize with default `"en"`.
- **Hybrid Tokenization Engine**:
  - Implement language-aware tokenization and Snowball stemming via `bm25s.tokenize(..., stopwords=..., stemmer=...)` for `claim`, `durability_reason`, and `retrieval_terms`.
  - Maintain specialized code component extraction (`_locator_tokens`) for `evidence.locator` (splitting camelCase, snake_case, paths, and punctuation) without applying linguistic stemmers.
- **Multi-Field BM25 Scoring**:
  - Build separate in-memory `bm25s.BM25` index instances for each field across active memories during `retrieve(...)`.
  - Calculate scores per field and compute the weighted linear sum:
    $$\text{Score} = w_{\text{claim}} \cdot S_{\text{claim}} + w_{\text{reason}} \cdot S_{\text{reason}} + w_{\text{locator}} \cdot S_{\text{locator}} + w_{\text{terms}} \cdot S_{\text{terms}} + \text{exact\_boost}$$
- **Score Gates & Truncation**:
  - Retain `EXACT_LOCATOR_WEIGHT = 100.0`, `MINIMUM_LEXICAL_SCORE = 0.25`, and `MINIMUM_RELATIVE_SCORE = 0.5`.
  - Maintain the existing candidate selection limit (`top_k = 5` by default) prior to applying `context_budget`.
- **Deterministic & Local**:
  - No remote service calls, vector databases, or embedding models.
  - In-memory index construction on active memories per task turn (stateless across process restarts).

## Testing Decisions

- **Highest Observable Seams**:
  - The public `retrieve(memories, prompt, budget, top_k)` interface in `memory_stale.retrieval`.
  - The public `memory.capture` MCP tool handler and Markdown serialization/deserialization.
- **Behavioral Test Slices**:
  1. *Portuguese Stemming Match*: A query with inflected/plural terms retrieves an active Portuguese memory with base-form terms.
  2. *English Stemming Match*: A query with past tense or plural verbs retrieves an active English memory with root terms.
  3. *Code Locator Structural Tokenization*: A query matching a camelCase or snake_case symbol in `evidence.locator` scores accurately without being mutated by a natural language stemmer.
  4. *Backward Compatibility*: Legacy memory Markdown documents without `memory_stale.language` load without error and default to `"en"`.
  5. *Multi-Field Weighting & Thresholding*: Assert that field weights and minimum score thresholds (`0.25` absolute, `50%` relative) filter low-scoring distractors.
  6. *Exact Locator Boost*: Verify that exact path/symbol locators in the prompt receive the `100.0` boost and bypass lexical filters.
- **Evaluation Benchmark**:
  - Excluded from default test runs (`pytest -m "not repository_evaluation"`).
  - Executed and recalibrated when running full evaluation suite (`uv run pytest -m repository_evaluation`).

## Out of Scope

- Reciprocal Rank Fusion (RRF) or ordinal rank-based fusion.
- Vector embeddings, dense neural retrievers, or hosted LLM endpoints.
- Automatic cross-lingual translation of stored claims or prompts.
- Modifying tree-sitter AST parsing or Git evidence tracking logic.

## Further Notes

`bm25s` provides fast in-memory indexing with Python and C-accelerated Snowball stemmers (`PyStemmer`). This maintains the millisecond execution budget required by lifecycle hooks like `UserPromptSubmit` while significantly improving lexical recall for inflected languages.

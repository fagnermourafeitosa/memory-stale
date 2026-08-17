# Spec 39: Prompt-language semantic memories

## Problem Statement

Memory Stale currently guarantees UTF-8 serialization but has no explicit
language contract for semantic memory content. The initial English-only idea
would also be incompatible with the current retrieval design: retrieval uses
literal, lexical BM25 over the incoming prompt and stored memory text. If a
Portuguese prompt creates an English memory, a later Portuguese prompt may not
share enough tokens with that memory to retrieve it.

The runtime does not know the user's language reliably, does not translate
queries, and must not call another LLM or an embedding service. The host agent
already has the prompt and can author the semantic memory in the prompt's
language. The product contract should use that fact instead of imposing a
single storage language.

## Solution

Require semantic memory content to use the natural language of the user prompt
that caused the capture. The host agent writes `claim`, `durability_reason`,
and `retrieval_terms` in that prompt language. The local runtime stores and
retrieves the text without detecting, translating, or normalizing it into
English.

BM25 remains a deterministic lexical retriever. Semantic retrieval is expected
when the later prompt and the stored memory use the same language. Cross-
language semantic retrieval is not promised. Exact repository locators and
symbols remain language-independent and continue to work across languages.

## User Stories

1. As a Portuguese-speaking user, I want a memory created from my Portuguese
   prompt to be written in Portuguese, so that later Portuguese tasks can
   retrieve it lexically.
2. As an English-speaking user, I want a memory created from my English prompt
   to be written in English, so that later English tasks can retrieve it.
3. As a user, I want the memory to follow the language of my current prompt,
   so that the system does not assume that every user speaks English.
4. As a host agent, I want to author semantic memory in the prompt language I
   already understand, so that no translation stage or language service is
   required.
5. As a maintainer, I want the runtime to preserve the submitted language and
   Unicode text exactly, so that UTF-8 storage does not alter the claim.
6. As a maintainer, I want BM25 to compare a prompt and memory in their
   original language, so that retrieval remains deterministic and explainable.
7. As a maintainer, I want cross-language semantic misses to be an explicit
   limitation, so that they are not confused with stale-memory failures.
8. As a user, I want an exact file path or symbol locator to retrieve a memory
   even when the surrounding prompt is written in another language.
9. As a maintainer, I want retrieval terms to use the originating prompt's
   language, so that declared vocabulary supports the same lexical audience as
   the claim.
10. As a maintainer, I want mixed-language prompts handled by the host agent,
    so that the deterministic runtime does not guess which language to use.
11. As an evaluation maintainer, I want each corpus scenario's capture text and
    retrieval prompt to use the same language when testing semantic retrieval,
    so that the result measures lexical retrieval fairly.
12. As an evaluation maintainer, I want cross-language scenarios labeled
    separately, so that a missed BM25 match is not counted as an unexpected
    lifecycle or freshness failure.
13. As a maintainer, I want this policy tested through local public seams, so
    that language behavior does not require the installed Codex or Claude
    environment.
14. As a maintainer, I want the 100-trial repository evaluator excluded from
    ordinary validation, so that it remains an intentional measurement.

## Implementation Decisions

- Replace the English-only semantic capture requirement with a prompt-language
  requirement. The host must author `claim`, `durability_reason`, and
  `retrieval_terms` in the natural language used by the user prompt that
  motivated the capture.
- Update both host-facing skill documents with this rule. They must not tell
  the host to default semantic memories to English and must distinguish memory
  language from repository contract language, which remains English.
- Do not add language detection, translation, embeddings, a remote language
  service, or another LLM. The host agent is the authority for interpreting the
  prompt language; the local engine remains deterministic and language-agnostic.
- Do not reject a capture because its prose is Portuguese, English, or another
  language. The capture boundary validates content shape and evidence as it
  does today, while preserving the submitted Unicode strings.
- For a mixed-language prompt, the host chooses the language of the main
  user-facing natural-language request. Technical identifiers, acronyms,
  paths, symbols, and version strings remain opaque and are preserved as
  written. A prompt containing no natural-language prose uses English as the
  stable host fallback for semantic wording.
- Keep automatic provenance records separate from semantic memory language.
  Their fixed English wording is deterministic operational provenance, not a
  host-authored semantic summary. It must not be translated by the local
  runtime.
- Preserve the existing retrieval interface and BM25 policy. The query is
  tokenized from the prompt as received; stored fields are tokenized in their
  original language; no persistent token index is introduced.
- Treat same-language lexical retrieval as the supported semantic path. Keep
  exact locator matching as the language-independent path. Do not claim that a
  Portuguese prompt retrieves an English semantic claim unless an exact code
  locator also matches.
- Update the repository evaluation corpus contract so semantic retrieval cases
  use the same language for `capture.claim`, `capture.durability_reason`,
  `capture.retrieval_terms`, and `retrieval_prompt`. Cross-language cases may
  be included only as explicitly labeled limitation cases.
- Do not translate corpus prompts as a substitute for production multilingual
  retrieval. A translated fixture is valid only when the scenario itself is
  defined as an English-language task; it must not pretend to exercise a
  user's original Portuguese-to-English runtime flow.
- Keep Markdown/YAML persistence UTF-8 and atomic. Encoding and language are
  separate concerns: UTF-8 preserves whatever prompt language the host chose.

## Testing Decisions

- The highest observable seams are the public `memory.capture` boundary and
  the public `retrieve(...)` operation. Tests must observe persisted text and
  returned context, not private token arrays or classifier behavior.
- First red-green slice: capture a Portuguese semantic memory through the
  public boundary, persist it, and retrieve it with a Portuguese prompt.
- Add the corresponding English capture/English prompt case and verify that
  the exact claim text and retrieval result remain unchanged.
- Add a Unicode round-trip case with Portuguese accents and punctuation. Verify
  the persisted bytes decode as UTF-8 and the loaded claim equals the submitted
  claim.
- Add a cross-language case showing that semantic BM25 retrieval is not
  promised, plus an exact-locator case showing that a locator can still
  retrieve across languages.
- Add a mixed-language capture case whose expected language choice is supplied
  by the host-authored claim; the runtime must preserve it rather than infer a
  different language.
- Add corpus-schema tests that reject semantic retrieval fixtures whose capture
  prose and retrieval prompt are declared as different languages. Do not infer
  the language with the production code; the fixture's expected language is an
  independent test datum.
- Keep tests local and bounded: use temporary repositories and direct public
  request handling where possible. Do not exercise project installation,
  Codex or Claude hooks, subprocess-host lifecycle orchestration, external
  services, or a full environment bootstrap for this spec.
- Do not run `pytest -m repository_evaluation`. The 100-trial repository
  evaluation is explicitly outside this spec's validation scope.
- When implementation is complete, run focused language/retrieval tests and
  the ordinary default suite as appropriate for changed code. The default
  suite must continue to exclude `repository_evaluation`.

## Out of Scope

- Enforcing one global language such as English for all memories.
- Automatically detecting the user's language in the local runtime.
- Translating prompts, claims, retrieval terms, or existing memories.
- Cross-language semantic retrieval for arbitrary user prompts.
- Embeddings, vector indexes, fuzzy translation dictionaries, or another LLM.
- Changing repository instructions, specs, README prose, source files, or
  evidence locators to follow the user's prompt language; those artifacts stay
  in English or retain their project-defined representation.
- Translating automatic operational provenance records.
- Running or recalibrating the 100-trial repository evaluation.
- Broadening integration coverage for Codex, Claude Code, installation, or
  global MCP registration.

## Further Notes

This contract deliberately aligns the two lexical inputs that the current
engine can control: the user prompt and the host-authored semantic memory. It
does not solve multilingual retrieval between different turns that use
different languages. Exact paths and symbols remain the reliable fallback for
those cases.

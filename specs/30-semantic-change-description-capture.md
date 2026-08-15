# 30 — Semantic descriptions for completed code changes

This spec supersedes specs 27 and 28 only where deterministic automatic change
records are treated as the complete memory of an ordinary completed code
change. Automatic symbol/source records remain mandatory provenance, and every
coherent change also receives a Codex-authored description of what it
established. Neither layer replaces the other.

Memory Stale remains a provenance-first product. Its distinguishing behavior is
resolving code evidence, fingerprinting it, determining whether a claim remains
active, and excluding stale claims. The Codex-authored description is the
required memory payload governed by that provenance; it is not generated or
semantically evaluated by the local engine.

## Problem Statement

Memory Stale currently turns supported code changes into records such as
`Automatic change record: added symbol app/main.py:atacantes.` This is precise
provenance, but it does not describe what was implemented. Naming a file or
symbol is not semantic project memory, regardless of whether the change is an
endpoint, a validation rule, a data transformation, an operational constraint,
a refactor with a durable invariant, or any other kind of code change.

The deterministic engine cannot author the missing meaning without violating
the product boundary against calling another LLM. The Codex instance already
performing the task has that meaning, but the current skill describes explicit
`memory.capture` as optional for ordinary code changes. As a result, Codex can
finish a change without submitting a semantic claim, leaving only automatic
provenance in durable storage.

## Solution

Make semantic capture a required completion step for supported code changes.
The `UserPromptSubmit` hook must inject a compact capture protocol into the
active Codex context, and the installed skill must state the same requirement:
before finishing a task that changed supported code, Codex calls
`memory.capture` once per coherent change and supplies a concise claim that
describes what the resulting code now does or guarantees.

The claim is authored by the same Codex instance that performed the task. The
local engine remains deterministic: it validates the structured claim,
evidence, turn scope, and fingerprints; it does not generate, rewrite, or judge
natural-language meaning and does not call another model.

Retrieval uses both parts for different purposes. Evidence determines whether a
memory remains active and provides exact path/symbol matching. The claim
provides lexical retrieval terms and is the substantive content injected into
Codex context. Provenance without a claim cannot communicate what should be
remembered; a claim without provenance cannot participate in deterministic
freshness control.

At `Stop`, deterministic automatic records continue to be created for every
added or changed symbol and for eligible source-level changes. These records
are the exact provenance layer: they identify what code location changed and
retain its fingerprint. Explicit semantic captures are persisted alongside
them as the meaning layer: they describe what the coherent change now does or
guarantees and declare the relevant provenance as evidence.

The engine deterministically checks whether the explicit captures collectively
cover the changed automatic locations. A capture covers an automatic location
when any of its declared evidence resolves to the same symbol locator, or, for
a source-level record, to that source path. Equivalent `symbol` and `test`
locators count as the same code location for coverage. Coverage is used only to
detect a missing semantic description; it never suppresses automatic
provenance.

If supported code changed and no explicit capture covers part of it, `Stop`
still persists all automatic records and returns an actionable diagnostic
naming the locations missing semantic coverage. The diagnostic makes the
incomplete meaning layer visible; it must not fabricate a description from
paths, diffs, the user request, or the final assistant message.

## User Stories

1. As a developer, I want memory to describe what a completed change
   established, so that a later task can recover intent rather than only locate
   modified code.
2. As a developer, I want one semantic memory to represent one coherent change
   supported by several implementation and test symbols, so that memory is not
   fragmented into per-symbol notifications.
3. As a developer, I want both exact automatic provenance and a semantic
   description persisted for the same change, so that I can recover both where
   it changed and what it means.
4. As a developer, I want semantically uncovered changes reported explicitly, so that a
   missed semantic capture cannot look like successful semantic memory.
5. As a maintainer, I want all language generation to come from the Codex
   instance already performing the task, while hooks and the memory engine
   remain local and deterministic.
6. As a product user, I want the provenance engine to remain the product's
   technical focus, while the Codex-authored claim supplies the content that is
   retrieved and injected into later tasks.

## Observable Test Seam

The highest seam is the installed project-local workflow in a temporary Git
repository:

1. `UserPromptSubmit` starts a turn and injects the semantic-capture protocol.
2. The task changes multiple supported symbols that implement one coherent
   behavior.
3. The real local MCP receives one `memory.capture` request with an independent
   human-authored expected claim and all relevant evidence.
4. `Stop` reconciles the turn.
5. The persisted Markdown store contains the semantic claim and the automatic
   records for every changed code location.
6. A later prompt containing claim-related language but no exact path or symbol
   retrieves and injects the semantic claim, proving that the description is
   operational memory content rather than audit-only metadata.

The complementary incomplete-capture seam performs the same hook cycle without
an MCP capture and observes both the missing-semantic-description diagnostic
and the unchanged automatic provenance records.

This is the seam to confirm before the first test. Tests do not attempt to make
the deterministic engine invent expected prose; the semantic claim is an
independent literal representing what the active Codex instance submits.

## Expected Behavior

- Every task that completes a supported code change receives an in-context
  instruction to capture what the resulting code does or guarantees before the
  final response.
- Codex submits one capture per coherent durable change, not one capture per
  changed file or symbol.
- A semantic claim must express resulting behavior, contract, constraint,
  architecture, or operation. A file path, symbol locator, task-history
  statement, or reserved `Automatic change record` claim is rejected by
  `memory.capture`.
- The capture declares all code evidence needed to support the claim. Changed
  implementation symbols are normally primary evidence; tests, configuration,
  schemas, and dependent symbols may be primary or supporting according to the
  existing evidence contract.
- One capture may cover several changed symbols and tests. Every automatic
  record remains persisted alongside that coherent semantic memory.
- Retrieval continues to use evidence for active/stale classification and
  exact-location matches, while using claim text for lexical ranking and
  context injection.
- Semantically uncovered supported changes retain their deterministic
  automatic records and are named in a non-blocking `Stop` diagnostic.
- A read-only, documentation-only, formatting-only, comment-only, or unsupported
  language turn requires no semantic capture and produces no new diagnostic.
- Existing automatic and semantic memories remain readable and are not
  rewritten or deleted by this feature.

## Implementation Constraints

- Do not call another LLM, invoke Codex recursively, add embeddings, or derive a
  natural-language claim from source, diffs, prompts, ledgers, or assistant
  messages.
- The active Codex instance is the sole semantic author and must use the
  structured local `memory.capture` MCP boundary.
- Keep Git mandatory and preserve typed evidence, versioned revisions, atomic
  writes, non-blocking hooks, and the existing supported-language boundary.
- Do not make `Stop` depend on undocumented hook blocking or retry behavior.
  Official OpenAI documentation located during specification did not establish
  a supported stop-blocking contract, so the runtime uses context instruction,
  mandatory provenance, deterministic coverage, and diagnostics only.
- Coverage matching is structural and deterministic. It compares normalized
  evidence locations only to detect missing semantic coverage; it does not
  suppress provenance or evaluate whether claim prose is truthful or complete.
- Preserve explicit `memory.capture` idempotency and existing evidence
  validation. Add only bounded rejection of mechanical claims that are
  structurally identifiable as non-semantic.

## Testing Decisions

- First red-green slice: a real `UserPromptSubmit` hook returns the mandatory
  semantic-capture protocol for a normal turn. The current implementation must
  fail because it injects retrieved memories only.
- Second slice: one explicit semantic capture covering two changed symbols and
  one changed test persists exactly one semantic memory plus all three
  automatic provenance records.
- Third slice: omit explicit capture and require the same automatic provenance
  records plus an actionable `Stop` diagnostic listing locations without
  semantic coverage.
- Test mechanical-claim rejection through the real MCP server, including the
  reserved automatic prefix and claims consisting only of a path or locator.
- Test that a partial semantic capture leaves every automatic record intact and
  reports only the locations without semantic coverage.
- Test no-op categories: read-only, comments, formatting, documentation,
  configuration-only changes not represented by automatic source capture, and
  unsupported languages.
- Use temporary Git repositories, real installed hooks, the real MCP process,
  persisted Markdown, and later retrieval. Do not mock project-owned modules or
  assert private call order.
- Run focused red-green slices, then the required format, lint, strict typing,
  and full test suite. Preserve the fixed evaluation corpus unchanged.

## Documentation Decisions

- Keep the public README provenance-first: the product outcome is durable
  project memory whose trust follows code evidence, and the differentiating
  mechanism is deterministic freshness through Tree-sitter-backed provenance.
- Explain that the Codex-authored claim is required memory content: it carries
  what should be remembered, participates in lexical retrieval, and is injected
  into later context. It is not a second provenance mechanism or an
  engine-generated LLM summary.
- Define automatic symbol/source records and semantic claims as mandatory,
  complementary stored records with different responsibilities.
- Show a domain-neutral example in which one claim is supported by multiple
  implementation and test symbols.
- State plainly that Memory Stale does not generate prose with a hidden model;
  the Codex instance doing the work submits the claim.
- Update the installed skill so semantic capture is a mandatory completion
  step for supported code changes rather than optional enrichment.

## Out of Scope

- Having the deterministic engine generate or improve natural-language
  descriptions.
- Claim truth scoring, semantic deduplication, embeddings, or vector retrieval.
- Automatically discovering undeclared dependencies or evidence relationships.
- Blocking Codex completion through undocumented hook behavior.
- Migrating or deleting existing automatic memories.
- Suppressing automatic provenance when a semantic memory covers the same code.

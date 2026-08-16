# 34 — OKF-compatible memory Markdown format

## Problem Statement

Memory Stale persists useful, Git-native Markdown, but its frontmatter is a
private schema. A third-party knowledge consumer can read the prose but cannot
reliably identify the claim's provenance, producer, verification event, or
standard lifecycle metadata without knowing Memory Stale's implementation.

Open Knowledge Format (OKF) v0.2 defines a deliberately small Markdown plus
YAML envelope for those concerns. It standardizes concept identity through
`type`, provenance through `sources`, trust through `generated` and `verified`,
and document lifecycle through `status`, while explicitly allowing
producer-defined extensions and not prescribing a runtime, storage engine, or
query system. Memory Stale must retain its deterministic evidence resolution,
fingerprinting, invalidation, and BM25 retrieval rather than treating OKF as a
replacement for them.

## Solution

Persist every Memory Stale revision as an OKF v0.2 concept document with
`type: Memory Stale Claim`. Place portable descriptive, provenance, trust, and
lifecycle fields at the top level. Place all deterministic Memory Stale state
under one `memory_stale` extension namespace.

The memory directory is an OKF bundle of claim concepts. It need not add an
`index.md` or `log.md` for this change. Each memory revision remains one
Markdown file named by its deterministic revision ID, and the Markdown body
remains the complete claim text.

The public persistence seam is the `MemoryStore` directory at
`.agents/skills/.agent-memory/memories/`: after a real capture and lifecycle
reconciliation, every written `*.md` record must be a parseable OKF concept and
must round-trip through the public store without changing the Memory model or
its deterministic lifecycle outcome. This seam is confirmed before the first
implementation test.

## User Stories

1. As a user, I want each memory file to declare standard provenance and trust,
   so that a general OKF consumer can understand its basic origin without a
   Memory Stale SDK.
2. As an auditor, I want every fingerprinted evidence item to have a matching
   OKF source, so that the ordinary provenance view and deterministic freshness
   view refer to the same artifacts.
3. As a Memory Stale user, I want source changes to keep making memories stale,
   so that adopting OKF does not weaken deterministic freshness decisions.
4. As a maintainer, I want Memory Stale-only fields isolated in one extension,
   so that external consumers can preserve or ignore them safely.
5. As an existing user, I want pre-OKF records to migrate on normal store
   write, so that existing memory history remains readable and no manual
   migration command is required.
6. As a retrieval user, I want active-memory filtering and field-weighted BM25
   to behave exactly as before, so that the schema change does not alter context
   quality.

## Expected Behavior

### Canonical v5 document

A newly persisted revision uses this logical shape. YAML serialization keeps
the shown top-level field order and the body has one trailing newline.

```markdown
---
type: Memory Stale Claim
title: Retry policy
description: Makes retry behavior available during later maintenance.
sources:
  - id: symbol:src/jobs.py:retry
    resource: src/jobs.py:retry
generated:
  by: process:memory-stale
  at: 2026-08-16T12:00:00+00:00
verified:
  - by: process:memory-stale
    at: 2026-08-16T12:00:00+00:00
status: stable
memory_stale:
  schema_version: 5
  claim_id: 3ac9b2c3f5d0b5ab7831
  revision_id: 8f5dd66d67f4ce0c2f44
  kind: behavior
  status: active
  durability_reason: Makes retry behavior available during later maintenance.
  evidence:
    - source_id: symbol:src/jobs.py:retry
      type: symbol
      role: primary
      fingerprint: abc123
  supported_by:
    - symbol:src/jobs.py:retry
  dependencies: []
  stale_reasons: null
  observed_commit: 0123456789abcdef
  observed_at: 2026-08-16T12:00:00+00:00
  legacy_id: null
---

Retry policy
```

The example IDs and fingerprint are illustrative literals, not a new identity
algorithm. Existing claim-ID, revision-ID, fingerprint, evidence, graph, and
atomic-write rules remain authoritative.

### Top-level OKF envelope

- Every memory document has the non-empty required OKF field
  `type: Memory Stale Claim`. This is a producer-defined OKF type; unknown
  types remain valid for conforming OKF consumers.
- `title` equals the normalized display form of the claim. `description` equals
  the durability reason. The complete, unmodified claim remains the Markdown
  body and is the value Memory Stale uses for claim identity and retrieval.
- `sources` has exactly one entry for each evidence item, in canonical evidence
  order. `sources[].id` is the evidence key (`<type>:<locator>`) and
  `sources[].resource` is the same compact Memory Stale locator. This treats a
  supported source symbol, source file, configuration node, schema node, or test
  as the concrete artifact from which the claim derives. Memory Stale does not
  invent credibility scores, `usage_count`, `author`, or `last_modified`.
- `generated` records the creation of the immutable evidence revision. Its
  actor is `process:memory-stale` and its timestamp is an ISO 8601 UTC timestamp
  supplied by the lifecycle boundary. The timestamp is created once for a new
  revision and is never changed merely because a later reconciliation marks it
  stale.
- Every successfully persisted new revision contains one `verified` event with
  `by: process:memory-stale` and the same timestamp as `generated.at`. It means
  the deterministic process resolved every declared evidence item and recorded
  the displayed fingerprints at capture time. It is not a human review, a
  semantic-truth verdict, or an OKF attestation.
- The top-level OKF `status` maps from the deterministic state: `active` maps
  to `stable`; `stale` and `superseded` map to `deprecated`. The missing OKF
  status must never be emitted for v5 records. This top-level lifecycle signal
  makes obsolete revisions safe for generic consumers, but Memory Stale itself
  uses only `memory_stale.status` to decide freshness and retrieval eligibility.
- Do not write `stale_after`: Memory Stale freshness is evidence divergence, not
  date expiration. Do not write OKF attested-computation fields; a memory claim
  is not an `Attested Computation` concept.

### `memory_stale` extension

`memory_stale` is the sole top-level producer extension. It contains these
fields and no former private top-level persistence fields:

- `schema_version`: integer `5`.
- `claim_id`, `revision_id`, `kind`, `status`, `durability_reason`,
  `observed_commit`, `observed_at`, and `legacy_id`: the existing values with
  their existing meanings. `status` is one of `active`, `stale`, or
  `superseded`.
- `evidence`: canonical evidence items. Each has `source_id`, `type`, `role`,
  and `fingerprint`; `source_id` must equal one `sources[].id`. The locator is
  represented once, as the matching source's `resource`, rather than duplicated
  inside this extension.
- `supported_by`: canonical source-ID list, replacing evidence-key strings.
  Each value must identify a declared extension evidence item.
- `dependencies`: canonical objects with `from` and `to` source IDs. Both ends
  must identify declared extension evidence items.
- `stale_reasons`: either `null` or a mapping keyed by source ID. Its values
  retain the current deterministic reason text, including an invalidation path
  when one exists.

The store rejects a v5 document when an evidence/source mapping is missing,
duplicated, mismatched, malformed, or has no primary item; when graph references
do not resolve to evidence; or when its OKF envelope does not match the
deterministic extension. These are invalid Memory Stale records even though a
general OKF reader may permissively display their unknown extension fields.

### Lifecycle and migration

- Lifecycle reconciliation continues to resolve current evidence, compare it
  with stored fingerprints, and transition the extension status to `stale` on
  divergence. It updates the mapped top-level `status` to `deprecated` in the
  same atomic write and retains `generated` and `verified` as historical
  provenance.
- A new revision remains `active`/`stable`; replacing an active revision with a
  recapture leaves the former revision `superseded`/`deprecated`. No active
  claim body is edited to state a newer fact.
- Existing schema versions through v4 remain readable. The next normal atomic
  `write_all` serializes them as v5 while preserving claim and revision IDs,
  claim body, evidence fingerprints and graph, stale reasons, observation
  metadata, and legacy provenance. Migration is deterministic and idempotent.
- Because top-level trust metadata did not exist before v5, a migrated record
  receives `generated` and the process verification event from its
  `observed_at` when present. If that timestamp is absent, the write boundary
  supplies one UTC timestamp; it must not participate in IDs, deduplication, or
  stale comparisons.

## Implementation Constraints

- Implement the format in the existing local store and lifecycle adapters; do
  not add a human-facing CLI, remote catalog, schema registry, database, index,
  or another LLM.
- Use OKF v0.2's Markdown/YAML conventions and actor convention. Do not claim
  full OKF runtime, storage, query, or attestation support merely by emitting
  this envelope.
- Preserve unknown top-level fields when a v5 document is loaded and written
  again, except where a known canonical field must be regenerated. This enables
  interoperable tools to add valid OKF fields such as tags without Memory Stale
  silently discarding them. Unknown fields must not influence claim identity,
  fingerprints, lifecycle, or retrieval.
- Serialize canonical fields and extension collections deterministically; do
  not rely on incidental YAML key sorting. The record remains UTF-8, readable,
  diffable, and atomically written.
- Pass the clock explicitly at the capture/store boundary so timestamps are
  testable and no hidden time source changes a record during reconciliation.
- Retain the existing project boundary: `.agents/` remains operational
  infrastructure and must not become eligible source evidence because memory
  files are now OKF documents.
- Update README documentation when implementation lands, describing the OKF
  envelope, the `memory_stale` extension, and the distinction between standard
  document lifecycle and deterministic evidence freshness.

## Testing Decisions

1. First red-green slice: run the real MCP capture and `Stop` lifecycle in a
   temporary Git repository, then inspect the persisted file. Require the
   top-level required `type`, exactly corresponding `sources`, `generated`,
   process `verified`, `status: stable`, the v5 `memory_stale` extension, and
   the claim body. The current v4 serializer must fail this test because it
   writes private top-level fields and no OKF envelope.
2. Add a store round-trip test that parses the persisted YAML independently of
   the internal `Memory` class, verifies the OKF structural requirements, then
   loads it through the public store and observes an equal memory revision.
3. Through a real later hook cycle, change only supporting evidence and require
   the same revision to become `memory_stale.status: stale` and top-level
   `status: deprecated`, with the source-ID-keyed stale reason and unchanged
   generated/verification timestamps.
4. Capture a replacement revision and require the prior active revision to be
   `superseded`/`deprecated`, the replacement to be `active`/`stable`, and
   normal retrieval to return only the latter.
5. Use v1 through v4 persisted fixtures, including absent observation time, and
   assert one normal write produces valid v5 documents without changing identity
   fields, evidence, graph, stale reasons, or claim text. A second write must
   be byte-for-byte stable when no lifecycle state changed.
6. Add malformed-v5 fixtures for a missing source, duplicate source ID,
   mismatched resource/locator, unknown graph source ID, and missing primary
   evidence. Observe actionable store failure rather than a partially loaded
   memory.
7. Add a round-trip fixture containing an unrelated valid OKF field such as
   `tags`; require it to survive Memory Stale load and write while retrieval,
   fingerprinting, and lifecycle results remain unchanged.
8. Retain the existing focused red-green cadence, then run the required
   formatter, lint, strict typing, and default test suite. The repository
   evaluation remains opt-in because this change does not alter its corpus or
   ranking policy.

## Out of Scope

- Replacing evidence resolution, fingerprints, stale detection, dependency
  traversal, BM25, or active-memory filtering with OKF behavior.
- Automatic evidence coverage, semantic dependency discovery, trust scoring,
  or a claim-truth assessment.
- Producing an OKF bundle index, log, cross-memory links, remote publication,
  import/export protocol, registry, or generic OKF query interface.
- Implementing OKF Attested Computations, executor/attester code, receipts, or
  runtime attestation.
- Changing supported evidence types, source grammars, claim/revision identity,
  lifecycle status names, retrieval scoring, or context budget.

## Further Notes

- The normative external reference is [Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).
- OKF is the interoperable representation envelope. Memory Stale remains the
  deterministic freshness engine layered inside its explicit extension.
- This spec builds on versioned evidence revisions (14), typed evidence sets
  (16), the explicit dependency graph (17), and the `.agents/` product boundary
  (33).

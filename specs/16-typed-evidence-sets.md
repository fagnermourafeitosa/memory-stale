# 16 — Typed evidence sets

## Problem Statement

A claim may depend on more than one symbol or on structured state outside the
changed symbol. The current contract permits multiple refs but requires all of
them to have changed during the turn, preventing intact supporting dependencies
from being recorded. It also treats all evidence as a code symbol without
explicitly representing configuration, schemas, or tests. Claims therefore
remain `active` when an unrecorded supporting source changes.

## Solution

Replace the implicit ref collection with an explicit, typed evidence set in each
revision. Evidence has a locator, fingerprint, type, and role. At least one
`primary` item must have changed during the turn; `supporting` evidence must
resolve and is fingerprinted even when unchanged. The revision requires
revalidation whenever any recorded item diverges.

## User Stories

1. As Codex, I want to anchor a claim to the changed symbol and intact supporting symbols, so that future changes to any support are detected.
2. As a user, I want a registered configuration change to make a revision stale, so that behavior controlled outside a method does not remain implicit.
3. As a user, I want to register a structured schema as evidence, so that data-contract changes require revalidation.
4. As a maintainer, I want to distinguish primary and supporting evidence, so that capture eligibility remains strict without requiring everything to change during the turn.
5. As an auditor, I want to see each item's type, role, locator, and fingerprint, so that provenance is readable.
6. As a user, I want relevant tests to be explicit evidence, so that removing or changing a protective scenario requires revalidation.
7. As a maintainer, I want unsupported formats and locators rejected, so that no imprecise file-level fallback appears.
8. As an existing user, I want legacy refs migrated to primary symbol evidence, so that history remains usable.
9. As Codex, I want per-item errors, so that a partially resolved evidence set is never captured as valid.

## Implementation Decisions

- Each revision contains a canonical set of `EvidenceItem` values with `type`, `role`, `locator`, and `fingerprint`.
- Roles are `primary` and `supporting`. At least one `primary` item must have changed during the active turn; `supporting` items need not have changed.
- Every item must resolve in the final state before capture. Capture is rejected atomically if any item is invalid.
- Explicit MCP capture supports `symbol`, `config`, `schema`, and `test`.
  Spec 27 adds internal automatic `source` evidence for parsed supported code
  files only.
- `symbol` continues to use tree-sitter resolution and the symbol's structural signature without a file fallback.
- `test` resolves a test function or method as a structural symbol but retains its own type to explain its provenance role.
- `config` points to an exact node in a JSON, YAML, or TOML document through a structured locator. Its fingerprint covers the node's canonical representation while ignoring formatting and comments.
- `schema` points to an exact JSON Schema or OpenAPI node in JSON or YAML. Its fingerprint covers the selected node's canonical representation.
- Whole-document locators, unsupported formats, invalid parsing, and missing locators are rejected; there is no fallback to a raw file hash.
- A change, removal, or resolution failure for any recorded item makes the revision `stale`, with a reason for that evidence item.
- Claim identity uses only the scope of `primary` evidence; adding or replacing support creates a new evidence revision of the same claim while primary scope remains unchanged.
- Input order does not affect IDs, comparison, or results.
- The legacy refs schema migrates to `symbol` items with the `primary` role.
- The skill, MCP server, Markdown store, Dream, and report use the same typed model and show actionable reasons per item.

## Testing Decisions

- Highest seam confirmed: a real MCP call in a temporary Git repository followed by hooks or Dream, Markdown persistence, and observation of final status.
- First behavioral slice: change the primary symbol, capture a claim with an intact supporting symbol, change only the support in a later turn, and observe the revision become `stale`.
- The first test must fail under the current contract because an unchanged ref cannot participate in capture.
- Subsequent slices cover configuration, schema, and test evidence with semantic changes and formatting-only or comment-only changes when the format permits.
- Each type has fixtures for valid evidence, missing locator, invalid parsing, removal, and independent canonicalization.
- Tests confirm atomic rejection of partially invalid evidence sets and staleness reasons per item.
- Legacy-ref migration is exercised through the public store and installed flow.
- All seven indexers continue to use real fixtures for supported `symbol` and `test` items.

## Out of Scope

- Automatically inferring which evidence supports a claim.
- Creating or traversing `depends_on` relationships between evidence items.
- Supporting whole-file hashes, arbitrary text regions, or unsupported languages.
- Semantically interpreting configuration or schema content.
- Adding SQL, a vector database, a remote service, or another LLM.
- Using evidence types for semantic retrieval ranking.

## Further Notes

- This spec depends on the revisioned schema from spec 14 and is evaluated with the corpus from spec 15.
- Flat evidence sets provide multi-source invalidation before the cost of a graph.

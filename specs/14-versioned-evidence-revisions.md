# 14 — Claims with versioned evidence revisions

**Status: Done (2026-08-11)**

## Problem Statement

Current persisted identity combines kind, normalized claim, and refs but omits
evidence fingerprints. After a memory becomes `stale`, a semantically identical
capture with the same refs and a new implementation produces the same ID and is
discarded as known. The product cannot represent that the same claim was
supported by different revisions over time or restore it to context without
losing prior history.

## Solution

Separate stable claim identity from the immutable identity of each evidence
revision. The same claim may accumulate historical revisions, at most one of
which is the current `active` revision. A new capture with new fingerprints
creates another revision, preserves previous revisions, and makes the claim
eligible for retrieval again. Markdown storage receives a `schema_version` and
a deterministic migration from the existing pre-alpha format.

## User Stories

1. As a user, I want to revalidate the same claim after an irrelevant change, so that useful knowledge returns to context.
2. As a user, I want every previous revision preserved, so that evidence evolution remains auditable in Git.
3. As Codex, I want to recapture the same claim and scope with new fingerprints, so that deduplication does not block legitimate revalidation.
4. As Codex, I want repeating the exact same revision to be idempotent, so that repeated hooks do not create duplicates.
5. As a maintainer, I want separate `claim_id` and `revision_id` values, so that semantic identity and historical observation are not the same object.
6. As a maintainer, I want a versioned schema, so that future Markdown changes have explicit migrations.
7. As an existing user, I want earlier-format memories to remain readable, so that an upgrade does not lose history.
8. As a user, I want retrieval to show a claim only once through its `active` revision, so that history does not pollute context.
9. As an auditor, I want to see the observed commit and time when available, so that I can relate a revision to repository state.

## Implementation Decisions

- The durable model has a logical claim entity and one or more immutable evidence revisions.
- `claim_id` is deterministic from kind, normalized claim, and canonical scope. At this stage, canonical scope is the ordered set of symbol locators currently represented by refs.
- `revision_id` is deterministic from `claim_id` and the ordered set of evidence fingerprints.
- Repeating a capture with the same `revision_id` is idempotent.
- Capturing the same claim and scope with different fingerprints creates a new revision even when an earlier `stale` revision exists.
- At most one revision is the current `active` revision for each `claim_id`. When a new revision is accepted, any previously current revision is preserved outside normal context.
- Status belongs to the evidence revision. A claim is eligible for retrieval only when it has a current `active` revision.
- Storage remains auditable, diffable Markdown and uses `revision_id` to prevent collisions between historical files.
- Every persisted record has `schema_version`. Documents without a version are interpreted as the legacy pre-alpha schema.
- Migration is deterministic, non-destructive, and idempotent. Legacy IDs remain available as migration provenance when they differ from new IDs.
- A revision stores deterministic repository observation metadata, including the commit when available. A timestamp is metadata and never participates in deduplication.
- Writing the reconciled corpus remains atomic and never leaves partially written claims or revisions.
- The report groups revisions by claim and shows history; normal context continues to receive only the current `active` revision.

## Testing Decisions

- Highest seam confirmed: real MCP server and hooks in a temporary Git repository, observing capture, persisted Markdown, staleness, recapture, and retrieval.
- First behavioral slice: capture a claim, change its symbol, observe the old revision become `stale`, recapture the exact same claim and refs, and observe a new `active` revision in context.
- The first test must fail under current behavior because legacy-ID deduplication discards recapture.
- Subsequent slices cover same-revision idempotency, retrieval grouping, history preservation, and a single current revision.
- Legacy fixtures without `schema_version` prove readable, idempotent migration without loss of claim, status, reasons, or signatures.
- The store is tested through the public Markdown directory; IDs, groupings, and metadata are observed in persisted documents without mocks of project-owned modules.
- Tests use real commits in temporary Git repositories to validate commit provenance.

## Out of Scope

- Changing which evidence may be associated with a claim.
- Allowing supporting refs that did not change during the turn.
- Configuration, schema, or test evidence as first-class types.
- A dependency graph or automatic dependency discovery.
- Semantic deduplication between differently worded claims.
- Automatic claim repair without explicit capture by the current Codex instance.

## Further Notes

- This spec depends on the meaning of `stale` defined in spec 13.
- Migration precedes expansion into evidence sets so that later specs have a versioned base.

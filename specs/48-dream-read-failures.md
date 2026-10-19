# 48 — Read failures do not invalidate memories in dream

**Status: Done (2026-10-19)**

## Problem Statement

When `dream` cannot read an evidence file for a reason other than an
evidence-resolution failure, it reports the error but also marks the memory
`stale`. A typical case is a source file without read permission, which raises
`PermissionError`.

The failing item is left out of the evidence map, and reconciliation treats
missing evidence as `unresolvable`. A read failure says nothing about whether
the evidence changed, so the memory is invalidated for no reason. Spec 46
recorded this finding.

## Solution

When resolving an item raises anything other than `EvidenceError`, `dream`
keeps that item's recorded fingerprint. The error still appears in `errors`.
The memory keeps its status unless one of its other items changed or broke.

`EvidenceError` behavior is unchanged. A missing file, a missing locator, or
an unparsable document still marks the memory stale with `file_missing`,
`locator_missing`, or `unresolvable`.

## User Stories

1. As a developer, I want a memory backed by a file `dream` cannot read to stay
   `active`, so that a permission or I/O problem does not invalidate knowledge
   that has not changed.
2. As a developer, I want the read failure listed in the `dream` errors, so that
   I know which file to fix.
3. As a developer, I want other memories audited normally in the same run, so
   that one unreadable file does not hide real staleness.
4. As a developer, I want deleted files, removed symbols, and unparsable
   documents to keep marking memories stale, so that real breakage is still
   flagged.

## Implementation Decisions

- In `dream`, the per-item branch for unexpected exceptions records the item's
  existing fingerprint as its current evidence, then appends the error entry.
  The format is unchanged: `<memory id>:<evidence key>: <ExceptionType>: <message>`.
- The memory is not added to `audited` because of a read failure alone.
- The stop hook is out of scope.

## Testing Decisions

- **Seam:** `dream` on a real temporary repository whose memory files are
  written to disk.
- The existing unreadable-source test in `test_dream_audit` becomes the
  regression test. Its source file is made unreadable with `chmod 000`, and it
  is skipped when running as root. It asserts:
  - the affected memories stay `active` with no stale reasons;
  - they are absent from `marked_stale` and `audited`;
  - the errors still name the `PermissionError` for each of them;
  - a memory in the same run whose config value changed is still marked stale.
- The regression test must fail before the fix.

## Out of Scope

- Read failures in the stop hook.
- Defending against hand-edited or corrupted internal task state.

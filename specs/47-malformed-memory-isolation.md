# 47 — Malformed memory isolation

**Status: Draft (2026-10-19)**

## Problem Statement

Memory Stale loads every memory file through one `MemoryStore.load_all` call,
and that call raises on the first file it cannot load. A single malformed
memory file (a bad hand edit, a merge conflict marker, a truncated write from
another tool) therefore breaks the whole tool:

1. **The prompt hook injects nothing.** The adapter reports one failure
   `systemMessage`, and the agent works without any project memory, including
   all the valid memories.
2. **The stop hook loses the turn's work.** `finish_task` raises before it
   reconciles and before it removes the task state. The turn's semantic
   captures are never persisted, and the task file is orphaned.
3. **`dream` and `memory.report` fail entirely**, so the tools a developer would
   use to diagnose the problem cannot run.
4. **Skipping the file naively would destroy it.** `write_all` deletes every
   memory file that is not in the list it is given. A reader that simply
   ignored bad files would delete them on the next write.

Spec 34 already requires that an invalid v5 record produce an actionable
failure rather than a partially loaded memory. This spec keeps that guarantee
for each file and stops one file's failure from spreading to the whole store.

## Solution

- Loading is isolated per file. A file that cannot be loaded is excluded
  entirely and is never partially loaded. Every valid memory continues to work
  in retrieval, stop reconciliation, `dream`, and the report.
- A malformed file is preserved byte for byte in place. The store never
  deletes, rewrites, or moves a file it could not load. When the file is fixed,
  it rejoins the store on the next load with no other action.
- Each skipped file is reported with its repository-relative path and an
  actionable reason:
  - **Prompt hook:** one warning line per skipped file in the injected context,
    so the agent can see and repair it.
  - **`dream`:** one entry per skipped file in `errors`.
  - **`memory.report`:** a short "Unreadable memory files" section.
  - **Stop hook:** silent about skipped files. It reconciles the valid memories
    and persists the turn's captures without repeating the prompt warning.
- If reconciliation produces a memory whose file would overwrite a malformed
  file, the malformed file is preserved. That one memory write is skipped and
  reported, and every other write proceeds.

## User Stories

1. As a developer, I want a single corrupt memory file not to disable every
   other memory, so that one bad edit does not silently degrade my agent.
2. As a developer, I want valid memories to keep being retrieved and injected
   at prompt time while a malformed file exists, so that the agent keeps its
   project knowledge.
3. As an agent, I want the injected context to name each skipped memory file
   and the reason, so that I can repair it when asked or when relevant.
4. As a developer, I want the stop hook to persist this turn's captures even
   when another memory file is malformed, so that no work is lost.
5. As a developer, I want the stop hook to remove its task state after a
   successful reconciliation even when a malformed file exists, so that task
   files are never orphaned.
6. As a developer, I want staleness reconciliation to keep working for every
   valid memory while a malformed file exists, so that outdated knowledge is
   still flagged.
7. As a developer, I want the malformed file left exactly as it was, byte for
   byte, so that I can inspect and fix my own edit.
8. As a developer, I want the store never to delete a file it could not read,
   so that a load failure can never turn into data loss.
9. As a developer, I want a fixed file to rejoin the store automatically on the
   next load, so that recovery needs no extra command.
10. As a developer, I want a write that would overwrite a malformed file to be
    skipped and reported rather than performed, so that a hand edit is never
    destroyed by an automatic write.
11. As a developer, I want `dream` to audit every valid memory and list each
    skipped file in its errors, so that the audit tool works exactly when I
    need it most.
12. As a developer, I want `memory.report` to render all valid memories and list
    the unreadable files, so that the report shows the full health of the
    store.
13. As a developer, I want each skip reason to be specific (unreadable file,
    invalid encoding, missing front matter, invalid YAML, schema violation with
    its message), so that I know what to fix.
14. As a developer, I want the warning to use the repository-relative path, so
    that I can open the file directly.
15. As a maintainer, I want per-file load failures represented by one specific,
    typed error, so that programming errors are not masked as malformed data.
16. As a maintainer, I want unexpected exceptions (programming errors) to keep
    using the existing non-blocking adapter failure contract, so that real bugs
    stay visible.
17. As a developer using Claude Code, Codex, or Antigravity, I want identical
    isolation behavior across harnesses, so that the guarantee does not depend
    on my agent.
18. As a developer, I want the stop hook not to repeat the malformed-file
    warning on every turn, so that the warning stays useful instead of noisy.
19. As a developer with legacy (unversioned, v3, v4) memory files, I want a
    legacy file that fails validation to be isolated just like a v5 file, so
    that migration problems never block the store.
20. As a developer, I want a store whose files are all malformed to behave like
    an empty store plus warnings, so that the hooks still run.

## Implementation Decisions

- **Isolation unit: the file.** A per-file load either yields one complete
  `Memory` or one skipped-file record. It never yields a partially loaded
  memory, which preserves the spec 34 guarantee.
- **Typed per-file load failure.** The store gets one specific exception type
  for per-file load failures. It carries the repository-relative path and a
  human-readable reason, and it covers:
  - read errors (`OSError`);
  - non-UTF-8 content;
  - missing `---` front-matter delimiters;
  - YAML errors;
  - every existing schema validation failure (v5, v4, v3, unversioned).

  Exceptions outside these categories are not converted. They propagate to
  the adapter's existing failure contract.
- **Store load result.** The store's loading interface returns the valid
  memories together with the skipped-file records. Callers that previously
  received only memories (prompt retrieval, stop reconciliation, `dream`, the
  report) receive both and decide how to surface the skips. `load_all` keeps
  returning only the valid memories, or is replaced by the new interface; the
  implementer chooses whichever keeps call sites cohesive, and no caller may
  ignore the skips silently.
- **Write protection.** The store's write operation never deletes or overwrites
  a file that the corresponding load reported as skipped:
  - Deleting files that no longer correspond to a memory excludes skipped
    files.
  - A memory whose target file is a skipped file is not written. It is
    reported as a skipped write, and the other writes proceed.

  Writes remain atomic for each file.
- **Prompt warning format.** Warnings are deterministic, English, and placed in
  the injected context after the capture protocol, one line per skipped file:
  `Memory Stale skipped <relative path>: <reason>`. They do not count against
  the context budget used for retrieved memories.
- **Stop hook.** The stop hook reconciles valid memories, persists captures,
  and removes the task state normally. It emits no message for skipped files.
  A skipped write caused by a collision is the one stop-time report, through
  the existing `systemMessage` channel.
- **`dream`.** It adds one `errors` entry per skipped file, in the form
  `<relative path>: <reason>`. Its other outcomes are unchanged.
- **Report.** The HTML report adds an "Unreadable memory files" section listing
  each path and reason. The section is omitted when there are no skipped files.
- **No quarantine and no auto-repair.** Files are never moved, renamed, or
  rewritten.

## Testing Decisions

- **Seams:** the hook adapter entrypoints (Claude, Codex, Antigravity) against
  a real temporary Git repository, `dream`, the MCP `memory.report` tool, and
  the installed local harness. These are the same seams spec 46 confirmed. No
  test calls private store loaders.
- **Fixtures:** each malformed kind is a literal file written into the memory
  directory alongside at least one valid memory:
  - unreadable (`chmod 000`, skipped as root);
  - non-UTF-8 bytes;
  - no front matter;
  - invalid YAML;
  - an invalid v5 record (unknown status, stale reason referencing unknown
    evidence, missing primary);
  - an invalid legacy record.
- **Core behavioral slices**, each with its own red-green TDD cycle:
  1. With a valid and a malformed file present, the prompt hook injects the
     valid memory and one warning line naming the malformed file.
  2. A turn that captures a memory while a malformed file exists persists that
     capture, removes the task state, and emits no warning.
  3. After any hook or `dream` run, the malformed file is byte-identical to its
     fixture.
  4. After the malformed file is fixed, the next prompt retrieves it, with no
     warning.
  5. A colliding write preserves the malformed file and reports the skipped
     write, while the other memories are written.
  6. `dream` audits the valid memories and lists the skipped file in `errors`.
  7. `memory.report` renders the valid memories and the "Unreadable memory
     files" section.
  8. Claude, Codex, and Antigravity produce equivalent outcomes for slice 1.
  9. A store whose only file is malformed behaves as an empty store with one
     warning.
- **Regression first.** Slice 1 is the regression test for the current failure
  (a whole-hook `systemMessage` with no context). It must fail before any
  production change.
- **Expected values** are independent literals: exact warning lines and exact
  file bytes. They are never recomputed with production helpers.
- **Prior art:**
  - `test_claude_hooks.py`: adapter entrypoints in a real Git repository.
  - `test_dream.py`: on-disk audits.
  - `test_memory_capture_mcp.py`: the report request flow.
  - `tests/local_harness.py`: installed-flow runs.

## Out of Scope

- Automatically repairing, migrating, or rewriting malformed files.
- Quarantine directories or renaming bad files.
- An MCP tool or skill command for fixing memory files.
- Localizing warning text.
- The broader coverage work in spec 46, beyond aligning its malformed-memory
  rows with this contract.

## Further Notes

- This spec supersedes the "Malformed memory contract" decision in
  [spec 46](46-coverage-recovery.md), which pinned the whole-store failure.
  Spec 46 is updated to test this contract instead.
- Consistent with [spec 34](34-okf-memory-format.md): each invalid record still
  fails actionably and is never partially loaded. The change is that the
  failure is contained to its file.
- Implementation runs on a dedicated `fix/47-malformed-memory-isolation` branch
  after this spec is approved.

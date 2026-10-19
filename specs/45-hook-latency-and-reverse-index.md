# 45 — Bounded hook latency and a live reverse dependency index

**Status: Done (2026-10-19)**

## Problem Statement

Memory Stale runs synchronously inside the coding agent's prompt and stop
hooks. The README promises "<10ms local hook execution (`O(Δ symbols)`)", and
[spec 44](44-reactive-coeffects-and-hmr-staleness.md) promises that an in-memory
`ReverseDependencyIndex` resolves affected memories without scanning the whole
memory corpus. Neither promise holds today.

1. **Hook latency grows with repository size.** A workspace snapshot runs one
   `git status` subprocess per tracked or untracked file. The prompt hook
   (`start_task`) builds that snapshot three times: directly, again for the
   source snapshot, and again for the symbol snapshot. It also parses every
   supported source file twice, once for the source signature and once for the
   symbol map. The stop hook (`finish_task`) repeats the same work. On a
   148-file clone of this repository, `start_task` took about 6.9s and
   `finish_task` about 7.1s. Each user prompt and each turn end pays this cost.
2. **The reverse dependency index never matches symbol evidence.** The
   lifecycle queries the index with changed repository-relative file paths
   (`src/auth.py`), but the index is keyed only by evidence keys
   (`symbol:src/auth.py:login`) and locators (`src/auth.py:login`). For symbol
   and test evidence, the lookup always returns an empty set. Staleness still
   works only because a fallback scan over every memory's evidence paths runs on
   every hook. That scan is exactly the corpus-wide work spec 44 claimed to
   remove. The spec 44 unit tests query the index with symbol locators, so they
   cannot catch this.

## Solution

- Each hook entrypoint makes a small, fixed number of Git subprocess calls,
  whatever the number of files in the repository. One `git ls-files` call and
  one `git status` call per snapshot replace the per-file status calls. Each
  hook builds the snapshot once and reuses it for the content, source-signature
  and symbol views.
- Each hook parses each supported source file at most once and derives both the
  source signature and the symbol map from that single parse. The stop hook
  re-parses only files whose content hash changed since the task baseline. For
  every other file it reuses the baseline values already stored in the task
  state.
- The reverse dependency index is also keyed by each evidence item's
  repository-relative file path. The lifecycle's lookup by changed file paths
  then finds every active memory whose evidence lives in a changed file. The
  fallback scan over the whole memory corpus is removed, so the index is the
  only selection path and a broken index fails tests visibly.
- The README replaces the unsupported "<10ms / `O(Δ symbols)`" claim with the
  guarantees the tests enforce, plus one labelled measurement taken after the
  change.

## User Stories

1. As a developer using a coding agent, I want the prompt hook to finish
   quickly on a real repository, so that Memory Stale does not add seconds of
   delay to every prompt.
2. As a developer, I want the stop hook to finish quickly, so that ending a
   turn does not stall the agent.
3. As a developer on a repository with hundreds or thousands of files, I want
   hook cost not to grow by one subprocess per file, so that Memory Stale stays
   usable as the project grows.
4. As a maintainer, I want a deterministic test that fails when a hook's Git
   subprocess count depends on repository size, so that per-file subprocess
   loops cannot return unnoticed.
5. As a maintainer, I want a fixed ceiling on Git invocations per hook, so that
   any new Git call on the hook path is a deliberate, reviewed decision.
6. As a maintainer, I want the latency contract checked without wall-clock
   assertions, so that the default suite stays deterministic and stable in CI.
7. As a developer, I want a memory backed by symbol evidence to become stale
   when its symbol changes semantically, with the reverse index selecting it
   rather than a fallback scan, so that staleness relies on the mechanism the
   documentation describes.
8. As a developer, I want memories whose evidence lives in unchanged files to
   be carried forward without being resolved again, so that the stop hook does
   no work for memories a turn did not touch.
9. As a developer, I want comment-only and formatting-only edits to keep
   memories active, exactly as before, so that the performance work does not
   weaken AST-normalized staleness.
10. As a developer, I want changes that already existed before a task, and
    files staged without content changes, to be treated exactly as they are
    today, so that the snapshot rewrite does not change what counts as a
    change.
11. As a developer, I want renamed, deleted and newly untracked files to be
    detected exactly as before, so that missing evidence still surfaces as
    `file_missing` or `locator_missing`.
12. As a developer, I want automatic provenance capture to report the same
    changed and added symbols as before, so that the uncovered-location
    diagnostic stays accurate.
13. As a maintainer, I want the reverse index to keep answering lookups by
    evidence key and by locator, so that existing callers and spec 44 tests
    keep working.
14. As a maintainer, I want the lookup by changed file path to be the contract
    the lifecycle relies on, so that the index's key space matches what the
    hooks actually observe.
15. As a reader of the README, I want performance claims backed by tests or
    labelled as measurements, so that the project's public description is
    trustworthy.
16. As a reader of spec 44, I want a clear note that spec 45 replaces its
    `O(Δ symbols)` hook-latency claim, so that the specs do not contradict each
    other.
17. As a developer on a host without a supported grammar for some files, I want
    those files to still be included in content hashing and change detection,
    without any added fallback parsing, so that unsupported-language rules
    stay unchanged.

## Implementation Decisions

### Confirmed observable test seam

The highest seam is the real hook entrypoints: the `UserPromptSubmit` and
`Stop` hook scripts, run through the project's `run-python.sh` wrapper against
temporary Git repositories, using the existing hook-subprocess harness in the
local runtime tests. The test puts a logging `git` shim first on `PATH`. The
shim appends one line per invocation to a log file in the test's temporary
directory, then hands off to the real `git` binary with unchanged arguments,
stdin, stdout, stderr and exit code. Calls are counted at the true process
boundary. No project-owned module is mocked.

The reverse-index regression is tested through the public `build_reverse_index`
/ `ReverseDependencyIndex.affected_memories` interface, queried with file
paths, and end-to-end through the stop hook.

### Latency contract

- One `UserPromptSubmit` hook invocation performs **at most 5** Git
  invocations, counted end to end (the wrapper's `rev-parse` included).
- One `Stop` hook invocation performs **at most 5** Git invocations, counted
  the same way.
- For each hook, the invocation count on a repository with 3 files equals the
  count on a repository with 30 files, given the same kind of change.
- The default suite contains no wall-clock assertions.

### Workspace snapshot

- A snapshot runs `git ls-files -z --cached --others --exclude-standard` once
  and `git status --porcelain=v1 -z --untracked-files=all` once. It reads the
  two-character status of each path from the single status output. Paths with
  no status entry get the clean status (`"  "`), as today.
- Renamed and copied entries in the `-z` status output are attributed to their
  destination path. The source path takes its status from the listing as
  today: absent if Git no longer lists it.
- The per-path record (two-character status plus content sha256, or `null` for
  non-files) and the persisted task-state shape do not change. Task states
  written before this change stay readable by `finish_task`.
- Ignored project paths are excluded exactly as today.
- Each hook builds its snapshot once and passes it to the source-signature and
  symbol views instead of rebuilding it.

### Parsing

- The symbol indexer exposes one operation that returns both the source
  signature and the symbol map for a supported file from a single parse. The
  hook runtime uses it for both views. A file that raises `SymbolIndexError`
  is left out of both views, exactly as today.
- In `finish_task`, a file whose content sha256 matches the baseline snapshot,
  and that has baseline source and symbol entries, reuses those baseline
  entries without being re-parsed. Only files that are new, changed, or lack
  baseline entries are parsed.
- Parse-once is an implementation constraint checked in review, not by a
  dedicated test. Tree-sitter is a third-party library, not a system boundary,
  so it is not mocked.

### Reverse dependency index

- `build_reverse_index` also indexes each active memory under the
  repository-relative file path of each evidence item, derived with the same
  `evidence_path` rule the lifecycle uses: symbol and test locators drop the
  trailing `:symbol`, config and schema locators drop the `#fragment`, and
  source locators are already paths.
- `affected_memories` accepts a collection of changed repository-relative file
  paths and returns every active memory with at least one evidence item in one
  of those files. Lookups by evidence key and by locator keep working.
- The lifecycle chooses which memories to re-resolve only from
  `affected_memories(changed_paths)`. The corpus-wide `evidence_path(...) in
  changed_paths` fallback scan is deleted. Inside an affected memory, evidence
  items in unchanged files still carry their stored fingerprint forward without
  being resolved again.

### Documentation

- In the README, the comparison-table cell, the hook-evaluation paragraph and
  the reverse-index paragraph drop "<10ms" and "`O(Δ symbols)`". They state
  the enforced guarantees instead: a fixed number of Git subprocesses per hook,
  at most one parse per supported file, and memory lookup proportional to the
  number of changed files. They add one labelled wall-clock measurement of both
  hooks on a clone of this repository, taken after the change.
- README.md had uncommitted user edits when this spec was written. The
  implementation must keep them or wait until the user has committed them.
  Never overwrite or move them.
- Spec 44 stays as a historical record. This spec replaces its
  `O(Δ symbols)` hook-latency claim and its implication that the index alone
  selected affected memories.

## Testing Decisions

- Good tests here check observable behavior: how many Git processes a hook
  entrypoint starts, which memories end up `active` or `stale` with which
  reasons, and what a public index lookup returns. They do not assert internal
  call order, private helpers, or tree-sitter call counts.
- Expected values are independent literals: fixed ceilings, explicit memory IDs
  and explicit status strings. They are never recomputed with production logic.
- Hook tests use temporary Git repositories, real files and the real hook
  scripts, following the existing local runtime hook tests (prior art: the
  stop-hook staleness and dirty-workspace tests).
- Planned TDD slices, each one red-green cycle:
  1. The `UserPromptSubmit` hook performs the same number of Git invocations on
     a 3-file and a 30-file repository, and at most 5 (fails today: about 3N).
  2. The `Stop` hook performs the same number of Git invocations on a 3-file
     and a 30-file repository, and at most 5 (fails today: about 3N).
  3. `affected_memories` queried with a file path returns the memories whose
     symbol, test, config or schema evidence lives in that file. This is the
     regression test and fails today with an empty set.
  4. With the fallback scan removed, a stop hook that semantically changes a
     symbol marks the memory that depends on it stale, and a memory whose
     evidence lives only in untouched files stays active with its stored
     fingerprint.
- Existing behavior tests must stay green unchanged: comment- and
  formatting-only edits, pre-existing dirty files, legacy fingerprints,
  read-only turns, automatic capture and the uncovered-location diagnostic.
  They are the safety net for the snapshot and parse-once refactor.
- No new pytest marker or wall-clock benchmark is added. The default suite
  still excludes `repository_evaluation`.

## Out of Scope

- A persistent, content-addressed parse cache across tasks. `start_task` still
  parses every supported file once.
- Symbol-level change diffing to drive the index lookup (true
  `O(Δ symbols)` selection).
- Removing the duplicate `rev-parse --absolute-git-dir` call between the
  wrapper and the runtime.
- Any change to what counts as a change, such as ignoring staging-only status
  transitions.
- Git calls made by the MCP server or the installer.
- New grammars, unsupported-language fallbacks, or changes to fingerprint
  formats.
- Wall-clock benchmarks in CI.

## Further Notes

- Baseline measurement before this spec: about 6.9s for `start_task` and about
  7.1s for `finish_task` on a 148-file clone of this repository.
- If parsing still dominates hook time after this change, a follow-up spec can
  evaluate the persistent parse cache that is out of scope here.

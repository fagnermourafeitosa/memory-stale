# 33 — Ignore the project-local `.agents` directory

This spec narrows the project boundary defined by specs 02, 27, 28, and 30.
Files stored below the repository-root `.agents/` directory are runtime,
installation, and memory infrastructure rather than project source evidence.

## Problem Statement

Memory Stale is installed below `.agents/skills/memory-stale/`, while its
automatic source discovery currently considers every tracked or unignored file
in the Git repository. When an installed skill file changes during a task, the
runtime can parse its own Python implementation, create automatic provenance
for it, and request a semantic description. Memory Stale therefore observes and
memorizes its own installed machinery instead of limiting itself to the target
project.

The same boundary can be crossed explicitly: a capture may declare evidence
inside `.agents/`, and an already persisted self-referential memory may remain
eligible for retrieval or Dream auditing. Merely adding `.agents/` to a user's
`.gitignore` would be incomplete because tracked installation files would still
exist and product behavior would depend on repository-specific Git settings.

## Solution

Make the repository-root `.agents/` tree a deterministic product exclusion.
Memory Stale must ignore every relative path whose first path component is
exactly `.agents` when it snapshots a task, discovers supported source, builds
symbol inventories, detects lifecycle changes, creates automatic captures,
retrieves active context, or performs a Dream audit.

Explicit `memory.capture` requests whose evidence resolves inside `.agents/`
must be rejected with an actionable error. Existing stored memories anchored
there are retained for audit compatibility, but they do not participate in
ordinary retrieval or Dream revalidation. The installer, memory store, report,
hooks, and MCP runtime continue to read, write, and execute their own operational
files below `.agents/`; the exclusion applies to project evidence and change
detection, not to product storage.

## User Stories

1. As a project user, I want Memory Stale to ignore its installed skill files,
   so that it never creates memory about its own runtime.
2. As a project user, I want a task that changes only `.agents/` to finish
   without automatic provenance or a missing-semantic-capture diagnostic.
3. As a project user, I want tracked and untracked `.agents/` files treated the
   same way, so that behavior does not depend on `.gitignore` configuration.
4. As a project user, I want normal project code changed in the same task to
   remain eligible for automatic and semantic capture.
5. As a project user, I want explicit evidence inside `.agents/` rejected, so
   that an agent cannot accidentally recreate self-referential memory.
6. As a project user, I want old self-referential memories hidden from ordinary
   context, so that prior accidental captures do not keep influencing tasks.
7. As a maintainer, I want one shared path policy for hooks, MCP capture,
   retrieval, and Dream, so that the exclusion cannot drift across adapters.
8. As a maintainer, I want only the root `.agents` component excluded, so that
   unrelated names such as `.agents-cache` or `src/.agents/` are not silently
   ignored.
9. As an auditor, I want existing Markdown records retained, so that introducing
   the boundary does not destructively rewrite project history.
10. As an installer, I want Memory Stale to keep operating from `.agents/`, so
    that ignoring evidence does not disable the hooks, MCP server, memory store,
    configuration, or reports.

## Observable Test Seam

The highest seam is a real lifecycle hook cycle in a temporary Git repository:

1. Track a supported Python file below `.agents/skills/memory-stale/`.
2. Start a task through the real `UserPromptSubmit` hook.
3. Change the installed Python file semantically.
4. Finish through the real `Stop` hook without `memory.capture`.
5. Observe an empty response, no persisted memory, and no semantic-coverage
   diagnostic.

A complementary mixed-change case modifies both `.agents/` and ordinary project
code and observes automatic capture only for the ordinary code location. The
existing MCP and public retrieval seams cover explicit-capture rejection and
legacy-memory exclusion without testing private path helpers.

These are the confirmed seams for the first implementation tests.

## Expected Behavior

- A path is ignored only when its normalized repository-relative first
  component is exactly `.agents`.
- `.agents`, `.agents/`, and every descendant are excluded whether tracked,
  untracked, modified, added, or deleted.
- `.agents-cache`, `agents/`, and `src/.agents/` are not excluded by this policy.
- Task baselines, current file snapshots, supported-source signatures, and
  symbol inventories contain no ignored path.
- A turn changing only ignored paths creates no automatic capture, persists no
  new memory, marks no existing project memory stale, and returns no
  missing-semantic-capture diagnostic.
- A mixed turn still captures eligible changes outside `.agents/` normally.
- `memory.capture` rejects any evidence graph containing an ignored locator,
  including nested dependencies and every supported evidence type.
- The capture error identifies `.agents/` as ignored project evidence and does
  not stage a partial capture.
- Ordinary retrieval excludes an active memory when any of its evidence belongs
  to `.agents/`. The remaining active corpus alone determines BM25 statistics,
  scoring, ordering, and budget selection.
- Dream does not resolve or revalidate ignored evidence and does not mutate the
  status of a memory anchored there.
- Existing ignored memories remain stored and visible to explicit audit/report
  surfaces; this change does not delete or migrate Markdown records.
- Project-local installation and runtime execution below `.agents/` continue
  unchanged.

## Implementation Decisions

- Introduce one small deterministic path-policy component shared by the hook
  runtime, MCP server, retrieval, and Dream.
- Evaluate normalized repository-relative POSIX components rather than using a
  substring or prefix check. This prevents `.agents-cache` from being excluded
  accidentally.
- Derive the file portion of symbol, test, source, configuration, and schema
  locators through the shared policy before deciding whether evidence is
  ignored.
- Apply the exclusion at the general task snapshot boundary so source and
  symbol snapshots inherit it automatically and ignored paths cannot enter
  changed-path lifecycle input.
- Reject explicit ignored evidence after structural graph validation but before
  resolving fingerprints or staging any capture.
- Filter ignored memories before retrieval corpus statistics are calculated;
  do not score and discard them afterward.
- Skip ignored memories during Dream evidence resolution while retaining their
  stored status and record.
- Do not modify the target repository's `.gitignore`; the runtime policy must be
  reliable even when `.agents/` is intentionally tracked.

## Testing Decisions

- First red-green slice: exercise the complete hook cycle with one tracked
  `.agents/skills/memory-stale/runtime.py` semantic change and require no memory
  and no diagnostic. The current implementation must fail by producing an
  automatic symbol record and missing semantic coverage.
- Add a mixed-change hook test proving that an ordinary supported source change
  is still captured while the `.agents/` change is absent from persisted claims
  and evidence.
- Add an MCP integration test that changes a supported `.agents/` symbol and
  attempts semantic capture; require an actionable rejection and verify that no
  capture was staged.
- Add a public retrieval test with one ignored active memory and one ordinary
  active memory. Require only the ordinary memory to influence and appear in
  returned context.
- Add a Dream test proving ignored evidence is not resolved, marked stale, or
  included in the audit summary.
- Cover exact-root matching with behavior examples for `.agents/`,
  `.agents-cache`, and `src/.agents/` through public operations rather than
  direct tests of a private predicate.
- Use real files, real Git repositories, real hook scripts, the MCP stdio
  process, and persisted Markdown. Do not mock project-owned modules.
- Run focused red-green slices followed by formatting, lint, strict typing, and
  the complete default test suite. The repository evaluator remains opt-in and
  is not required because this boundary does not change its fixed corpus.

## Documentation Decisions

- State in the public README that `.agents/` is operational infrastructure and
  is excluded from evidence discovery, automatic capture, retrieval, and Dream.
- Clarify that users do not need a `.gitignore` entry for Memory Stale to enforce
  this boundary.

## Out of Scope

- Deleting, migrating, or rewriting existing self-referential memory files.
- Ignoring other dot-directories, dependency folders, generated directories, or
  user-configured path patterns.
- Adding a general ignore configuration language.
- Changing supported grammars, semantic fingerprints, retrieval scoring,
  lifecycle status names, context budgets, or report rendering.
- Preventing users from viewing or manually deleting old ignored records.
- Adding `.agents/` to the target repository's `.gitignore` automatically.

## Further Notes

- This is a product-boundary exclusion, not a performance optimization.
- The distinction between operational storage and evidence is intentional:
  Memory Stale must execute and store state below `.agents/` without treating
  those files as facts about the target project.

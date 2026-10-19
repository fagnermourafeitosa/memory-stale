# 46 — Behavioral coverage recovery

**Status: Done (2026-10-19)**

## Problem Statement

`pyproject.toml` requires 90% branch coverage, but `uv run pytest --cov` reports
84.28% and fails. The default suite passes (220 tests), so the coverage gate is
the only signal of the shortfall, and it predates spec 45. The real problem is
underneath that number. Several user-facing guarantees have no test that would
fail if they broke:

1. **Hooks must never block the agent and must never fail silently.** The
   Claude, Antigravity, and Codex adapters each define what happens on a
   non-Git directory, a malformed payload, a missing turn identifier, or a
   missing tool call. Most of these paths are unexercised, especially in the
   Antigravity adapter (70%) and the Claude adapter (80%).
2. **Document evidence must become stale only on semantic change.** `config`
   and `schema` evidence (JSON, YAML, TOML documents addressed by
   `path#/json/pointer`) are a documented evidence type. Their rejection rules
   are largely untested: missing node, non-schema document, TOML used as
   schema, path escaping the repository, unparsable document, non-canonical
   values. The core promise is also untested for document evidence: a value
   change marks the memory stale, while reformatting keeps it active. Evidence
   resolution sits at 67%.
3. **Stored memories must stay readable across schema versions.** Specs 14 and
   16 declare that unversioned, v3, and v4 memories migrate deterministically
   and idempotently. The v3/v4 evidence loader has no test at all. The
   behavior for a malformed memory file was unpinned: one corrupt file made
   every hook fail. [Spec 47](47-malformed-memory-isolation.md) defines the
   per-file isolation contract that this spec's tests must assert.
4. **Audit must explain why evidence broke.** `dream` records `file_missing`,
   `locator_missing`, or `unresolvable` stale reasons, and it isolates
   unexpected per-item failures in its error list. None of these outcomes is
   asserted.
5. **Rejected captures must leave nothing behind.** The lifecycle validates
   about fifteen capture-shape rules (`supported_by`, `dependencies`,
   `relationship`, retrieval terms). Most are untested, and some may be
   unreachable because the MCP layer already rejects the same input.

Coverage is a guardrail, not the goal. The goal is that each guarantee above
has a behavioral test at the highest public seam, and that 90% follows from
that as a consequence.

## Solution

- Add behavioral tests, organized by guarantee, through the existing public
  seams: the hook adapter entrypoints (JSON in, JSON out) running against a
  real temporary Git repository, the MCP capture tool, `dream`, and the
  installed local harness.
- Pin current behavior. Where a test exposes a bug or an undesirable contract,
  record it under Findings in this spec and fix it in a dedicated `fix/` spec.
  This spec does not change production behavior.
- Remove production code only when it is proven unreachable from every public
  seam and has no observable behavior. Each removal is listed explicitly in
  this spec.
- Keep `fail_under = 90`. If the guarantee-driven tests still leave the total
  below 90%, report the remaining gap with the specific uncovered branches and
  propose follow-up specs. Never write tests just to hit lines.

## User Stories

1. As a developer using Claude Code, I want the prompt hook to stay silent in a
   directory that is not a Git repository, so that Memory Stale never adds
   noise outside the projects it supports.
2. As a developer using Claude Code, I want a malformed hook payload to produce
   exactly one actionable `systemMessage` with exit code 0, so that the agent
   keeps working and I can see what went wrong.
3. As a developer using Claude Code, I want a payload carrying the wrong
   `hook_event_name` for its entrypoint to be reported rather than processed,
   so that a misconfigured hook cannot corrupt task state.
4. As a developer using Claude Code subagents, I want an empty `agent_id` to be
   reported as invalid, so that subagent task isolation cannot silently merge
   into the main task.
5. As a developer using Claude Code, I want the post-tool and stop hooks to
   no-op in a non-Git directory, so that every event follows the same
   non-blocking contract as the prompt hook.
6. As a developer using Antigravity, I want hooks without a conversation id to
   no-op silently, so that Memory Stale runs only for turns it can track.
7. As a developer using Antigravity, I want a post-tool payload without a
   `toolCall`, or with a tool call that has no name, to no-op, so that partial
   events do not corrupt the task ledger.
8. As a developer using Antigravity, I want the repository resolved from
   `workspacePaths[0]` first, then `cwd`, then the process working directory,
   so that multi-root workspaces bind to the expected project.
9. As a developer using Antigravity, I want every event in a non-Git directory
   to return its empty response, so that the harness never sees an error for an
   unsupported directory.
10. As a developer using Antigravity, I want an internal failure in any event to
    produce one `systemMessage` naming the event, so that failures are visible
    without blocking.
11. As a developer using Codex, I want the same non-Git, malformed-payload, and
    failure guarantees as the other harnesses, so that the three integrations
    behave identically.
12. As an agent, I want to capture a memory backed by a JSON, YAML, or TOML
    `config` node, so that durable facts about configuration are remembered.
13. As an agent, I want to capture a memory backed by a JSON Schema or OpenAPI
    `schema` node, so that durable facts about contracts are remembered.
14. As an agent, I want a capture whose document pointer does not exist to be
    rejected with a clear message, so that I fix the locator instead of storing
    unverifiable evidence.
15. As an agent, I want `schema` evidence that targets a document that is
    neither JSON Schema nor OpenAPI to be rejected, so that the `schema` type
    keeps its meaning.
16. As an agent, I want TOML `schema` evidence, and unsupported file formats,
    rejected, so that only supported document kinds are fingerprinted.
17. As an agent, I want locators that are absolute or contain `..` rejected, so
    that evidence cannot point outside the repository.
18. As an agent, I want a locator without a `#/pointer`, or with an invalid JSON
    Pointer escape, rejected, so that document evidence is always addressed
    exactly.
19. As an agent, I want an unparsable document rejected, so that broken files
    never produce a fingerprint.
20. As an agent, I want JSON Pointer array indexes and `~0`/`~1` escapes
    resolved exactly, so that I can address any node in a real document.
21. As a developer, I want a memory backed by a document node to become stale
    when that node's value changes, so that outdated configuration knowledge is
    flagged.
22. As a developer, I want reformatting, key reordering, or changes to sibling
    nodes to keep the memory active, so that staleness reflects semantics, not
    layout.
23. As a developer upgrading Memory Stale, I want unversioned, v3, and v4 memory
    files to load and be rewritten in the current format without losing claim,
    status, stale reasons, evidence, or graph edges, so that my history survives
    upgrades.
24. As a developer upgrading Memory Stale, I want migration to be idempotent, so
    that running hooks repeatedly does not keep rewriting or drifting my
    memories.
25. As a developer, I want every malformed-file kind (invalid front matter,
    invalid OKF type, unknown status, stale reason that references unknown
    evidence, invalid graph) covered against the spec 47 isolation contract,
    so that one bad file never disables the others.
26. As a developer, I want `dream` to mark a memory stale with `file_missing`
    when its evidence file is deleted, so that the audit explains the breakage.
27. As a developer, I want `dream` to report `locator_missing` when the symbol or
    document node no longer exists, so that I know the file survived but the
    target did not.
28. As a developer, I want `dream` to report `unresolvable` when the evidence
    document can no longer be parsed, so that corruption is distinguished from
    deletion.
29. As a developer, I want one memory's unexpected audit failure to be listed in
    the `dream` errors without aborting the audit of the other memories, so that
    a single bad file does not hide every other result.
30. As an agent, I want each invalid capture shape (non-array evidence, missing
    primary, duplicate locators, unknown `supported_by` node, malformed
    dependency, unknown relationship, invalid retrieval terms) rejected with a
    structured message, so that I can correct the capture in the same turn.
31. As a developer, I want a rejected capture to leave no memory file and no
    staged candidate, so that the memory store never holds partial state.
32. As a maintainer, I want `uv run pytest --cov` to pass at the configured 90%
    threshold, so that the coverage gate is meaningful again.
33. As a maintainer, I want unreachable defensive code removed rather than
    exercised by artificial tests, so that coverage measures real behavior.

## Implementation Decisions

- **Guarantee-first.** The spec lists guarantees, and tests are written to
  prove them. Coverage is the acceptance check, not the design driver.
- **No production behavior changes.** Production code changes are limited to
  removing code proven unreachable, listed under "Approved removals". Any
  behavior a test exposes as wrong goes under Findings and into its own `fix/`
  spec with its regression test.
- **Approved removals.**
  - `evidence.parse_items` has no caller in `src`, `tests`, or `evaluator`.
    Every capture path uses `parse_graph`. Remove it.
  - Lifecycle capture-shape validations that the MCP capture tool always
    rejects first, and the `dream` per-item `except Exception` branch if no
    real file condition reaches it. These become removal candidates only after
    a test shows the behavior is unreachable through every seam. Each one is
    added to this list, by updating the spec, before it is deleted.
- **Malformed memory contract.** [Spec 47](47-malformed-memory-isolation.md)
  defines it: per-file isolation, the bad file preserved byte for byte, and
  warnings at prompt time, in `dream`, and in the report. Spec 47 is
  implemented first. This spec then covers the remaining malformed-file kinds
  against that contract instead of pinning the old whole-store failure.
- **Legacy formats remain supported.** The unversioned `signatures` schema,
  schema v3, and schema v4 remain part of the contract from specs 14 and 16.
- **Antigravity repository resolution precedence** is
  `workspacePaths[0]` > `cwd` > the process working directory. The tests
  document this precedence as the contract.

## Testing Decisions

- **Seams (confirmed with the user):**
  1. Hook adapter entrypoints for Claude, Antigravity, and Codex (`run_*` with
     JSON input and output streams) against a real temporary Git repository.
  2. The MCP capture tool, through the same request handling the installed MCP
     server uses.
  3. `dream` on a real repository with memory files on disk.
  4. The installed local harness, for migration scenarios that need the full
     prompt-to-stop flow.

  No test calls private loaders or fingerprint helpers (`MemoryStore._load*`,
  `evidence._document_fingerprint`, and similar). Malformed and legacy memories
  enter as real files in the memory directory, and their effect is observed
  through a seam.
- **Adapter contract matrix.** Use one parametrized table per harness, with
  rows of event × condition (non-Git directory, malformed JSON, wrong event
  name, empty `agent_id`, missing turn or conversation id, missing or nameless
  `toolCall`, internal failure). Each row asserts the exact response shape,
  that the exit code is 0, and that no task state or memory was written.
  Internal failure is triggered through a real condition (for example, a
  malformed memory file in the store), never by mocking project modules.
- **Document evidence.** Use real JSON, YAML, and TOML fixtures. Each rejection
  rule has one row asserting its message. The stale-versus-active pair runs
  through capture and then a document edit (value change compared with
  reformatting, key reordering, or sibling edits), observed via the stop hook
  or `dream`.
- **Migration.** Use handwritten literal fixtures for unversioned, v3, and v4
  memories. Assert that the rewritten file preserves claim, status, stale
  reasons, evidence, `supported_by`, and dependencies. Then run the flow again
  and assert byte-identical output to prove idempotence.
- **Malformed memories.** Use one row per invalid-file kind not already covered
  by spec 47. Assert the spec 47 outcome: the valid memories are still
  injected, one warning names the file, the file is unchanged, and `dream`
  lists it in `errors`.
- **Dream audit.** Use real deletions, symbol or node removals, and corrupted
  documents. Assert the stale reason recorded in the rewritten memory file.
  Error isolation uses an unreadable source file (`chmod 000`), skipped when
  the suite runs as root. If that condition surfaces as an `EvidenceError`
  rather than a generic exception, the generic branch becomes a removal
  candidate instead of a test target.
- **Capture rejection.** Use one table row per invalid shape through the MCP
  capture tool. Assert the structured error and that the memory directory and
  the staged-candidate area are unchanged.
- **Test placement.** Extend `test_claude_hooks`, `test_antigravity_adapter`,
  `test_dream`, and `test_memory_capture_mcp`, and add `test_memory_migration`
  for legacy and malformed memory files.
- **Prior art.** Follow the existing test style:
  - `test_claude_hooks.py`: adapter entrypoints, a real `git init`, payload
    builders.
  - `test_memory_capture_mcp.py`: capture rejection tables.
  - `test_dream.py`: audits over on-disk memories.
  - `tests/local_harness.py`: installed-flow runs.
- **TDD discipline.** Each slice that pins existing behavior is a
  characterization test, and a test that passes immediately is acceptable for
  that kind of slice. A slice that reveals a bug follows `test -> fail` in its
  own `fix/` spec. Removals are tooling-like deletions verified by the full
  suite.
- **Acceptance.** All four required validation commands pass, and
  `uv run pytest --cov` passes at `fail_under = 90`. If it does not, the spec
  records the residual uncovered branches with reasons and proposed follow-ups.

## Out of Scope

- Lowering `fail_under` or adding coverage exclusions (`pragma: no cover`,
  `omit`) to reach the threshold.
- Changing the malformed-memory contract beyond spec 47.
- Fixing any bug these tests uncover. Each fix goes in its own `fix/` spec.
- Coverage gaps in `symbol_index` (88%) and `evaluation` (87%). They need
  grammar and corpus work under a separate spec.
- `mcp_server` gaps beyond what the capture-rejection table reaches naturally.
- The 100-trial repository evaluation.

## Findings

Result: `uv run pytest --cov` passes at 92.19% (313 tests), up from 84.28%.
This spec did not change any production behavior.

- **Removed:** `evidence.parse_items` had no caller. Every capture path uses
  `parse_graph`.
- **Kept, because they are reachable:**
  - The `dream` per-item `except Exception` branch. An unreadable source file
    raises `PermissionError`, which lands in `errors`.
  - The lifecycle capture-shape validations. A corrupt staged capture in the
    task state reaches them at stop time. They are now covered by a rejection
    table that asserts no memory is written.
- **Bug candidate (follow-up `fix/`):** when `dream` cannot read a source file,
  each memory backed by it is listed in `errors` but is still marked `stale`.
  `audited` also omits it. A transient read failure should not invalidate
  evidence.
- **Bug candidate (follow-up `fix/`):** a corrupt staged capture makes the stop
  hook fail as a whole. The task state is left behind, and the turn's other
  captures are lost. This is the same containment problem spec 47 solved for
  memory files.
- **Pinned as-is:** the Claude and Codex prompt hooks report
  `Memory Stale is inactive: cwd is not inside a Git repository.` outside Git.
  Every other event, and every Antigravity event, stays silent.
- **Residual gaps** remain in `symbol_index` (88%) and `evaluation` (87%). Both
  are out of scope, as decided above.

## Further Notes

- Baseline (2026-10-19, after spec 45): total coverage 84.28%. Per module:
  `evidence` 67%, `antigravity_adapter` 70%, `memory_store` 76%,
  `claude_adapter` 80%, `dream` 84%, `codex_adapter` 88%, `mcp_server` 89%,
  `lifecycle` 90%.
- The scope was agreed through a `grilling` session. The user's guiding
  requirement was tests that prove the tool really works.

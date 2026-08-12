# Memory Stale

Automatic, code-anchored memory maintenance for Codex.

Memory Stale is a Codex plugin, not a CLI workflow. It gives Codex relevant
project memory before a task, lets the same Codex instance capture durable
knowledge while working, and invalidates memories when the code that supported
them changes.

No second LLM, remote service, vector database, or manual `remember` command is
required.

## The problem

Persistent memory is useful only while it remains true.

A coding agent may remember that `AuthService.login` accepts only a password.
If that method later gains MFA validation, the old memory becomes dangerous:
it is easy to retrieve, confidently stated, and no longer supported by the
code.

Memory Stale treats Git and code structure as evidence. A memory is connected
to the exact symbols that support its claim. When one of those symbols changes,
disappears, or stops resolving, the memory becomes `stale` and is excluded from
future task context.

## How it works

The plugin participates in three Codex lifecycle events and exposes one local
MCP tool:

```text
User submits task
  → UserPromptSubmit loads relevant active memories
  → Codex receives them as additional context

Codex works
  → PostToolUse builds a per-task change ledger
  → Codex calls memory.capture for durable knowledge, when appropriate

Codex finishes the turn
  → Stop compares the final workspace with the task-start snapshot
  → validates captured claims and symbol references
  → writes valid memories
  → marks affected existing memories stale
  → optionally refreshes the HTML report
```

Hooks perform deterministic local work. Codex provides semantic judgment
because it already understands what it implemented; the plugin does not start
another model to summarize the diff.

## What becomes a memory

The user prompt is never stored as the memory. A request describes intended
work, not the final truth of the codebase.

Before finishing a task, the bundled skill asks Codex to capture a claim only
when all of these are true:

- it defines durable behavior, a contract, a constraint, an architectural
  decision, or a non-obvious operational fact;
- another agent could make a meaningful mistake without knowing it;
- the final code contains symbols that support the claim;
- it says more than “this task happened” or “these files changed.”

Examples:

```text
Do not store: "Added MFA to login."
Do not store: "Changed auth.py and its tests."

Store: "Login validates password and MFA before creating a session."
Refs:  src/auth.py:AuthService.login
```

Trivial fixes, formatting changes, mechanical refactors, and generic diff
summaries do not become memories.

## `memory.capture`

`memory.capture` is a local MCP tool used internally by Codex. It is not a
human-facing command.

Conceptually, Codex sends:

```json
{
  "kind": "behavior",
  "claim": "Login validates password and MFA before creating a session.",
  "refs": [
    "src/auth.ts:AuthService.login",
    "src/session.ts:SessionService.create"
  ],
  "durability_reason": "Future auth changes must preserve this ordering."
}
```

Allowed v1 kinds are:

- `behavior`
- `contract`
- `constraint`
- `architecture`
- `operation`

Every reference must exist in the final code, resolve to a supported
tree-sitter symbol, and have been modified during the current task. Captures
with the same normalized claim, kind, and refs are idempotent. The plugin does
not guess at semantic duplicates with different wording.

## Symbol-level staleness

Memory Stale uses tree-sitter to resolve symbols and build canonical structural
signatures.

The signature includes syntax structure and real tokens, while ignoring
whitespace and comments. Therefore:

- reformatting or editing comments does not make memory stale;
- changing logic, identifiers, literals, parameters, or structure does;
- deleting or renaming a symbol does;
- deleting its file does.

V1 supports:

- TypeScript and JavaScript
- Python
- Go
- Java
- Kotlin
- Rust

There is deliberately no file-level fallback. If a language has no supported
grammar, the reference is rejected instead of creating an imprecise memory.

## Memory lifecycle

V1 has two states:

```text
active → supported by current symbol signatures and eligible for retrieval
stale  → at least one supporting reference changed or no longer resolves
```

When code changes, an existing memory becomes `stale`; it is not silently
rewritten or marked as superseded. If the completed implementation establishes
a new durable fact, Codex can capture that fact as a new memory. The old stale
record remains available for audit but never enters normal task context.

Memories are Markdown files with structured front matter stored in the project:

```text
<repo>/.agents/skills/.agent-memory/memories/*.md
```

Project configuration lives at:

```text
<repo>/.agents/skills/.agent-memory/config.toml
```

Durable memories belong to the repository and can be reviewed and versioned in
Git. Derived indexes, task snapshots, and temporary ledgers are local cache,
not sources of truth.

## Relevant context before a task

Only `active` memories are eligible for retrieval. Ranking is deterministic:

1. exact path or symbol matches;
2. BM25 over the claim and durability reason;
3. a boost for related code references;
4. selection within the configured token budget.

The default context budget is 1500 tokens and can be changed per project.
There are no embeddings in v1.

## Dirty workspaces and multi-file tasks

At `UserPromptSubmit`, the plugin snapshots the current working tree. During
the task, `PostToolUse` records writes. At `Stop`, the final diff is compared
with the snapshot.

This separates pre-existing user changes from changes made during the Codex
task and supports tasks that modify many files and symbols. A single claim may
reference multiple changed symbols; each reference is validated independently.

## Manual reconciliation with Dream

Normal memory maintenance is automatic. For an explicit audit, the user can
invoke:

```text
/memory-stale dream
```

Dream uses the current Codex instance to inspect stale memories, broken refs,
and unresolved symbols. It applies valid adjustments directly, uses
`memory.capture` for newly supported claims, and reports created memories,
stale records, and errors.

Dream does not rewrite healthy `active` memories without evidence and does not
run another LLM.

## HTML report

The report is an optional artifact, not the primary interface. By default it
is generated only when explicitly requested. Projects may enable automatic
regeneration whenever memory changes.

The report shows active and stale memories, code references, and staleness
reasons. Its output location is configurable.

## Architecture

```text
Codex plugin
├── bundled skill
│   ├── durable-memory policy
│   └── /memory-stale dream
├── local MCP server
│   └── memory.capture
├── lifecycle adapters
│   ├── UserPromptSubmit
│   ├── PostToolUse
│   └── Stop
└── pure core
    ├── tree-sitter symbol indexers
    ├── task change ledger
    ├── Markdown memory store
    ├── staleness lifecycle
    ├── BM25 retrieval
    └── optional HTML renderer
```

Hooks and MCP handlers remain thin adapters around the local memory engine, so
the plugin can be tested without depending on a live Codex session.

## Failure behavior

Memory maintenance must never block the user's coding task.

If capture, parsing, indexing, persistence, or a hook fails, the plugin records
a clear local error, avoids partial memory writes, and lets Codex finish the
task normally. Git is required; outside a Git repository, the plugin explains
why it is inactive and performs no memory operations.

## Project status

Memory Stale is pre-alpha. The product contract and architecture are defined,
but no installable release is available yet. Storage formats, configuration,
and plugin interfaces may change before `0.1.0`.

## Current limitations

- There is no installable release yet.
- Only the seven languages listed above are supported in v1.
- Syntax that tree-sitter cannot resolve cannot be used as memory evidence.
- All refs in a new capture must have changed in the current task. This favors
  precision over broader contextual links.
- Codex decides whether a fact is durable. The skill provides a strict policy,
  but a local script cannot prove the semantic value of prose.
- Deduplication is exact and deterministic, not semantic.
- Retrieval is lexical and structural; phrasing with no shared terms or code
  refs may not rank well.
- Stale memory is excluded rather than automatically repaired during ordinary
  tasks. Dream provides explicit reconciliation.
- Best-effort, non-blocking failure behavior means a failed hook can miss a
  memory update rather than interrupting the user's work.
- The plugin depends on Codex hook trust and project-local Git state.

## Roadmap

### Toward `0.1.0`

- Ship the installable Codex plugin, local MCP server, lifecycle hooks, and
  project-local memory store.
- Deliver tree-sitter support for TypeScript, JavaScript, Python, Go, Java,
  Kotlin, and Rust.
- Deliver deterministic retrieval, staleness evaluation, Dream reconciliation,
  and the optional HTML report.
- Publish an end-to-end test suite covering dirty workspaces, multi-file tasks,
  hook failures, and every supported grammar.

### Beyond `0.1.0`

- Add grammar packs for more languages without weakening the no-fallback rule.
- Improve symbol resolution for overloads, anonymous functions, generated
  code, macros, and partial classes.
- Add stronger diagnostics for missed captures and failed hook runs.
- Expand Dream with dry runs, review modes, and targeted scopes.
- Add ranking evaluation and quality metrics before considering an optional
  semantic retrieval layer.
- Add report history, memory diffs, and schema migration tooling.

## License

MIT

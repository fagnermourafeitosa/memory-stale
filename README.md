# Memory Stale

Automatic, code-anchored project memory for Codex.

Memory Stale gives Codex relevant knowledge before a task and requires
revalidation when the recorded code evidence changes. It runs as a Codex plugin through
lifecycle hooks, a bundled skill, and a local MCP server. There is no separate
human-facing CLI, second LLM, remote service, vector database, or manual
`remember` command.

> [!NOTE]
> Memory Stale is currently a pre-alpha local development build. The complete
> plugin has been exercised end to end, but no public marketplace release has
> been published yet.

## Why it exists

Persistent memory is useful only while its recorded evidence remains unchanged.

Suppose an agent remembers that `AuthService.login` accepts only a password. If
that method later gains MFA validation, the old fact becomes dangerous: it is
easy to retrieve, confidently stated, and no longer supported by the code.

Memory Stale connects each durable claim to the exact code symbols that support
it. Git identifies the working tree, tree-sitter provides structural signatures,
and deterministic lifecycle rules decide whether its recorded evidence still
matches the capture.

```text
active memory + unchanged evidence → available to future Codex tasks
active memory + changed evidence   → stale and excluded pending revalidation
new durable behavior               → captured as a new active memory
```

`active` means every recorded item of evidence still matches its captured
fingerprint. It does not prove that the claim is true or that its provenance is
complete. `stale` means recorded evidence changed, disappeared, or could not be
resolved, so the claim requires revalidation; it does not prove the claim false.
The stale record remains available for audit and is never silently rewritten as
if it had always contained the new behavior.

## A 60-second example

Imagine Codex changes `src/auth.py:AuthService.login` and establishes this
durable behavior:

```text
Login validates password and MFA before creating a session.
```

During that turn, Codex stages the claim with `memory.capture`. The local tool
verifies that the referenced symbol exists and changed during the task, then
computes its structural signature. At `Stop`, Memory Stale reconciles existing
evidence and writes the validated capture as an active Markdown memory.

On a later task mentioning `src/auth.py:AuthService.login`, Codex receives:

```text
Memory Stale active context:
- Login validates password and MFA before creating a session.
  Refs: src/auth.py:AuthService.login
```

If the method's logic changes, the old memory becomes `stale`. Formatting and
comment-only edits do not invalidate it. If the completed change establishes a
replacement fact, Codex captures a new active memory while retaining the stale
history.

## Requirements

- Codex with plugin, hook, skill, and local MCP support
- Git
- [`uv`](https://docs.astral.sh/uv/) available on `PATH`
- Python 3.10 or newer, selected and managed through `uv`

The plugin uses `uv` exclusively. On first use it creates its environment,
dependency cache, and tree-sitter grammar cache under Codex's plugin data
directory. It does not install project dependencies globally and does not use
`pip`.

## Local installation

There is no public Memory Stale marketplace release yet. The currently tested
installation uses Codex's personal marketplace and this repository as a local
plugin source.

Clone the source into the personal plugin layout:

```bash
mkdir -p ~/plugins
git clone https://github.com/fagnermourafeitosa/memory-stale.git ~/plugins/memory-stale
mkdir -p ~/.agents/plugins
```

Create `~/.agents/plugins/marketplace.json` if you do not already maintain a
personal marketplace:

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
  },
  "plugins": [
    {
      "name": "memory-stale",
      "source": {
        "source": "local",
        "path": "./plugins/memory-stale"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
```

If that file already exists, merge the Memory Stale entry into its `plugins`
array instead of replacing the file. Then install and verify the plugin:

```bash
codex plugin add memory-stale@personal
codex plugin list
```

Start a new Codex conversation after installation so the skill, MCP tools, and
hooks are loaded from the installed plugin snapshot. Review and trust the hooks
before enabling them. The hooks invoke only the bundled local bootstrap and
memory engine.

## Normal use

Memory maintenance is automatic:

1. `UserPromptSubmit` retrieves relevant active memories and adds them to the
   Codex context.
2. `PostToolUse` records task activity while Codex works.
3. Codex calls `memory.capture` only for durable facts supported by changed code.
4. `Stop` compares the final workspace with the task-start snapshot, validates
   refs and signatures, persists captures whose recorded evidence resolves, and
   marks affected memories stale for revalidation.

You do not call `memory.capture` yourself. Ask Codex to work normally. The
bundled skill decides when a fact is durable enough to propose, while the local
engine deterministically validates its code evidence.

### What qualifies as durable memory

A useful memory describes behavior, a contract, a constraint, an architectural
decision, or a non-obvious operational fact that could prevent a future mistake.

```text
Do not store: "Added MFA to login."
Do not store: "Changed auth.py and its tests."

Store: "Login validates password and MFA before creating a session."
Refs:  src/auth.py:AuthService.login
```

Trivial fixes, formatting changes, mechanical refactors, user prompts, and
generic diff summaries should not become memories.

## Verify that it works

Use a Git repository containing a supported language:

1. Ask Codex to make a meaningful behavior change to a named function, method,
   class, struct, or type.
2. If the result establishes a durable fact, ask Codex to confirm that Memory
   Stale captured it.
3. Inspect `.agents/skills/.agent-memory/memories/` for an `active` Markdown
   memory with the expected claim and ref.
4. Start a new task mentioning that exact path or symbol. The active claim
   should appear in Codex's injected context.
5. Change the referenced symbol semantically. The previous memory should become
   `stale` and disappear from normal context; a replacement fact may become a
   new active memory.

An unrelated prompt should not retrieve the memory. A comment-only or formatting
change should not make it stale.

## Storage and version control

Memories are plain Markdown with structured front matter:

```text
<repo>/.agents/skills/.agent-memory/memories/*.md
```

Each file is an immutable evidence revision. It records a stable `claim_id`, a
fingerprint-derived `revision_id`, `schema_version: 2`, and the observed Git
commit and time when available. Re-capturing the same claim after its evidence
changes preserves the earlier revision and restores one new `active` revision
to normal context. Repeating an identical evidence revision is idempotent.

Older pre-alpha files without `schema_version` are read as legacy records and
migrated deterministically on their next write; their prior ID remains in
front matter as migration provenance. The HTML report groups revision history
by claim, while context retrieval uses only the current active revision.

## Staleness evaluation corpus

`evaluation-corpus.yaml` is a versioned, human-labeled set of before-and-after
fixtures used by the normal test suite. Its deterministic evaluator runs the
same lifecycle against real source files, then reports two deliberately separate
trade-offs: `unnecessary_revalidation_rate` for `preserved` claims marked stale,
and `missed_semantic_change_rate` for `changed` claims left active. The current
baseline is versioned in `evaluation-baseline.yaml`; its known instrumentation
false-stale and indirect-policy false-negative cases document limitations rather
than redefining evidence staleness as claim truth.

Project configuration lives at:

```text
<repo>/.agents/skills/.agent-memory/config.toml
```

Commit the memory files and configuration when the team wants to share durable
project knowledge through Git. Review them like documentation. Active and stale
records are both intentional history.

Task snapshots and temporary ledgers live under the repository's Git metadata.
The Python environment, dependency cache, and grammar cache live in Codex's
plugin data directory. They are derived local state and should not be committed.
The optional HTML report may be committed or ignored according to project
policy.

## Configuration

All fields are optional. Defaults are shown below:

```toml
context_budget = 1500
auto_report = false
report_path = "memory-report.html"
```

- `context_budget` is a positive approximate token budget for injected memory.
- `auto_report` regenerates the HTML report at the end of lifecycle processing.
- `report_path` must be a non-empty relative path inside the repository.

Invalid configuration is surfaced as a structured, non-blocking plugin error.

## Memory health and Dream

Ask Codex to generate the Memory Stale health report when you want an HTML view
of active and stale memories, refs, durability reasons, and staleness reasons.
Codex calls the local `memory.report` MCP tool and returns the configured path.
The report is not generated on ordinary turns unless `auto_report` is enabled.

For an explicit repository-wide audit, invoke:

```text
/memory-stale dream
```

The deterministic `memory.dream` tool checks current symbol evidence, reports
stale or broken items, and marks active memories whose evidence no longer
matches as stale for revalidation. The same
Codex instance can then review those results and use `memory.capture` for new
durable facts. Dream does not launch another LLM and does not rewrite healthy
active memories without evidence.

## MCP tools

The local MCP server exposes three tools for the bundled skill and Codex. They
are implementation surfaces, not a separate end-user CLI.

- `memory.capture` stages a durable claim anchored to symbols changed during the
  active turn.
- `memory.dream` performs an explicit wide evidence-revalidation audit.
- `memory.report` writes the optional static HTML health report.

Capture kinds are `behavior`, `contract`, `constraint`, `architecture`, and
`operation`. Captures with the same normalized claim, kind, and refs are
idempotent. Deduplication is exact and deterministic, not semantic.

## Symbol-level staleness

Memory Stale uses tree-sitter to resolve symbols and create canonical structural
signatures. Signatures include syntax structure and real tokens while ignoring
whitespace and comments.

- Logic, identifiers, literals, parameters, or structural changes make a memory
  stale and require its claim to be revalidated.
- Deleting or renaming a symbol makes its recorded evidence stale.
- Deleting its file makes its recorded evidence stale.
- Formatting and comment-only changes do not make it stale.

V1 supports TypeScript, JavaScript, Python, Go, Java, Kotlin, and Rust. There is
deliberately no file-level fallback. Unsupported languages and unresolved syntax
are rejected instead of producing imprecise evidence.

Every ref in a new capture must resolve in the final code and must have changed
during the active task. A claim may reference multiple changed symbols; each ref
is validated independently.

## Retrieval quality

Only active memories are eligible for normal context. Retrieval is deterministic:

1. BM25 scores shared terms in the claim and durability reason.
2. An exact path or symbol occurrence in the prompt receives a strong boost.
3. Ranked memories are selected within the configured context budget.

Stale memories are always excluded. There are no embeddings in v1, so prompts
with neither shared terms nor code refs intentionally return no memory context.

## Architecture

```text
Codex plugin
├── bundled skill
│   ├── durable-memory policy
│   └── /memory-stale dream workflow
├── local MCP server
│   ├── memory.capture
│   ├── memory.dream
│   └── memory.report
├── lifecycle adapters
│   ├── UserPromptSubmit
│   ├── PostToolUse
│   └── Stop
└── deterministic local core
    ├── tree-sitter symbol indexers
    ├── task snapshots and change ledger
    ├── Markdown memory store
    ├── staleness lifecycle
    ├── BM25 retrieval
    └── static HTML renderer
```

Hooks and MCP handlers are thin adapters around the local engine, allowing the
core behavior to be tested with real temporary Git repositories and without a
live Codex session.

## Failure behavior and privacy

Memory maintenance must not block the coding task. Hook, parsing, indexing,
configuration, and persistence failures are converted into actionable structured
messages. Writes are atomic, so a failure should not leave a partially written
memory. Best-effort behavior means a failed hook may miss an update instead of
interrupting the user's work.

Git is required. Outside a Git worktree, the plugin explains that it is inactive
and performs no memory operation.

Memory files, task state, indexes, reports, and caches remain local. The plugin
does not call another model or send memory to a dedicated service. Active memory
selected for a task is added to the current Codex context, which is the intended
product behavior.

## Current status

Memory Stale is a pre-alpha `0.1.0` development build. The following are
implemented and covered by integration or end-to-end tests:

- installable local Codex plugin with isolated `uv` bootstrap;
- bundled skill, lifecycle hooks, and three local MCP tools;
- Markdown memory store and `active → stale` evidence-revalidation lifecycle;
- versioned claim/evidence revisions with deterministic legacy migration and
  Git observation metadata;
- labeled evaluation corpus and deterministic revalidation trade-off baseline
  across every supported grammar;
- structural indexing for all seven v1 languages;
- deterministic retrieval with exact-ref priority and context budgets;
- Dream reconciliation, project configuration, and HTML reporting;
- dirty-worktree handling, multi-file captures, failure behavior, and installed
  plugin validation.

Storage formats, configuration, and plugin interfaces may still change before a
stable release.

## Current limitations

- There is no published marketplace release or one-command public installation.
- Codex provides the semantic judgment about whether prose is durable; the local
  engine checks recorded evidence but cannot prove claim truth, semantic value,
  or provenance completeness.
- Retrieval is lexical and structural. A query with no shared language or refs
  may miss a conceptually related memory.
- Exact deduplication does not merge semantically equivalent wording; it only
  recognizes an identical claim scope and evidence fingerprint.
- Stale memory is excluded rather than automatically repaired during ordinary
  turns. Dream provides explicit reconciliation.
- Overloads, anonymous functions, generated code, macros, and partial classes
  may not resolve with the desired granularity.
- Hook trust, `uv` availability, dependency bootstrap, and local Git state are
  operational prerequisites.
- Best-effort non-blocking behavior can miss a memory update when a hook fails.

## Roadmap

### Before a public release

- Publish a versioned Codex marketplace package and documented upgrade path.
- Add release packaging and installed-plugin smoke tests to CI.
- Improve first-run bootstrap diagnostics and MCP capture observability.
- Add task-level diagnostics for missed or rejected captures.

### Later

- Add grammar packs for more languages without weakening the no-fallback rule.
- Improve symbol resolution for overloads, anonymous functions, generated code,
  macros, and partial classes.
- Expand Dream with dry runs, review modes, and targeted scopes.
- Add ranking evaluation datasets and retrieval quality metrics.
- Add memory diffs beyond the existing claim-level revision history.
- Evaluate an optional semantic retrieval layer only after deterministic ranking
  has measurable quality baselines.

## Development

Use `uv` for every Python operation:

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Repository behavior is specified in numbered files under `specs/`. See
`AGENTS.md` for the spec-first, branch, TDD, and commit-authorization workflow.

## License

MIT

# Memory Stale

**Persistent project memory that stops being trusted when its code evidence changes.**

Memory Stale gives Codex durable, code-anchored context across tasks. It stores
claims as reviewable Markdown, connects each claim to specific code evidence,
and deterministically marks the claim `stale` when that evidence no longer
matches.

It is installed per repository as a local Codex skill with hooks and a local
MCP server. It does not use Codex Plugins, global installation, another model,
embeddings, a hosted service, or a vector database.

## Why it matters

Codex can remember that `AuthService.login` only checks a password. If MFA is
added later, that fact is now unsafe. Memory Stale keeps the claim only while
the recorded code still supports it.

```text
unchanged evidence → active memory → available to Codex
changed evidence   → stale memory  → excluded until revalidated
```

`active` means the recorded evidence is unchanged; it is not proof that a claim
is complete or universally true. `stale` means evidence changed, disappeared,
or no longer resolves; it is not proof the claim is false.

## Install in a project

From the target Git repository, ask Codex:

> Install Memory Stale in this project from https://github.com/fagnermourafeitosa/memory-stale

Or run:

```bash
git clone https://github.com/fagnermourafeitosa/memory-stale.git /tmp/memory-stale
sh /tmp/memory-stale/scripts/install-project.sh .
```

The installer adds only target-project artifacts:

```text
.agents/skills/memory-stale/  # skill, hooks, Python runtime, lockfile
.codex/hooks.json             # lifecycle registrations
.mcp.json                     # local memory-stale MCP server
.git/memory-stale/runtime/    # local uv and grammar caches
```

It preserves unrelated hook and MCP entries, rejects an incompatible existing
`memory-stale` MCP server, and never changes `~/.codex`. Review the resulting
hooks, then start a new Codex conversation to load the local configuration.

Requirements: Git, `uv`, Python 3.10+, and Codex support for project-local
skills, hooks, and MCP configuration.

## How memory is discovered and classified

On every task, the `UserPromptSubmit` hook considers only records whose evidence
is still valid. It retrieves relevant active claims deterministically: exact
paths/symbols receive priority and remaining matches use lexical BM25 ranking.

```mermaid
flowchart TD
    A[Codex starts a task] --> B[UserPromptSubmit hook]
    B --> C[Load project memories]
    C --> D{"All recorded evidence<br/>still resolves and matches?"}
    D -->|Yes| E[Classify as active]
    D -->|No| F["Classify as stale<br/>and retain for audit"]
    E --> G{"Relevant to this task?<br/>Exact code ref or lexical match"}
    G -->|Yes| H["Inject active memory<br/>into Codex context"]
    G -->|No| I[Keep stored; do not inject]
    F --> J[Exclude from ordinary context]
```

This means a comment-only or formatting-only edit does not invalidate a memory,
while a semantic change to its referenced source does.

## How a memory is created

The local runtime captures supported code changes automatically. It never asks
another LLM: it fingerprints the parsed source at the start and end of a turn,
then records a code-anchored change record only when its semantic structure
differs.

```mermaid
flowchart TD
    A[UserPromptSubmit snapshots supported source] --> B[Codex changes code]
    B --> C["Stop hook fingerprints<br/>the final source"]
    C --> D{"Semantic source<br/>signature changed?"}
    D -->|No| E[No automatic memory]
    D -->|Yes| F[Stage automatic source-change record]
    F --> G[Reconcile final evidence]
    G --> H[Write active Markdown memory]
    I["Optional: Codex calls memory.capture<br/>for a richer claim"] --> G
```

An automatic record is intentionally factual:

```text
Automatic change record: src/auth.py changed in this task.
Evidence: src/auth.py
```

Codex can still call `memory.capture` to add a richer, code-backed claim such
as “Login validates password and MFA before creating a session.”

## Daily use

Memory maintenance is automatic:

1. `UserPromptSubmit` retrieves relevant active memory.
2. `PostToolUse` records work performed during the task.
3. `Stop` automatically captures semantic changes to supported code files,
   persists them, and marks affected existing records stale.
4. Codex may call `memory.capture` to attach a richer, explicit claim.

Ask Codex to work normally; no memory command or tool call is required for code
changes. For explicit maintenance, use:

```text
/memory-stale dream
```

Ask Codex for the Memory Stale health report to generate the local HTML view of
active/stale memories, evidence, and invalidation reasons.

## What is stored

Durable records and configuration live in the target project:

```text
.agents/skills/.agent-memory/memories/*.md
.agents/skills/.agent-memory/config.toml
```

Memory files are Git-reviewable Markdown. Commit them when the team wants to
share project knowledge. Turn ledgers and runtime caches remain under `.git/`.

Automatic primary evidence is a parsed source file and supports Python,
JavaScript/TypeScript, Go, Java, Kotlin, and Rust. Explicit MCP captures may
also use symbols, tests, configuration nodes, and schema nodes. Unsupported
languages intentionally have no fallback.

## Design boundaries

- **Codex supplies meaning.** It decides whether a fact is durable and states
  the claim.
- **The local core supplies proof of freshness.** It resolves declared evidence,
  fingerprints it, retrieves active records, and manages lifecycle state.
- **Hooks and MCP are adapters.** They keep the deterministic Python core
  independent from Codex transport and configuration.
- **Failures do not block coding.** Hook failures return actionable, non-blocking
  messages; writes are atomic.

## Current limitations

- Retrieval is lexical and structural; a prompt with no shared terms or code
  references may not retrieve a conceptually related memory.
- Stale records are excluded, not automatically rewritten. Revalidate them with
  Dream or a new capture.
- Overloads, anonymous functions, generated code, macros, and partial classes
  may not resolve at the desired granularity.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/logo-dark.png">
    <img src="./assets/logo-light.png" alt="Memory Stale logo" width="240">
  </picture>
</p>

**Deterministic, evidence-bound project memory for coding agents.**  
*When the code moves, outdated memory dies. Automatically.*

[![Local First](https://img.shields.io/badge/Local--first-100%25-blue.svg)](#design-boundaries)
[![AST Verification](https://img.shields.io/badge/Verification-Tree--sitter%20AST-green.svg)](#how-it-works-in-practice)
[![No Vector DB](https://img.shields.io/badge/Embeddings%20%2F%20Vector%20DB-None-orange.svg)](#why-deterministic-over-vector-dbs)
[![Format](https://img.shields.io/badge/Storage-OKF%20v0.2%20Markdown-purple.svg)](#what-is-stored)
[![Tested](https://img.shields.io/badge/Evaluation-100--trial%20Corpus%20(86.0%25)-brightgreen.svg)](#measured-evaluation)

Memory Stale gives **Codex**, **Claude Code**, and **Antigravity** persistent project memory anchored directly to the code AST. The moment referenced code or its static dependencies change, the claim is automatically invalidated and excluded from your agent's context.

No embeddings. No extra LLM calls. No cloud dependencies. Just deterministic AST fingerprinting and local Git hooks.

---

## The Problem: Stale Memory Rot

AI coding agents remember facts across tasks, but code changes constantly. Without continuous code-level verification, persistent memory quickly turns into **authoritative hallucinations**:

```text
Task 1  Agent records: "AuthService.login validates only password."
        Evidence: src/auth.py:AuthService.login

Task 2  You add Multi-Factor Authentication (MFA) to AuthService.login.

Task 3  Agent works on authentication again.
        ❌ Plain Memory / Vector DB: Injects the password-only claim as current truth.
        ✅ Memory Stale: Detects AST change in src/auth.py, marks memory STALE, and excludes it.
```

<p align="center">
  <img src="./assets/stale-memory-rot.png" alt="Stale Memory Rot vs AST Verification" width="800">
</p>

---

## Why Deterministic over Vector DBs?

Traditional agent memory uses vector databases or raw text files. Here is why that fails in real-world codebases:

| Feature | Vector DBs & LLM Memory | Plain Files (AGENTS.md / napkin) | Memory Stale |
| :--- | :--- | :--- | :--- |
| **Freshness Check** | ❌ None (Semantic similarity only) | ❌ Manual editing required | ✅ **Deterministic AST fingerprint comparison** |
| **Code Dependency Graph** | ❌ Blind to function call changes | ❌ None | ✅ **Static provenance graph (up to 3 hops)** |
| **Formatting / Comment edits** | ⚠️ Often alters embedding distance | ⚠️ Unversioned | ✅ **Immune (AST-level normalization)** |
| **Cost & Latency** | 💸 Extra LLM calls & embedding API | ⚡ Fast but brittle | ⚡ **100% Local, zero API calls, <10ms lookup** |
| **Audit Trail** | 🔒 Black-box vector space | 📝 Plain text | 📝 **Git-reviewable OKF v0.2 Markdown** |

---

## 60-Second Quickstart

Clone Memory Stale directly into your project's `.agents/skills/` directory and configure your harness:

```bash
# 1. Clone into your project's skills directory
git clone https://github.com/fagnermourafeitosa/memory-stale.git .agents/skills/memory-stale

# 2. Configure hooks and MCP for your harness:

# For Antigravity (workspace hooks + plugin MCP)
sh .agents/skills/memory-stale/scripts/install-project.sh . --harness antigravity

# For Claude Code (project hooks + project .mcp.json)
sh .agents/skills/memory-stale/scripts/install-project.sh . --harness claude

# For Codex (project hooks + project .mcp.json)
sh .agents/skills/memory-stale/scripts/install-project.sh . --harness codex
```

> **Requirements**: Git, `uv`, and Python 3.10+.  
> Restart or open a new agent session after installation to load hooks and the local MCP server.

---

## How It Works in Practice

Memory Stale runs transparently inside your agent's normal execution loop using lifecycle hooks:

<p align="center">
  <img src="./assets/lifecycle-flow.png" alt="Memory Stale Lifecycle and AST Verification" width="800">
</p>

### 1. Transparent Capture
When your agent completes a coherent code change, it calls `memory.capture` via MCP:

```json
{
  "claim": "Failed jobs retry up to 3 times before surfacing error.",
  "durability_reason": "Background queue contract required by worker services.",
  "evidence": ["src/jobs.py:retry", "tests/test_jobs.py:test_retry_limit"],
  "retrieval_terms": ["retry limit", "background job retries"]
}
```

### 2. Static Provenance Graph Expansion
For symbol evidence, Memory Stale doesn't just watch one line — it builds a local static dependency graph up to 3 hops (direct calls and named reads):

```text
claim
  → supported_by src/jobs.py:retry
      → calls src/policy.py:max_retries
      → reads src/config.py:RETRY_LIMIT
```
If `src/policy.py:max_retries` changes tomorrow, the claim is automatically invalidated.

<p align="center">
  <img src="./assets/static-provenance-graph.png" alt="Static Provenance Graph (Up to 3 Hops)" width="800">
</p>

### 3. Multilingual BM25S Retrieval
Active memories are ranked using field-weighted `bm25s` with Snowball stemming across natural language fields (`claim: 1.0`, `durability_reason: 0.5`, `retrieval_terms: 0.75`, `exact_locators: 2.0`). Exact symbols receive a `100.0` boost.

### 4. Reactive Coeffects & In-Memory Reverse Dependency Index
Memory Stale models evidence as **active reactive coeffects** rather than passive metadata (formalized in *Spatiotemporal Composability* — [Cordis Paper](https://github.com/cordiverse/paper/blob/main/paper.pdf)). Code entities act as *providers* and memories as *consumers* declaring environmental dependencies (`depends_on`).

Instead of naively scanning the entire memory corpus against all files ($O(N \times M)$), an in-memory `ReverseDependencyIndex` maps canonical symbol locators directly to dependent memory IDs. When Git changes occur, affected memories are resolved in $O(\Delta\text{symbols})$ time, maintaining near-zero hook latency without disk-based index files.

<p align="center">
  <img src="./assets/reactive-coeffects-reverse-index.png" alt="Spatial Composability and Reverse Dependency Index" width="800">
</p>

### 5. HMR Staleness Propagation & Granular Lifecycle
Inspired by Hot Module Replacement (HMR) dependency graphs, Memory Stale tracks transitive downstream shifts. When a callee function (`jwt.py:verify_token`) changes, any active memory whose dependency closure intersects the modified set ($\text{Closure}(C(M)) \cap \Delta \neq \emptyset$) is automatically transitioned to `STALE`, citing the exact downstream propagation path (e.g., `changed via auth.py:login`).

The `EvidenceTarget` model decouples logical symbol identity from AST fingerprints to establish deterministic lifecycle states:
* `STALE`: Symbol identity exists in the AST, but the semantic fingerprint diverged.
* `UNBOUND`: Symbol locator missing from the source file (renamed or deleted).
* `ORPHAN`: Target source file deleted from the Git repository.

<p align="center">
  <img src="./assets/hmr-staleness-propagation.png" alt="HMR Staleness Propagation and Target Reconciliation" width="800">
</p>

---

## What is Stored (Zero Lock-in)

All memories and configurations live directly inside your project in Git-reviewable Markdown:

```text
.agents/skills/.agent-memory/
├── config.toml           # Budget, top_k, and auto-report settings
└── memories/
    └── 2026-08-18-auth-password-contract.md
```

### Stored Format: Open Knowledge Format (OKF v0.2)
Every memory file is an immutable OKF document:

```markdown
---
type: Memory Stale Claim
title: Auth password validation contract
status: stable
memory_stale:
  schema_version: 1
  id: mem_9f82a1
  status: active
  fingerprints:
    "src/auth.py:AuthService.login": "sha256:d8a92f..."
---

AuthService.login validates password against Argon2 hash with rate-limiting.
```

---

## Daily Workflow & Maintenance

You don't need to learn new CLI commands. Work normally with your harness:

* **Context Injection**: Automatic on every prompt submit.
* **Audit Stale Records**: Run `/memory-stale dream` in chat to review stale claims.
* **Visual Health Report**: Ask your agent for the "Memory Stale health report" to generate a standalone `memory-report.html` showing active vs. stale evidence.

---

## Supported Languages (Tree-sitter AST)

Automatic symbol extraction, structural normalization, and static call graph expansion are natively supported for:

* **Python**
* **TypeScript & JavaScript**
* **Go**
* **Rust**
* **Java & Kotlin**

*Unsupported languages intentionally have no speculative fallback — evidence remains file-level to prevent false confidence.*

---

## Measured Evaluation & Benchmark

Memory Stale is continuously benchmarked against a versioned, human-labeled corpus of **100 end-to-end repository lifecycle cases** (50 semantic changes, 50 behavior-preserving edits):

| Metric | Result | 95% Confidence Interval |
| :--- | :---: | :---: |
| **Overall Accuracy** | **86.0%** (86/100) | 77.9% – 91.5% |
| **Stale Precision** | **84.6%** (44/52) | 72.5% – 92.0% |
| **Stale Recall** | **88.0%** (44/50) | 76.2% – 94.4% |
| **Mean Reciprocal Rank (MRR)** | **0.450** | Position-aware ranking quality |
| **NDCG@5 Ranking Quality** | **0.540** | High-relevance context promotion |
| **Operational Failures** | **0 / 100** | 100% deterministic test stability |

### Reproduce Benchmark Locally
Run the 100-case evaluation suite anytime:

```bash
uv run pytest -m repository_evaluation
```

---

## Current Boundaries & Limitations

* **Lexical & Structural**: Memories are retrieved by exact code references, BM25S terms, and declared aliases. Pure conceptual queries with no vocabulary overlap are not retrieved.
* **Static Graph Bounds**: Provenance follows direct named declarations up to 3 hops (64 nodes max). Dynamic reflection, monkey patching, and external runtime configuration are omitted rather than guessed.
* **Exclusion over Mutation**: Stale memories are excluded from prompt injection, never silently rewritten without verification.

---

## License

[MIT](LICENSE.txt)

# 44 — Reactive coeffects, HMR staleness propagation, and target reconciliation

**Status: Done (2026-08-18)**

## Problem Statement

Memory Stale currently models evidence as stored provenance metadata attached to
each memory. While AST normalization and static provenance graph expansion
([spec 38](file:///Users/seufagner/Documents/ChatGPT/memory-stale/specs/38-automatic-static-provenance-graph.md))
track direct calls and reads, the lifecycle engine still evaluates validity via
iterative verification across the memory corpus. Furthermore, if an entity's
underlying implementation changes, memory validity is checked node-by-node
without a unified formal model of **reactive dependency tracking**.

As formalized in the research on *Spatiotemporal Composability*
([Cordis Paper](https://github.com/cordiverse/paper/blob/main/paper.pdf),
[Cordis Framework](https://github.com/cordiverse/cordis)), dynamic systems
require two complementary dimensions:
1. **Spatial Composability (Reactive Coeffects)**: Managing what a component
   requires from its environment. In Memory Stale, **code entities are
   providers** and **memories are consumers** declaring coeffects (`depends_on`).
2. **Hot Module Replacement (HMR) Staleness Model**: An entry becomes stale
   when its dependency closure intersects modified modules/symbols.

Memory Stale needs to elevate evidence from passive recorded metadata to
**active reactive coeffects**, maintain an in-memory **reverse dependency index**
for $O(\Delta\text{symbols})$ hook evaluation, formalize **`EvidenceTarget`**
(decoupling symbol identity from AST fingerprint), and enforce **inertial target
reconciliation** to guarantee that revalidated claims are verified against the
exact repository state at the moment of capture.

## Solution

1. **Reactive Coeffects & In-Memory Reverse Index**:
   - Each memory's evidence set constitutes its declared reactive coeffects.
   - The memory store maintains a deterministic, rebuildable in-memory
     `ReverseDependencyIndex` mapping canonical symbol locators to dependent
     memory IDs (`SymbolLocator -> Set[MemoryId]`).
   - On Git diff or symbol modification, the engine resolves affected memories
     in $O(\Delta\text{symbols})$ rather than scanning the entire memory corpus.

2. **HMR-Inspired Staleness via Bounded Graph Intersection**:
   - When a Git change occurs, the set of modified symbols $\Delta$ is computed.
   - The dependency closure of each active memory is evaluated against $\Delta$.
   - If the dependency closure of a memory intersects $\Delta$, the memory is
     transitioned to candidate `stale`.
   - Transitive propagation is bounded to direct AST-parsed invocations and
     module-local references ($depth \le 1$) to prevent over-invalidation from
     global or utility changes.

3. **`EvidenceTarget` Specification (Identity vs. Semantic Fingerprint)**:
   - Each evidence reference is structured as an `EvidenceTarget`:
     - `identity`: Canonical locator (`path/to/file.py::SymbolName`).
     - `fingerprint`: Normalized Tree-Sitter AST hash (`sha256:...`).
   - Distinguishes lifecycle outcomes deterministically:
     - `STALE`: `identity` exists, but `fingerprint` diverged (semantic change).
     - `UNBOUND`: `identity` missing from the target source file (symbol deleted or renamed).
     - `ORPHAN`: Target source file deleted from the repository.

4. **Inertial Target Reconciliation**:
   - Capture and revalidation operations record a `target_signature` representing
     the exact state of all supporting evidence at the start of evaluation.
   - When persisting a revalidation result, the engine checks that
     `current_target_signature == started_target_signature`.
   - If the underlying repository code changed during the turn, the outdated
     result is rejected, preventing race conditions and ensuring linearizable
     consistency.

## User Stories

1. As an agent, I want modified code symbols to instantly invalidate dependent
   memories via reverse index lookup, so that hook latency remains near-zero on
   large repositories.
2. As an agent, I want changes to a repository function called directly by my
   evidence symbol to invalidate my claim (HMR staleness), so that downstream
   behavioral shifts do not leave outdated memories active.
3. As a developer, I want a clear distinction between `STALE` (logic changed),
   `UNBOUND` (symbol renamed/deleted), and `ORPHAN` (file removed), so that I
   know whether to revalidate the claim or update the locator.
4. As a user, I want capture and revalidation to verify target consistency
   inertially at the moment of write, so that concurrent edits do not activate
   stale conclusions.
5. As a maintainer, I want the reverse index to be purely derived and in-memory,
   so that Git-native Markdown remains the sole durable source of truth without
   corruptible secondary index files.
6. As an auditor, I want staleness explanations in `memory-report.html` and
   Markdown frontmatter to cite the intersecting dependency path.

## Implementation Decisions

- **In-Memory Reverse Index**: Built dynamically when loading memories from
  `.agents/skills/.agent-memory/memories/*.md`. No secondary index files are
  committed or persisted on disk.
- **EvidenceTarget Data Model**:
  ```python
  @dataclass(frozen=True)
  class EvidenceTarget:
      identity: str  # canonical locator (e.g., "src/auth/jwt.py::verify_token")
      fingerprint: str  # "sha256:..."
      kind: str  # "symbol" | "source" | "test" | "config"
  ```
- **HMR Staleness Intersection**:
  - A memory $M$ with coeffects $C(M)$ is marked `stale` if:
    $$\text{Closure}_{k=1}(C(M)) \cap \Delta_{\text{modified}} \neq \emptyset$$
  - Closure expansion uses the conservative Tree-Sitter extraction rules from
    [spec 38](file:///Users/seufagner/Documents/ChatGPT/memory-stale/specs/38-automatic-static-provenance-graph.md).
- **Fiber Target State Transitions**:
  - Valid states: `ACTIVE`, `REVALIDATING`, `STALE`, `UNBOUND`, `ORPHAN`, `ARCHIVED`.
  - Revalidation must supply the expected `EvidenceTarget` states.
- **Boundaries**:
  - No asynchronous background daemons or Node.js runtime bindings. The engine
    remains 100% synchronous, pure Python, and CLI/hook/MCP-driven.
  - No rollback of mutative effects (`ctx.effect` inverse operations are out of
    scope, as freshness is exclusion, not rollback).

## Testing Decisions

- **Highest Observable Seam**: A real MCP capture persists a memory declaring
  an evidence target. A subsequent code change modifies a downstream called
  symbol. The hook runs, performs reverse index lookup and HMR closure
  intersection, marks the memory `stale` with an explicit dependency path,
  and confirms context retrieval immediately excludes the claim.
- **TDD Slice 1**: `EvidenceTarget` parsing and `ReverseDependencyIndex`
  construction from a memory corpus, verifying $O(1)$ affected lookup per symbol.
- **TDD Slice 2**: HMR staleness detection via graph intersection for direct
  and $depth=1$ called dependencies.
- **TDD Slice 3**: Differentiated lifecycle states (`STALE` vs `UNBOUND` vs `ORPHAN`).
- **TDD Slice 4**: Inertial target reconciliation during `memory.capture` and
  `memory.reconcile` (rejecting stale target tokens).
- **TDD Slice 5**: End-to-end integration via MCP and lifecycle hooks with real
  Git diffs and temporary repositories.

## Out of Scope

- Importing the Cordis TypeScript library or creating a Python port of Cordis runtime.
- Revertible side-effect handlers (`ctx.effect` LIFO rollback).
- Global unbounded call-graph traversal ($depth > 1$).
- Secondary SQLite or persistent binary index caches.
- Asynchronous multi-threaded fiber scheduling.

## Further Notes

- Conceptual foundations:
  - *Spatiotemporal Composability* (Cordis Paper: https://github.com/cordiverse/paper/blob/main/paper.pdf)
  - *Coeffects: Unified Static Analysis of Context-Dependence* (Petricek, Orchard, Mycroft, 2013)
  - *Hot Module Replacement & Graph Intersection* (Cordis & Vite ESM Graph Models)
- Documentation and public `README.md` updates will reflect these concepts under
  the "Reactive Knowledge Dependency Engine" section once implemented.

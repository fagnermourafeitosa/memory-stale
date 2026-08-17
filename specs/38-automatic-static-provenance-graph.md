# 38 — Automatic bounded static provenance graph

**Status: Done (2026-08-17)**

## Problem Statement

Memory Stale can already persist explicit `supported_by` and `depends_on`
relationships, traverse them deterministically, and invalidate a claim revision
when reachable evidence changes. However, the Codex instance capturing a claim
must currently declare every dependency. A claim whose primary evidence is a
function or method can therefore remain active after a repository-local
function, method, or named declaration consumed by that primary symbol changes,
even when the dependency is directly and unambiguously visible in the parsed
source.

Real code behavior is usually distributed across calls and referenced values.
Tracking only the supplied `path:symbol` locator makes the validity boundary
narrower than the code boundary that supports the claim. Requiring a complete
manually declared graph also makes provenance quality depend on discretionary
capture detail.

Memory Stale needs to expand code evidence into a small, deterministic static
provenance closure. The closure must improve real repository tracking without
claiming to be a complete call graph, inventing ambiguous relationships, using
another LLM, or broadening one precise reference into a whole-file dependency.

## Solution

When capturing a revision with resolvable `symbol` or `test` evidence, Memory
Stale will use the existing supported tree-sitter grammars to discover a
conservative set of repository-local dependencies. It will persist only
dependencies whose target has one unambiguous declaration and whose relationship
is directly established by supported syntax.

The first version will add two automatic relationship types:

- `calls`: the source evidence directly calls a uniquely resolved function or
  method declaration.
- `reads`: the source evidence directly references a uniquely resolved named
  declaration outside its local scope.

Imports participate in name and module resolution but do not themselves create
an edge to an entire module. Automatic expansion follows newly resolved code
evidence until it reaches the configured hard bounds or no further safe
dependency can be resolved. Explicit `depends_on` edges remain supported and
are combined with automatic edges. Every evidence node in the effective closure
is fingerprinted using its evidence adapter and persisted in the immutable
claim revision.

Later reconciliation uses the persisted closure exactly like an explicitly
declared evidence graph. A changed, removed, or unresolvable reachable node
makes the revision stale and records the complete typed provenance path from the
claim's supporting root to the affected node.

References that are dynamic, ambiguous, external, unsupported, or not safely
resolvable are omitted. Omission never becomes a guessed edge or a file-level
fallback. The product describes the result as a bounded static provenance graph,
not as complete dependency analysis or proof that a claim remains true.

## User Stories

1. As a user, I want a change to a directly called repository function to
   invalidate a memory about its unchanged caller, so that transitive behavior
   changes do not remain silently active.
2. As a user, I want a change to a repository-local named value read by a
   function to invalidate a memory about that unchanged function, so that
   behavior controlled outside the function body remains tracked.
3. As a user, I want dependencies to expand transitively within a small bound,
   so that a safely resolved dependency of a dependency participates in
   revalidation.
4. As a user, I want an import to resolve the exact referenced declaration
   rather than make the memory depend on an entire module, so that unrelated
   module edits do not cause revalidation.
5. As a user, I want unresolved or ambiguous references omitted rather than
   guessed, so that the graph contains only defensible relationships.
6. As a user, I want explicit evidence dependencies to continue working, so
   that I can represent domain relationships and dynamic behavior unavailable
   to static syntax.
7. As a user, I want explicit and automatic dependencies to coexist in one
   closure, so that automatic coverage does not discard richer declared
   provenance.
8. As an auditor, I want to distinguish automatic `calls` and `reads` edges
   from explicit `depends_on` edges, so that every stale decision is
   explainable.
9. As an auditor, I want the stale reason to include the ordered relationship
   path to the changed dependency, so that I can see why the claim requires
   revalidation.
10. As a maintainer, I want graph construction to use canonical ordering and
    cycle-safe traversal, so that the same repository state produces the same
    persisted revision.
11. As a maintainer, I want graph depth and node count bounded, so that hooks
    stay predictable on highly connected code.
12. As a maintainer, I want a bound reached during expansion reported as an
    incomplete closure rather than hidden as completeness, so that operational
    limits remain auditable.
13. As a maintainer, I want automatic dependency extraction versioned, so that
    an extractor upgrade does not silently reinterpret an existing revision.
14. As an existing user, I want previously stored explicit graphs to retain
    their current lifecycle behavior, so that installing the new runtime does
    not invalidate or rewrite history.
15. As a developer in any currently supported grammar, I want the same safety
    rule—unique static resolution or no edge—even when the exact supported
    syntax differs by language.
16. As a developer using dynamic dispatch, reflection, dependency injection,
    wildcard imports, or runtime configuration, I want Memory Stale to leave
    those relationships explicit, so that it does not pretend tree-sitter has
    compiler or runtime knowledge.
17. As a user, I want Dream and task-end reconciliation to reach the same final
    lifecycle state from the same persisted graph, so that audit timing does
    not change correctness.
18. As a user, I want automatic provenance to remain local and deterministic,
    so that capture never calls another model, compiler, language server, or
    remote indexing service.
19. As a user, I want unsupported languages and unsupported dependency forms
    rejected or omitted without raw-file fallback, so that the product boundary
    remains precise.
20. As a maintainer, I want repository evaluation reserved for a separately
    requested statistical measurement, so that ordinary implementation
    validation stays focused on behavioral tests rather than benchmark samples.

## Implementation Decisions

- The existing evidence graph remains the lifecycle source of truth. Automatic
  extraction enriches the persisted graph before revision identity and
  fingerprints are finalized; it does not introduce a second invalidation
  mechanism.
- Automatic expansion applies to exact `symbol` and `test` evidence. `source`,
  `config`, and `schema` evidence remain leaf nodes in this spec.
- Expansion starts from the revision's `supported_by` code-evidence roots and
  from code-evidence nodes reached through explicit edges. Newly discovered
  code nodes are traversed transitively within the same bounds.
- Every persisted edge records a relationship and origin. Existing declared
  edges are interpreted as relationship `depends_on` with origin `declared`.
  New edges use relationship `calls` or `reads` with origin `static`.
- Existing stored graph revisions remain readable without migration. Missing
  relationship and origin fields use the declared-edge compatibility values.
  Existing revisions are never automatically re-expanded or rewritten.
- The extractor version and expansion completeness are persisted with each new
  revision. Completeness distinguishes a fully exhausted safe closure from one
  stopped by a depth or node bound. It does not claim that dynamic or
  unsupported dependencies were discovered.
- The implementation will define small hard defaults for maximum traversal
  depth and maximum discovered nodes. The limits are deterministic product
  constants in this spec; they are not user-facing configuration in the first
  version. Reaching a limit preserves the safely discovered prefix and exposes
  a non-blocking diagnostic.
- Tree-sitter nodes and grammar fields are the only source for recognizing
  calls, identifiers, declarations, scopes, imports, aliases, and qualified
  accesses. Regular expressions over source text will not establish graph
  edges.
- A target is resolvable only when lexical scope, explicit repository-local
  import information, and the repository symbol index identify exactly one
  compatible declaration. Zero or multiple candidates produce no automatic
  edge.
- Direct calls may resolve to a unique function in the same source scope, a
  unique method declared on the syntactically explicit current receiver type,
  or a unique function/method reached through an explicit repository-local
  import. Inherited dispatch, interface dispatch, overloaded ambiguity,
  callbacks, first-class function values, and computed callees are excluded.
- Reads may resolve to a unique module-, file-, type-, or class-level named
  declaration outside the current local scope. Parameters, local variables,
  fields on values of unknown type, computed properties, and names with
  ambiguous shadowing do not create edges.
- The symbol index will gain exact fingerprints and locators for the named
  declarations admitted by `reads`. Declaration support is grammar-specific
  but follows one public rule: a declaration is indexable only when its name,
  enclosing scope, and syntax extent are unambiguous.
- Explicit import aliases may participate when both the imported module and
  declaration resolve uniquely inside the repository. Wildcard imports,
  package re-exports, external packages, generated module lookup, and ambiguous
  repository layouts do not create edges.
- In the first version, same-source direct calls and named reads are supported
  for all seven existing grammars. Cross-source resolution is limited to Python
  named imports and JavaScript/TypeScript relative named imports whose literal
  module path maps to exactly one supported repository source file. Go, Java,
  Kotlin, and Rust imports require module, source-root, build, or package
  semantics beyond tree-sitter and therefore remain unexpanded in this spec.
- Import statements are resolution evidence, not graph targets. Importing a
  module never makes every declaration or the complete source file part of the
  closure.
- Automatic nodes use supporting evidence and their exact symbol fingerprint.
  They do not alter the primary evidence scope used for claim identity.
- Duplicate nodes and edges from declared and static discovery are canonicalized.
  A declared edge is retained as declared when the same endpoints are also
  statically discoverable, because the explicit provenance is the stronger
  historical statement.
- Traversal is deterministic, breadth-first, canonically ordered, bounded, and
  cycle-safe. The persisted graph and revision identifier do not depend on
  filesystem enumeration order.
- Reconciliation compares the persisted fingerprints of every reachable node.
  It does not recompute the historical graph with a newer extractor version.
- A graph topology change inside primary evidence changes that evidence's own
  structural fingerprint and follows the existing revision lifecycle. A later
  revision captured from the new code receives a newly expanded graph.
- Stale reasons include evidence identity plus relationship labels for the
  deterministic shortest path. Existing declared paths remain readable and
  acquire the compatibility relationship label when rendered.
- Task-end reconciliation may use changed paths to avoid resolving unrelated
  evidence. Dream remains the broad correctness audit. Optimization must not
  change the final lifecycle state.
- Derived adjacency or reverse indexes may be introduced for lookup efficiency,
  but they are rebuildable and never become the Git-native source of truth.
- The report shows automatic versus declared edges, extractor version,
  incomplete-expansion diagnostics, and the exact stale path. Markdown remains
  the storage and audit surface; no graph editor or human-facing CLI is added.
- All seven currently supported grammars retain explicit fixtures for every
  dependency form claimed as supported. A grammar does not fall back to text,
  whole-file evidence, or guessed resolution when a form is unsupported.

## Testing Decisions

- **Confirmed highest observable seam:** a real MCP
  capture records a claim with only one primary caller symbol; after the called
  repository symbol changes in a later real hook cycle, task-end reconciliation
  persists the revision as stale, ordinary retrieval excludes it, and the
  Markdown/report reason contains the complete automatic `calls` path.
- The first TDD slice will use that seam for a single unambiguous same-module
  call. Before production code is written, the behavioral test must fail because
  the dependency is absent and the unchanged caller leaves the memory active.
- The second vertical slice covers an explicitly imported, uniquely resolved
  repository call without making an unrelated change in the imported module
  stale.
- The third vertical slice covers a uniquely resolved named declaration read
  by the primary symbol and observes invalidation when only that declaration
  changes.
- Subsequent behavioral slices cover transitive expansion, explicit plus
  automatic edges, deterministic cycles, a removed dependency, a depth bound,
  a node bound, and compatibility with a previously stored declared graph.
- Negative behavioral tests cover ambiguous same-name declarations, wildcard
  imports, dynamic dispatch, callbacks, unknown receiver types, external
  imports, package re-exports, local-variable reads, and unsupported syntax.
  Each must prove that no automatic edge is persisted.
- Every supported grammar has real source fixtures for its admitted direct-call
  and named-read forms, plus ambiguity fixtures. Tests use the public index or
  lifecycle seam and never mock project-owned parsers or resolvers.
- Integration tests use temporary Git repositories, real files, real hook
  commands, the real MCP process, persisted Markdown, and ordinary retrieval.
- Dream and targeted task-end reconciliation are tested to produce identical
  final memory state for the same stored graph.
- Expected locators, fingerprints where externally exposed, edge metadata,
  paths, statuses, and diagnostics are independent literals. Tests do not
  rebuild expected graphs with the production extraction algorithm.
- Existing explicit dependency-graph, lifecycle, retrieval, report, automatic
  capture, and symbol-index behavior remains covered by their current public
  tests.
- Do not run or update the repository evaluation as ordinary implementation
  validation. It is a separate intentional statistical measurement and runs
  only when explicitly requested for that purpose; the feature's behavioral
  tests provide the implementation feedback loop.
- After the implementation is stable, an explicitly requested final measurement
  may run the repository evaluation once. Preserve the pre-graph baseline, write
  the post-graph result as a separate dated artifact, update the exact evaluator
  assertions to that artifact, and document the before/after comparison without
  presenting the curated corpus as a real-world accuracy estimate.
- Before completion, run the repository's required formatting, lint, strict
  typing, and default behavioral tests. The repository evaluation remains
  excluded.

## Out of Scope

- A complete call graph, control-flow graph, data-flow graph, type checker, or
  whole-program semantic model.
- Guessing a target when more than one declaration is compatible.
- Runtime dispatch, reflection, monkey patching, metaprogramming, dynamic
  imports, dependency-injection container resolution, callbacks, event buses,
  registries, or string-selected functions.
- Inheritance, interface, trait, protocol, or overload resolution unless a
  future spec establishes a separately testable unique-resolution contract.
- Framework semantics such as interpreting a decorator or annotation as
  `validated_by`, `authorized_by`, or another domain relationship.
- Automatic dependencies on JSON, YAML, TOML, schemas, environment variables,
  databases, services, or files opened at runtime.
- Treating an imported module or complete source file as evidence merely
  because an import exists.
- Language-server, compiler, build-system, package-manager, or remote index
  invocation.
- New grammars, unsupported-language fallback, raw-text analysis, embeddings,
  GraphRAG, another LLM, or semantic-neural inference.
- Stable symbol identity across moves or renames.
- Reverse-impact scheduling and graph-based retrieval ranking beyond any
  rebuildable adjacency needed to preserve current reconciliation behavior.
- Multi-layer fingerprints beyond the existing versioned exact fingerprint
  used for each discovered evidence node.
- A dedicated graph editing interface, visualization product, or human-facing
  CLI.

## Further Notes

- This spec extends the explicit graph contract rather than replacing it. The
  declared graph remains necessary for dependencies that syntax cannot prove.
- “Complete expansion” means only that every safely supported reference inside
  the configured bounds was exhausted. It never means complete behavioral
  provenance.
- The design criterion is repository usefulness with defensible edges. Corpus
  results are a regression and validation instrument, not the architectural
  objective.
- The user confirmed the highest observable test seam before implementation.

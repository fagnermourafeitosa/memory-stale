# 17 — Explicit evidence dependency graph

## Problem Statement

Flat evidence sets can record multiple sources but manually repeat every
dependency for each claim and do not explain why indirect evidence supports it.
A claim tied to `AuthService.login` may depend on a policy that itself depends on
configuration or another policy. Without explicit relationships, the product
cannot traverse that provenance or reuse declared dependencies. Building an
automatic call graph now, however, would require semantic resolution that
tree-sitter alone does not provide reliably across seven languages.

## Solution

Add an explicit, local evidence dependency graph. Claims have `supported_by`
relationships to evidence items, and evidence items may declare `depends_on`
relationships to other evidence items. The current Codex instance provides
relationships while capturing knowledge; the core only validates locators,
records fingerprints, and traverses the graph deterministically. A change to any
reachable evidence item requires revalidation of the dependent revision.

## User Stories

1. As a user, I want a registered transitive dependency change to make a revision stale even when the local symbol remains unchanged.
2. As an auditor, I want the provenance path that connects the claim to changed evidence, so that the revalidation reason is explainable.
3. As Codex, I want to declare that one policy depends on another policy or configuration, so that the relationship is reusable and not hidden in prose.
4. As a maintainer, I want deterministic, cycle-safe traversal, so that real graphs do not block hooks.
5. As a maintainer, I want every node validated before relationships are persisted, so that broken edges do not create artificial trust.
6. As a user, I want Dream to audit transitive dependencies, so that changes outside the current turn are also found.
7. As a user, I want the report to show invalidation paths, so that the graph has operational rather than merely structural value.
8. As a maintainer, I want to measure the graph's effect on the existing corpus, so that greater coverage does not hide uncontrolled revalidation growth.
9. As an evaluator, I want the project to remain deterministic provenance, so that the graph is not confused with GraphRAG or semantic retrieval.

## Implementation Decisions

- The graph has claim-revision and typed-evidence-item nodes with directed `supported_by` and `depends_on` edges.
- Edges are declared by the Codex instance that already performs semantic judgment during capture. The local engine does not infer meaning or call another model.
- Every persisted evidence node has a resolvable locator and a fingerprint supplied by its type adapter.
- A revision is `active` only when every evidence item reachable from its `supported_by` edges matches its recorded fingerprint.
- A changed, removed, or unresolvable reachable node makes the revision `stale` and records at least one deterministic path from the claim to the affected node.
- Traversal uses canonical ordering, a visited set, and finite behavior in the presence of cycles. Cycles do not make results depend on visit order.
- Capturing or updating relationships is atomic: missing nodes, incompatible types, and malformed edges reject the entire set.
- Shared dependencies may be referenced through canonical identity, but each evidence revision preserves the fingerprint snapshot that validated it.
- Hooks perform targeted audits of items touched during the turn and revisions reachable through reverse edges. Dream continues to provide broad audits.
- The report presents claims, revisions, nodes, edges, and staleness paths without becoming the primary editing surface.
- Storage remains Git-native Markdown. Derived indexes for reverse traversal may be rebuilt and are not a source of truth.
- The corpus from spec 15 compares the flat baseline and graph, including unnecessary revalidation and missed semantic changes.
- The feature is described as an evidence or provenance graph, never as a semantic knowledge graph or GraphRAG.

## Testing Decisions

- Highest seam confirmed: real MCP capture of a revision with a transitive dependency, a change only to the leaf node, execution of Stop or Dream, and observation of Markdown, context, and report.
- First behavioral slice: `login supported_by authentication policy depends_on MFA policy`; changing only the MFA policy must mark the login revision `stale` and record the complete path.
- The first test must fail with flat evidence sets that do not explicitly include the leaf node in the claim revision.
- Subsequent slices cover a dependency shared by multiple claims, cycles, a removed node, a broken locator, edge updates, and deterministic ordering.
- Tests use real files and Git repositories; only true external boundaries may be simulated.
- Targeted auditing and Dream must produce the same final state for the same graph.
- Tests observe public paths and states, not call order, internal adjacency representation, or private functions.
- The evaluation corpus records changes in both metrics before the graph is considered a completed improvement.

## Out of Scope

- Automatically discovering call graphs, imports, dynamic dispatch, or dataflow.
- Querying language servers, remote compilers, or indexing services.
- GraphRAG, embeddings, a vector database, or ranking through graph traversal.
- Treating the graph as proof of provenance completeness or claim truth.
- Editing the graph through a dedicated human interface.
- Adding file-level fallback or generic support for unknown formats.

## Further Notes

- This spec depends on revisioned claims, baseline metrics, and typed evidence sets from specs 14, 15, and 16.
- Implementation proceeds only if the corpus demonstrates additional benefit over flat evidence sets proportional to cost and revalidation rate.

# 37 — Declared retrieval terms

## Problem Statement

Memory Stale retrieves active claims through deterministic, field-weighted
lexical matching. Claim prose and structural evidence locators provide useful
terms, but a later task can use valid product vocabulary that neither field
spells exactly. For example, a claim about session invalidation may be stored
with evidence for a token-rotation function while a later task asks about MFA.
The deterministic engine cannot safely infer synonyms, entities, or semantic
equivalence without leaving the product boundary.

## Solution

Allow the Codex or Claude Code instance already performing a task to declare a
small optional set of retrieval terms when it captures a semantic claim. The
local engine validates, persists, and lexically ranks those terms but never
generates, expands, or interprets them. A term is only a supplementary retrieval
signal: it cannot by itself make a memory eligible for context. Retrieval terms
are not evidence and do not affect active/stale validation.

## User Stories

1. As a developer, I want to declare concise product vocabulary for a memory,
   so that later tasks can retrieve it without repeating its exact claim text.
2. As a Codex or Claude Code host, I want to supply retrieval terms in the same
   capture request as a semantic claim, so that semantic judgment stays with
   the instance already doing the work.
3. As a maintainer, I want the memory engine to treat terms as opaque lexical
   text, so that it does not infer entities, synonyms, or claim truth.
4. As a developer, I want an alias to reinforce a claim or locator match, so
   that domain phrasing improves ranking without becoming an uncorroborated
   assertion from the host.
5. As a developer, I want claim prose to remain more important than declared
   terms, so that labels cannot displace the remembered behavior.
6. As a developer, I want exact evidence locators to retain their existing
   dominant priority, so that precise code requests remain predictable.
7. As a maintainer, I want malformed, blank, repeated, or excessive terms to
   be rejected atomically, so that persisted retrieval vocabulary remains
   bounded and auditable.
8. As a user with existing memories, I want documents without retrieval terms
   to remain readable and retrievable exactly as before.
9. As an auditor, I want declared terms visible in Markdown, reports, and the
   capture contract, so that retrieval behavior is explainable.
10. As a user, I want terms never to make stale memory eligible for context,
    so that retrieval recall cannot weaken provenance validation.
11. As a maintainer, I want recapturing the same claim and evidence with
    changed terms to create a distinct immutable revision, so that the
    retrieval vocabulary observed at each evidence revision is preserved.
12. As a project owner, I want public documentation and examples to distinguish
    host-declared terms from automatic entity extraction, so that the product
    boundary remains clear.
13. As a developer, I want low-confidence lexical tails removed from context,
    so that adding retrieval vocabulary does not indiscriminately inject every
    weakly related active memory.
14. As an evaluator author, I want the score cutoffs fixed before reviewing
    held-out retrieval outcomes, so that the benchmark does not tune itself to
    pass its own samples.
15. As a project owner, I want retrieval to inject at most a configurable
    number of highest-ranked eligible memories, so that supplementary terms
    can improve selection without a large token budget admitting every
    candidate.
16. As a project owner who has no retrieval-count setting, I want a stable
    default of five memories, so that the context remains bounded without
    requiring configuration.

## Implementation Decisions

- Extend semantic capture with an optional `retrieval_terms` collection of at
  most eight non-empty strings, each at most 80 Unicode code points after
  trimming.
- Canonicalize terms for validation and identity by trimming and Unicode
  case-folding. Preserve one trimmed display spelling for persisted Markdown;
  canonical duplicates reject the complete capture rather than being silently
  discarded.
- Terms are opaque retrieval annotations. They are neither evidence items nor
  graph nodes, are not fingerprinted independently, and never participate in
  active/stale state calculation or semantic coverage.
- Persist the declared terms in the current immutable revision format. A
  document that omits the field represents an empty collection. The revision
  identity includes canonical terms, so a changed term collection produces a
  new revision even when the claim and evidence fingerprints are unchanged.
- Add a fourth independently normalized BM25 field for retrieval terms with a
  fixed weight of `0.75`. Existing claim, durability-reason, locator, and exact
  locator scores remain `1.0`, `0.5`, `2.0`, and `100.0` respectively.
- An exact evidence locator bypasses lexical eligibility cutoffs. Otherwise a
  candidate must have a combined lexical score of at least `0.25`, and must be
  within `50%` of the highest eligible score for that prompt. These fixed
  cutoffs are product policy, not user configuration or values learned at
  runtime.
- A matched retrieval term requires a separate positive claim or locator score
  for the same memory. Durability-reason text is not sufficient corroboration.
  A term-only score is discarded before ranking, even when the memory is
  active.
- Apply the relative threshold after exact locator boosts and deterministic
  sorting. A prompt with an exact locator may therefore intentionally suppress
  weaker lexical context in favor of the directly named code anchor.
- Add a `top_k` project configuration setting with a default of `5`. It must
  be a positive integer, cannot be a boolean, and is passed through the task
  start hook to the public retrieval operation.
- After active-state filtering, lexical eligibility gates, relative cutoff,
  and deterministic score/ID ordering, retain only the first `top_k`
  candidates. Apply the existing context-token budget only to that retained
  prefix. `top_k` is a selection limit, not a token budget and does not alter
  lexical scores, stale exclusion, or exact-locator priority.
- Retrieval terms are tokenized with the existing natural-language lexical
  contract. Field statistics and length normalization use only active memories
  and are calculated independently for the field.
- Return terms through existing public capture, store, report, and hook
  surfaces without adding a human-facing command or a separate entity store.
- Update the host instructions so Codex and Claude Code may declare a few
  durable domain names, abbreviations, or alternative task phrases. The host
  must not invent broad keyword lists or claim that the runtime extracts them.
- Extend the existing 100-trial repository evaluator instead of creating a
  separate retrieval corpus. The corpus remains exactly 100 cases and continues
  to produce its freshness confusion matrix.
- Mix retrieval behavior into the 100 cases: 20 cases declare retrieval terms,
  split between 10 semantically preserved targets that should be recovered and
  10 semantically changed targets that should be excluded; 10 additional
  preserved cases use unrelated prompts and should return no context; the
  remaining 70 cases retain ordinary claim or locator retrieval as controls.
- Select declared-term cases from existing domain-bearing policy, MFA,
  configuration, pricing, permissions, schema, observability, graph, and
  repository-shape scenarios. Do not relabel generic language fixtures with
  aliases authored only to guarantee a lexical hit.
- Do not require the observed lifecycle state to agree with the semantic label
  when selecting retrieval cases. Existing false-stale and missed-change cases
  must remain represented so the evaluation exposes both lost recall and unsafe
  availability instead of selecting only cases the implementation already wins.
- Add multiple active, source-backed distractor memories to every declared-term
  repository through the real capture boundary. Some distractors carry
  plausible overlapping vocabulary and others are unrelated, so the evaluation
  observes irrelevant returned context and term collisions rather than testing
  a single isolated memory.
- Add an independent retrieval expectation to each evaluated outcome. Freshness
  metrics use lifecycle state only; retrieval metrics compare actual context
  inclusion with the explicit retrieval expectation.
- For all 20 declared-term cases, run the same repository trial once more with
  `retrieval_terms` removed from the target and distractors. Hold source files,
  claims, prompts, lifecycle changes, and evaluation expectations constant.
- Label the 20 declared-term cases in advance as 10 calibration and 10 holdout
  cases, balanced across expected inclusion and exclusion. The fixed score
  policy is documented before the holdout measurement; report the two partitions
  separately instead of changing cutoffs after reviewing the holdout outcome.
- Report the 100-case retrieval accuracy both with terms and under that
  counterfactual substitution, plus the net change. Separately report declared-
  term target recall, no-context exclusion rate, and returned-context precision
  with and without terms so a recall gain cannot hide added false context.
- Define positive success as inclusion of the expected target claim. For
  declared-term and unrelated negative cases, define success as returning no
  memory context, not merely omitting the target while returning an irrelevant
  distractor. Existing locator controls continue to judge target availability
  because their current-source automatic captures can be valid context. Report retrieval recall,
  no-context exclusion rate, micro precision over returned known claims, and
  overall retrieval accuracy. Keep these separate from stale precision, recall,
  and accuracy.

## Testing Decisions

- The confirmed highest seam for the gate is the public `retrieve(...)`
  interface, with an end-to-end `memory.capture` and `UserPromptSubmit` test
  proving the same context behavior through the local runtime.
- Add a configuration test proving that an omitted `top_k` resolves to five,
  an explicit positive value is preserved, and zero, booleans, and non-integer
  values fail through the public configuration loader. Add a retrieval test
  proving that more eligible candidates than `top_k` returns only the stable
  highest-ranked prefix, even when the token budget could fit all of them.
- Add an end-to-end task-start test proving that the TOML `top_k` setting,
  rather than only direct `retrieve(...)` calls, limits injected context.
- The first red-green slice proves that a term-only prompt returns no context.
  The next slice proves that the same term plus an independently matching claim
  or locator signal becomes eligible, while a weak candidate below the fixed
  score cutoff remains absent.
- Subsequent behavioral slices prove that terms below the claim weight do not
  outrank an otherwise comparable claim-text match, that an exact locator still
  dominates a term match, and that stale records are excluded even when their
  terms match exactly.
- Test validation through the public MCP boundary: blank strings, canonical
  duplicates, too many terms, and oversized terms reject the whole capture.
- Test Markdown compatibility by loading an existing document without the new
  field and observing unchanged retrieval behavior.
- Test revision history through persisted Markdown: a recapture differing only
  in retrieval terms creates a distinct current revision while preserving the
  earlier revision.
- The confirmed evaluation seam remains
  `evaluate_repository_corpus(...)`. Its first evaluator slice uses a small
  mixed manifest and observes independent freshness and retrieval results from
  the real lifecycle.
- Extend that slice with a source-backed distractor that shares the query term.
  The target is eligible only when corroborated, weak tails are excluded by the
  cutoffs, and removing terms changes only the supplementary score. This is the
  first red test for competitive retrieval and no-context exclusion semantics.
- Test the checked-in 100-case corpus against one exact reviewed baseline that
  includes freshness and retrieval metrics, the 20 declared-term cases, the 10
  unrelated negative controls, source-backed distractors, and the complete
  declared-term counterfactual.
- Keep the complete measurement under the existing `repository_evaluation`
  marker; no second benchmark command or parallel evaluator is introduced.
- Follow existing real temporary-Git-repository and MCP/hook test patterns;
  do not mock project-owned modules or assert private scoring details.
- During each vertical slice, observe the focused behavioral test fail, add the
  smallest production change, then rerun it. Before completion run formatter,
  lint, strict type checking, the default test suite, and the intentional
  repository-evaluation benchmark requested for this change.

## Documentation Decisions

- Update the public README's retrieval and capture sections with the fourth
  field, its fixed weight, concise examples, the top-five default, and the
  host-declared boundary.
- Update both installed host skills with optional `retrieval_terms` guidance
  and an example capture payload.
- Update the stored-memory example and the generated health-report presentation
  so declared terms are reviewable.

## Out of Scope

- Entity extraction, named-entity recognition, synonym expansion, stemming,
  query rewriting, embeddings, vector databases, or another LLM.
- Automatic generation, ranking, semantic validation, or truth scoring of
  terms.
- New evidence types, changes to evidence dependency graphs, or changing the
  meaning of active, stale, and superseded revisions.
- Learning retrieval weights from data, user-configurable weights, fuzzy
  matching, a persistent search index, dynamic `top_k`, or a new human-facing
  CLI.
- Increasing the repository corpus beyond 100 cases or publishing retrieval
  metrics as population estimates.
- Committing, pushing, or opening a pull request.

## Further Notes

Declared retrieval terms emulate only the controlled vocabulary benefit of an
entity layer. The host decides what a term means while the local engine stores
and matches literal text deterministically. This preserves Memory Stale's
provenance-first design: terms refine the ranking of an already corroborated
candidate, whereas evidence alone establishes whether a revision may be trusted
as active context.

The mixed corpus measures the ranking and false-context tradeoff inside the
same end-to-end project evaluation. A higher term-assisted target hit rate only
establishes that aliases improve a curated, corroborated candidate ordering. It
must be read beside no-context exclusion, precision, the held-constant overall
accuracy, and the predeclared holdout partition; it does not establish
semantic-search recall, safety, or general performance across arbitrary
repositories.

# 32 — Field-weighted locator retrieval

This spec supersedes spec 05 only for lexical ranking. The active-memory filter,
exact-reference priority, deterministic ordering, context format, configurable
budget, and `UserPromptSubmit` integration remain in force.

## Problem Statement

Memory Stale currently applies BM25 to one document made from a memory's claim
and durability reason. Evidence locators do not participate in lexical ranking;
they contribute only a large binary boost when the prompt contains the exact
locator or its path.

This creates a retrieval gap between exact provenance and natural task language.
A memory may be anchored to `src/security/session.py:rotate_token`, while a later
prompt asks to change token rotation in session handling without spelling that
locator literally. In that case, meaningful terms carried by the locator do not
help retrieve the memory. Retrieval depends entirely on whether the claim or
durability reason happens to repeat the prompt's vocabulary.

Treating all text as one unweighted document would not resolve the problem
cleanly. Claims state remembered behavior, durability reasons explain why it
matters, and locators identify code structure. Those fields have different
retrieval value and must remain independently auditable.

## Solution

Rank every active memory with deterministic field-weighted BM25. Score the
claim, durability reason, and combined evidence locators as separate lexical
fields, then add the existing exact-locator boost:

```text
score =
    BM25(claim) * 1.0
  + BM25(durability_reason) * 0.5
  + BM25(evidence_locators) * 2.0
  + exact_locator_matches * 100.0
```

The locator field contains every evidence locator on the memory, regardless of
evidence type or role. It uses structural tokenization so a locator such as
`src/security/session.py:rotate_token` contributes useful components including
`src`, `security`, `session`, `py`, `rotate`, and `token`. Exact path or symbol
text continues to dominate through the additive boost, while partial lexical
matches can now improve ranking without being treated as exact references.

Retrieval remains local, deterministic, explainable, and bounded. It does not
infer meaning, call another model, create embeddings, or change whether a memory
is active or stale.

## User Stories

1. As a developer, I want a prompt phrased in task language to find memories
   whose evidence names related files or symbols, so that I do not need to type
   an exact code locator.
2. As a developer, I want an exact path or symbol in my prompt to retain
   overwhelming priority, so that precise requests remain predictable.
3. As a developer, I want claim text to remain the principal natural-language
   description of remembered behavior, so that provenance does not replace
   semantic memory content.
4. As a developer, I want durability reasons to influence retrieval less than
   claims, so that supporting rationale does not dominate the behavior being
   recalled.
5. As a developer, I want evidence locators to carry stronger lexical weight
   than prose fields, so that code-oriented task language benefits from precise
   provenance.
6. As a developer, I want path segments, file stems, extensions, and symbol
   words to be searchable independently, so that `session` can match
   `session.py` and `token` can match `rotate_token`.
7. As a maintainer, I want each field's contribution to be explicit and fixed,
   so that ranking remains auditable and reproducible.
8. As a maintainer, I want memories with multiple evidence items to receive one
   combined locator-field score, so that retrieval behavior does not depend on
   storage order.
9. As a maintainer, I want stale memories excluded before any field statistics
   or ranking is calculated, so that stale provenance cannot affect active
   results indirectly.
10. As a Codex user, I want the same bounded context format and budget behavior,
    so that better ranking does not increase injected context unexpectedly.

## Observable Test Seam

The highest existing seam is the public retrieval operation: it receives a
memory corpus, a prompt, and a token budget, and returns the exact context that
can be injected into Codex. Behavioral tests observe inclusion, exclusion, and
result order through that returned context rather than inspecting token lists,
field statistics, or private scoring helpers.

The integration seam remains the real `UserPromptSubmit` lifecycle in a
temporary Git repository. A persisted active memory whose prose has no query
terms but whose locator has structurally related terms must be injected for a
non-exact prompt. This confirms that the field-weighted ranking is used by the
installed workflow rather than only by an isolated scoring unit.

This is the seam to confirm before writing the first implementation test.

## Expected Behavior

- Only memories whose current revision is `active` participate in corpus
  statistics, scoring, selection, or returned context.
- Query matching remains case-insensitive and Unicode-aware.
- Claim, durability reason, and evidence locators are scored as separate BM25
  fields with weights `1.0`, `0.5`, and `2.0`, respectively.
- BM25 retains the existing constants `k1 = 1.5` and `b = 0.75`. Document
  frequency, average field length, and length normalization are calculated
  independently for each field over active memories.
- All locators belonging to one memory are normalized and concatenated into one
  locator-field document. Their order must not change the score.
- Locator tokenization splits path separators, dots, colons, underscores,
  hyphens, and camel-case boundaries. It case-folds components and discards
  empty components. No stemming, lemmatization, synonyms, or fuzzy matching is
  introduced.
- Natural-language fields preserve the existing lexical tokenization contract;
  this spec does not redefine claim or durability-reason parsing.
- Each exact evidence locator or exact locator path recognized in the prompt
  adds `100.0` after the three weighted BM25 field scores. Partial locator-token
  matches never receive this boost.
- A memory is a retrieval candidate when its total score is greater than zero,
  including when its only positive contribution comes from locator BM25.
- Results remain ordered by descending total score and then by stable memory ID
  for deterministic ties.
- Selection retains the existing context-block representation, approximate
  token-cost calculation, skip-if-over-budget behavior, and default budget of
  1,500 tokens.
- Empty corpora, empty lexical queries, non-positive budgets, and unrelated
  prompts continue to return empty context.
- No persisted-memory schema or stored Markdown changes are required.

## Implementation Decisions

- Extend the deterministic retrieval component rather than adding a separate
  index, search service, or storage representation.
- Represent each memory as three logical BM25 fields. Do not concatenate fields
  before scoring because that would erase the required weights and field-length
  normalization.
- Build the locator field from the canonical evidence collection already held
  by the active memory revision. Both primary and supporting evidence, and all
  supported evidence types, participate with the same locator-field weight.
- Normalize all locator components deterministically. Preserve duplicates only
  when they arise from distinct locator occurrences; canonical evidence order
  must not affect the resulting frequency counts.
- Keep the numeric weights and exact-match boost as named ranking constants in
  the retrieval component. They are fixed product policy in this version, not
  new user configuration.
- Preserve the public retrieval interface and returned context contract. No new
  public scoring API is required.
- Preserve exact-reference matching as a separate structural signal. Locator
  BM25 supplements it and must not turn a partial term match into an exact
  match.
- Continue to derive all ranking state in memory for each retrieval operation;
  Markdown remains the source of truth and no index migration is introduced.

## Testing Decisions

- First red-green slice: through the public retrieval operation, use an active
  memory whose claim and durability reason share no terms with the prompt but
  whose locator contains independently chosen matching path and symbol terms.
  Require the memory to be returned. The current implementation must fail
  because locator text is absent from its BM25 document and the prompt contains
  no exact locator.
- Second slice: provide multiple eligible memories and enough budget for all of
  them, then assert returned order demonstrates the fixed relative field
  weights. Use independent literal fixtures rather than recomputing production
  scores in the test.
- Test each field distinction with behavioral ranking examples: claim over an
  otherwise equivalent durability match, and locator over an otherwise
  equivalent claim match when term statistics are controlled.
- Test structural locator normalization with path segments, file extensions,
  snake_case, kebab-case, and camelCase symbols through retrieval outcomes, not
  private tokenizer calls.
- Test that a prompt containing the full locator still ranks that memory above
  stronger non-exact lexical matches, preserving the `100.0` exact boost.
- Test multiple evidence locators in different canonical orders and require
  identical observable ranking.
- Preserve regression coverage for stale filtering, unrelated prompts,
  deterministic ID tie-breaking, empty input, and budget truncation.
- Add an integration slice through the real `UserPromptSubmit` hook with a
  temporary Git repository, real persisted Markdown, and a non-exact prompt
  whose only connection to the memory is structural locator vocabulary.
- Do not assert private helper calls, internal token arrays, floating-point
  intermediate values, or an implementation-specific loop order.
- During implementation, run each focused test to observe the expected red
  phase, add only enough production behavior for green, then run the required
  formatter, linter, strict type checker, and full default test suite.

## Documentation Decisions

- Update the public retrieval description to state that lexical ranking is
  field-weighted across claims, durability reasons, and evidence locators.
- Document the relative weights and retain the explicit statement that exact
  paths and symbols receive priority.
- Keep the explanation concise and distinguish lexical locator decomposition
  from semantic search.

## Out of Scope

- Embeddings, vector databases, semantic search, GraphRAG, reranking through an
  LLM, or calling another model.
- Stemming, lemmatization, synonym expansion, typo tolerance, edit distance, or
  other fuzzy matching.
- Learning weights from feedback or evaluation data.
- User-configurable field weights, BM25 constants, or exact-match boost.
- Changing capture, evidence resolution, fingerprints, active/stale lifecycle,
  revision identity, storage schema, or Markdown format.
- Adding a persistent derived index or a human-facing search CLI.
- Changing context rendering, token-budget estimation, or hook transport.

## Further Notes

- The proposed weights intentionally make locators influential without allowing
  partial lexical matches to outrank an exact structural reference under normal
  scores.
- Locator decomposition improves lexical recall but does not make the engine
  semantic. For example, `rotate` and `rotation` remain different terms unless
  another exact token such as `session` or `token` connects the query.
- Repository evaluation of retrieval quality is separate from the mandatory
  default suite and should run only when an implementation task explicitly
  requests that intentional measurement.

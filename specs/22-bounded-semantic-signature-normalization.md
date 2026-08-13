# 22 — Bounded semantic signature normalization

**Status: Done (2026-08-12)**

## Problem Statement

Memory Stale correctly keeps a revision available when its recorded evidence is
unchanged and requires revalidation when that evidence changes. Its current
symbol fingerprints are structural: apart from comments and formatting, every
syntax token contributes to the fingerprint. Consequently, a bounded set of
locally provable, behavior-preserving rewrites unnecessarily makes memories
stale.

The fixed 100-trial repository lifecycle corpus records 38 true stale, 26 false
stale, 12 missed changes, and 24 true active outcomes (62% aggregate accuracy).
The false-stale outcomes include literal simplifications and local-variable
renames that can be recognized safely without executing code. The missed changes
are incomplete-provenance cases: the recorded primary evidence is unchanged but
an undeclared dependency changes. Those outcomes must remain visible rather
than being hidden by inference beyond the evidence model.

The corpus is an immutable oracle for this work. Its samples, labels, fixtures,
rationales, families, evidence declarations, prompts, and ordering must not be
edited to improve the result. Any improvement must be a general production
behavior, never a corpus-specific exception.

## Solution

Add a deterministic, fail-closed semantic-normalization layer to symbol
fingerprinting. It will normalize only a closed set of syntax forms whose
equivalence can be established from the resolved symbol's local syntax. All
other syntax will retain its structural representation.

The required delivery consists of two independent stages:

1. Normalize allowlisted, side-effect-free literal expressions to their
   canonical literal result.
2. Normalize strictly local bindings and references to deterministic local
   identities while retaining every externally observable, captured, ambiguous,
   or unresolved name verbatim.

A third stage is optional and may add only three conservative local reductions:
a single-use local alias, a literal-false branch, and a `finally` block that
contains only the language's no-op statement. It may not delay the two required
stages or grow into general semantic analysis.

Fingerprint evolution must be versioned. Existing unversioned fingerprints
continue to use legacy structural comparison until a later capture records a new
revision. Updating the local runtime alone must not make legacy evidence stale.

## User Stories

1. As a Memory Stale user, I want a memory to remain active after a provably
   equivalent literal rewrite, so that harmless maintenance does not require
   unnecessary revalidation.
2. As a Memory Stale user, I want a local temporary-variable rename to preserve
   a memory when no observable contract changed, so that implementation naming
   does not create noise.
3. As a user, I want changed return values to continue making evidence stale,
   so that semantic regressions are not normalized away.
4. As a user, I want changed comparison boundaries and branch results to remain
   significant, so that the safety boundary remains conservative.
5. As a library consumer, I want public function, method, and parameter names
   to remain significant, so that API-contract changes require revalidation.
6. As a maintainer, I want unresolved, shadowed, captured, and reflective names
   retained structurally, so that uncertain scope resolution never produces a
   false active result.
7. As a maintainer, I want unsupported expressions to fall back to structural
   fingerprints, so that the feature cannot silently become a general
   equivalence engine.
8. As a user with existing memories, I want legacy fingerprints to stay
   comparable after an upgrade, so that a fingerprint-format change itself does
   not invalidate history.
9. As a contributor, I want each accepted normalization to be grammar-aware,
   so that superficially similar syntax is not treated as equivalent across
   languages with different semantics.
10. As a contributor, I want comments and formatting to remain insignificant
    in all supported grammars, so that the existing signal-to-noise guarantee is
    preserved.
11. As an evaluator, I want literal corpus counts after each required stage, so
    that any score movement is attributable to observable behavior.
12. As an evaluator, I want the corpus inputs to remain byte-for-byte unchanged,
    so that the benchmark remains an independent oracle.
13. As a reviewer, I want incomplete provenance to remain reported as a product
    limitation, so that active evidence is not confused with proof that a claim
    is true or complete.
14. As a security-conscious user, I want fingerprinting never to execute
    repository code, so that revalidation stays deterministic and local.
15. As a maintainer, I want optional reductions to be independently removable,
    so that their risk cannot compromise the required delivery.

## Implementation Decisions

### Confirmed test seams

The proposed highest direct seam is the public symbol-signature operation: real
source files are resolved by supported grammar and a `path:symbol` locator
returns a deterministic fingerprint or a structured resolution error.

The proposed highest end-to-end seam is the repository lifecycle evaluator:
it creates a temporary Git repository, captures a memory through the public
hook and MCP boundaries, applies the trial change, completes reconciliation,
and observes whether a later prompt receives the memory as active context.

The user confirmed these seams when authorizing implementation. The direct seam
governs each red-green slice; the lifecycle seam verifies the fixed corpus
without changing its input.

### Normalization boundary

- Normalize before hashing the resolved symbol, inside the existing
  symbol-indexing boundary. Do not introduce evaluator-specific lifecycle
  decisions or special cases.
- Use grammar node kinds and fields, never regular expressions over source.
- Model each normalization as a small pure transformation over resolved syntax.
  A transformation that cannot prove its preconditions must emit the existing
  structural form unchanged.
- Do not execute repository code or add an interpreter, compiler invocation,
  symbolic executor, theorem prover, test execution as a fingerprint oracle,
  another LLM, embeddings, or a remote service.
- Do not special-case corpus identifiers, filenames, claims, fixture text, or
  prompts.

### Required stage 1: closed literal expressions

- Use an explicit allowlist of syntax shapes and operators. The first supported
  forms are integer subtraction such as `2 - 1`, neutral integer addition such
  as `1 + 0`, double negation of a boolean literal, selection from a literal
  one-item tuple only where the language has an equivalent form, and a
  conditional expression selected by a boolean literal.
- Permit evaluation only when the complete result derives from literals without
  calls, name reads, mutation, observable identity allocation, coercion,
  overloaded operators, or repository execution.
- Document and enforce a deliberately small, cross-language-safe integer range.
  Reject division, overflow-sensitive arithmetic, language-specific coercion,
  unsupported indexing, and every form whose equivalence differs across
  supported grammars.
- On the unchanged corpus, this stage must produce exactly 38 true stale, 15
  false stale, 12 missed changes, and 35 true active outcomes (73% aggregate
  accuracy, 76% stale recall, and 70% specificity) before its baseline is
  updated.

### Required stage 2: strictly local binding renames

- Assign canonical local identifiers by deterministic declaration order and
  rewrite only references unambiguously resolved to those declarations.
- Preserve the original spelling of function, method, class, parameter, field,
  property, attribute, label, global, import, export, captured, unresolved, and
  ambiguously shadowed names.
- Treat any nested-function or closure boundary as non-local for this feature.
  Preserve spelling when reflective facilities such as `eval`, `locals`, macros,
  or comparable language mechanisms can observe it.
- If a grammar does not provide sufficient binding information for a case, keep
  its structural signature.
- On the unchanged corpus, the two required stages together must produce exactly
  38 true stale, 8 false stale, 12 missed changes, and 42 true active outcomes
  (80% aggregate accuracy, 76% stale recall, and 84% specificity). This is the
  required delivery target; it is not an estimate of population accuracy.

### Optional stage 3: small structural reductions

- Only after the required stages are green, optionally reduce a local alias
  assigned once and read once when its initializer is side-effect-free; remove
  a literal-false branch; and ignore a `finally` block containing only the
  language's no-op statement.
- Each reduction is separately test-driven and omitted if it requires general
  control-flow, dataflow, purity, or interprocedural analysis.
- If all are implemented safely, the expected unchanged-corpus result is 38
  true stale, 5 false stale, 12 missed changes, and 45 true active outcomes
  (83% aggregate accuracy, 76% stale recall, 90% specificity, and approximately
  76.4% macro-family accuracy). This optional result cannot broaden or delay the
  required work.

### Compatibility and product limits

- New fingerprints identify their normalization version. A persisted legacy
  fingerprint remains comparable with the legacy structural algorithm until
  recapture writes a new revision.
- Preserve all currently supported grammars and reject unsupported languages;
  there is no file-level or unsupported-language fallback.
- Preserve the meaning of lifecycle states: `active` means every recorded item
  of evidence still matches, and `stale` means recorded evidence changed,
  disappeared, or cannot resolve. Neither state proves claim truth.
- Do not add automatic import, call, constant, configuration, schema, or
  dataflow discovery. The incomplete-provenance cases remain missed changes
  because their changed dependency was never declared as evidence.
- Do not normalize logging, metrics, tracing, identity helpers, guards that
  call another function, or other changes that require interprocedural purity
  or side-effect reasoning.

## Testing Decisions

- Test observable behavior through the proposed public symbol-signature seam
  using real files, then test the proposed lifecycle-evaluator seam through
  real hooks, MCP capture, persisted memory, reconciliation, and retrieval.
  Do not test private normalization helpers directly.
- The first red-green slice is one Python
  literal expression with an independently known preserved result: it initially
  has a different fingerprint and then has the same fingerprint after the
  smallest allowlisted normalization.
- Add one behavioral slice per accepted literal form. Each includes independent
  nearby counterexamples that remain different: a changed result, a call, a
  name read, an unsupported operator, and language-sensitive syntax when
  applicable.
- Add local-binding rename coverage one grammar at a time. For each grammar,
  cover parameter, field or attribute, shadowing, nested capture, and
  reflective counterexamples whenever those constructs exist.
- Retain the existing per-grammar proofs that comments and formatting are
  insignificant while literal, public-signature, control-flow, deletion, and
  referenced-symbol rename changes remain significant.
- Prove compatibility through persisted public evidence: unchanged legacy
  fingerprinted memory remains active after upgrade, while a real structural
  change still becomes stale.
- After each required stage, run the fixed repository corpus and assert the
  literal matrix stated above. Update only the checked-in result after the
  production behavior is proven; do not edit corpus input.
- Before completion, verify that the corpus manifest has no diff. Run the
  repository's required formatting, lint, strict typing, and full test gates.

## Out of Scope

- Changing, regenerating, relabeling, reordering, replacing, or adding any
  fixed repository-lifecycle corpus trial.
- Automatic provenance or call-graph discovery; new evidence types; file-level
  evidence fallbacks; or changes to evidence-graph traversal.
- Interprocedural purity, side-effect, control-flow, or dataflow analysis.
- General expression equivalence, arbitrary constant folding, or execution of
  repository code to decide equivalence.
- Changes to retrieval ranking, capture policy, lifecycle state names, or the
  meaning of `active` and `stale`.
- Claims that the fixed-corpus score generalizes to real repositories.
- Optional Stage 3 reductions unless separately authorized.
- Commits, publication, or other external actions.

## Further Notes

The corpus's incomplete-provenance outcomes are intentional evidence-model
limits, not candidates for evaluator adjustment. Codex declares supporting
evidence and dependency edges; the deterministic core resolves, fingerprints,
and traverses that declared graph. Keeping this boundary explicit is more
valuable than raising a benchmark score through undeclared-provenance inference.

The required two stages were delivered on the unchanged corpus at
`38 / 8 / 12 / 42` (80% aggregate accuracy). The optional Stage 3 reductions
were intentionally not implemented.

The `to-spec` workflow also calls for publication to the configured project
issue tracker with the `ready-for-agent` label. No tracker configuration or
triage vocabulary was supplied for this session, and this request authorizes
only revision of the local specification. Publication is therefore deliberately
deferred rather than inferred.

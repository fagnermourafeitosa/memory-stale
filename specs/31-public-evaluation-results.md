# 31 — Public evaluation results and methodology

## Problem Statement

Memory Stale has a deterministic, human-labeled repository lifecycle corpus and
a checked-in baseline, but its public README does not expose the measured
results or explain how they were obtained. A reader therefore cannot distinguish
the tool's measured corpus behavior from a general accuracy claim, understand
the error modes behind the aggregate score, or reproduce the measurement.

## Solution

Add a concise evaluation section to the public README that reports the current
100-case corpus result, defines the classification task and metrics, summarizes
the end-to-end methodology, links to the auditable evaluation artifacts, and
states how maintainers verify and update the statistics. Keep curated-corpus
quality separate from repeated-run reproducibility, and place limitations beside
the results so that neither measurement is presented as population accuracy.

## User Stories

1. As a prospective user, I want to see measured results in the README, so that I
   can assess the tool using evidence rather than product claims.
2. As a reader, I want the positive class and confusion matrix defined, so that I
   can interpret precision, recall, and accuracy correctly.
3. As a maintainer, I want the reported rates tied to literal counts, so that
   rounded percentages remain auditable.
4. As a reviewer, I want direct links to the corpus and checked-in result, so that
   I can inspect every fixture, label rationale, and observed outcome.
5. As a contributor, I want the highest end-to-end evaluation seam described, so
   that future measurements exercise Git, hooks, MCP capture, persistence,
   reconciliation, and retrieval together.
6. As a product evaluator, I want family-level weaknesses summarized, so that a
   strong aggregate result does not hide incomplete provenance or conservative
   false-stale behavior.
7. As a statistician, I want Wilson intervals labeled as descriptive corpus
   intervals, so that they are not mistaken for population estimates.
8. As a maintainer, I want operational failures separated from semantic
   classifications, so that evaluator failures cannot disappear into the
   confusion matrix.
9. As a maintainer, I want a documented refresh procedure, so that intentional
   product or corpus changes produce a reproducible, reviewable baseline update.
10. As a reader, I want repeated-run stability distinguished from unique sample
    size, so that 1,000 executions of 100 cases are not advertised as 1,000
    independent examples.
11. As a contributor, I want the immutable-corpus tuning boundary documented, so
    that fixtures and labels are not changed merely to improve a score.
12. As a project owner, I want evaluation documentation to remain compact and
    adjacent to current limitations, so that important qualifications are not
    hidden in implementation specs.

## Implementation Decisions

- The highest observable seam is the rendered public README section: its literal
  counts, rates, links, methodology, and limitations must agree with the
  versioned evaluation artifacts.
- Report the current corpus as 100 unique, human-labeled cases balanced between
  50 semantic changes and 50 preserved behaviors across every supported grammar.
- Define a positive observation as a semantic change that should make the memory
  stale. Publish the literal matrix as 38 true stale, 8 false stale, 12 missed
  changes, and 42 true active outcomes.
- Publish overall accuracy, stale precision, stale recall, F1, specificity,
  unnecessary revalidation rate, missed semantic change rate, and unweighted
  macro-family accuracy. Derive any additional displayed metric from the literal
  checked-in matrix and round display percentages to one decimal place.
- Explain that every case creates a temporary Git repository and crosses the real
  prompt hook, MCP capture, persisted Markdown, stop reconciliation, and later
  retrieval boundary. Labels remain human-authored and independent of tool output.
- Link the public section to the versioned corpus, dated baseline, evaluation
  contract, evaluator implementation, and reproducibility test.
- Summarize the principal error concentration: all missed changes in the current
  corpus belong to incomplete provenance, while all false-stale observations
  belong to conservative behavior-preserving transformations.
- State that the dated 1,000-execution check repeated the same 100 unique cases
  ten times, matched the baseline in every execution, and had no operational
  failures. Do not use those repeats to narrow statistical intervals or claim a
  larger independent sample.
- Document that an intentional statistic update requires independently reviewed
  labels, a versioned corpus or behavior change, a fresh end-to-end evaluation,
  exact baseline review, and synchronized public documentation. Product tuning
  must not mutate the evaluation oracle merely to raise the score.
- Keep operational outcomes visible outside the semantic matrix and report both
  attempted and classifiable counts.
- Describe Wilson intervals as descriptive uncertainty for this curated corpus,
  never as evidence of generalization to arbitrary repositories.
- Do not change runtime behavior, evaluator behavior, fixtures, labels, corpus
  composition, or the checked-in baseline in this documentation change.

## Testing Decisions

- This is documentation-only work, so it does not require a fabricated failing
  production test or a red-green cycle.
- Compare README literals directly with the checked-in result rather than
  recalculating expected values through production metric code.
- Verify that every relative link in the new section resolves to a tracked
  repository artifact.
- Preserve the existing public evaluator seam and its exact baseline assertion.
- Treat the completed ten-run check as 1,000 lifecycle executions for
  reproducibility and only 100 unique samples for semantic quality.
- Run formatting, lint, strict typing, and the full test suite before completion.

## Out of Scope

- Changing production behavior or evaluator calculations.
- Adding, removing, relabeling, reordering, or tuning corpus trials.
- Claiming that the curated corpus estimates behavior across all repositories.
- Building a randomly sampled external benchmark or mining public repository
  changes.
- Adding an LLM judge, embeddings, a remote benchmark service, or a human-facing
  evaluation CLI.
- Treating repeated deterministic executions as independent semantic samples.
- Publishing an issue, pushing a branch, opening a pull request, or tagging a
  release without separate authorization.

## Further Notes

The public score is a regression-oriented corpus score. Its most useful product
signal is the distribution of errors by family, not the aggregate percentage in
isolation.

The `to-spec` workflow also requests publication to a configured issue tracker
with the `ready-for-agent` label. This repository provides no tracker or triage
configuration in the current task, and the user authorized a local README update
and commit only. External publication is therefore deferred.

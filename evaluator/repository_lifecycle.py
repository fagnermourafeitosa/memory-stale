"""Repository-scale evaluation through the local runtime boundaries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import sqrt
from pathlib import Path, PurePosixPath
from typing import cast

import yaml


class RepositoryCorpusError(ValueError):
    """Raised when a repository evaluation manifest is unsafe or incomplete."""


@dataclass(frozen=True)
class RepositoryTrial:
    """One independently labeled, end-to-end repository observation."""

    identifier: str
    family: str
    semantic_case: str
    label_rationale: str
    label: str
    initial_files: dict[str, str]
    capture_files: dict[str, str]
    capture: dict[str, object]
    change_files: dict[str, str]
    distractor_files: dict[str, str]
    distractor_captures: tuple[dict[str, object], ...]
    retrieval_case: str
    retrieval_partition: str | None
    expected_retrieval: bool
    retrieval_prompt: str
    expected_stale_reasons: dict[str, str] | None


@dataclass(frozen=True)
class OperationalOutcome:
    """A failure that cannot be treated as a semantic classification."""

    identifier: str
    kind: str
    detail: str


@dataclass(frozen=True)
class TrialOutcome:
    """The persisted lifecycle and later availability observations for one trial."""

    identifier: str
    family: str
    label: str
    lifecycle_status: str
    retrieval_case: str
    retrieval_partition: str | None
    expected_retrieval: bool
    target_retrieved: bool
    context_returned: bool
    returned_claim_count: int
    term_baseline_target_retrieved: bool | None
    term_baseline_context_returned: bool | None
    term_baseline_returned_claim_count: int | None


@dataclass(frozen=True)
class ConfusionMatrix:
    """Counts that compare human semantic labels with availability decisions."""

    true_stale: int
    false_stale: int
    missed_change: int
    true_active: int


@dataclass(frozen=True)
class RateMetric:
    """A descriptive rate with its numerator, denominator, and Wilson interval."""

    count: int
    denominator: int
    rate: float | None
    wilson_interval: tuple[float, float] | None


@dataclass(frozen=True)
class EvaluationMetrics:
    """Descriptive rates for the curated, non-random repository corpus."""

    stale_recall: RateMetric
    stale_precision: RateMetric
    specificity: RateMetric
    unnecessary_revalidation_rate: RateMetric
    missed_semantic_change_rate: RateMetric
    overall_accuracy: RateMetric


@dataclass(frozen=True)
class RetrievalEvaluationMetrics:
    """Availability rates, kept separate from lifecycle freshness rates."""

    recall: RateMetric
    exclusion_rate: RateMetric
    precision: RateMetric
    overall_accuracy: RateMetric
    without_terms_overall_accuracy: RateMetric
    term_baseline_recall: RateMetric
    term_assisted_recall: RateMetric
    term_baseline_exclusion_rate: RateMetric
    term_assisted_exclusion_rate: RateMetric
    term_baseline_precision: RateMetric
    term_assisted_precision: RateMetric
    term_net_gain: int


@dataclass(frozen=True)
class FamilyEvaluation:
    """One family's classifiable observations and unweighted accuracy input."""

    family: str
    sample_count: int
    matrix: ConfusionMatrix
    accuracy: RateMetric


@dataclass(frozen=True)
class RetrievalPartitionEvaluation:
    """Fixed declared-term split used to report calibration and holdout outcomes."""

    partition: str
    sample_count: int
    metrics: RetrievalEvaluationMetrics


@dataclass(frozen=True)
class RepositoryEvaluationResult:
    """Deterministic, classifiable outcomes and separately retained failures."""

    corpus_version: int
    attempted_count: int
    sample_count: int
    trials: tuple[TrialOutcome, ...]
    matrix: ConfusionMatrix
    metrics: EvaluationMetrics
    retrieval_metrics: RetrievalEvaluationMetrics
    retrieval_partitions: tuple[RetrievalPartitionEvaluation, ...]
    families: tuple[FamilyEvaluation, ...]
    macro_family_accuracy: float | None
    operational_outcomes: tuple[OperationalOutcome, ...]


def load_repository_corpus(path: Path) -> tuple[int, tuple[RepositoryTrial, ...]]:
    """Load a versioned repository corpus without inferring semantic labels."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("version") not in {1, 2, 3}:
        raise RepositoryCorpusError("repository corpus version must be 1, 2, or 3")
    version = cast(int, loaded["version"])
    raw_trials = loaded.get("trials")
    if not isinstance(raw_trials, list) or not raw_trials:
        raise RepositoryCorpusError("repository corpus trials must be a non-empty list")
    trials: list[RepositoryTrial] = []
    distractor_files, distractor_captures = _retrieval_distractors(
        loaded.get("retrieval_distractors")
    )
    identifiers: set[str] = set()
    for raw_trial in raw_trials:
        if not isinstance(raw_trial, dict):
            raise RepositoryCorpusError("repository trial must be an object")
        identifier = _required_string(raw_trial, "id", "trial")
        if identifier in identifiers:
            raise RepositoryCorpusError(f"{identifier}: duplicate id")
        identifiers.add(identifier)
        label = _required_string(raw_trial, "label", identifier)
        if label not in {"changed", "preserved"}:
            raise RepositoryCorpusError(f"{identifier}: label must be changed or preserved")
        capture = _capture_definition(raw_trial.get("capture"), identifier)
        retrieval_case = raw_trial.get("retrieval_case", "standard")
        if retrieval_case not in {"standard", "declared-term", "unrelated"}:
            raise RepositoryCorpusError(
                f"{identifier}: retrieval_case must be standard, declared-term, or unrelated"
            )
        expected_retrieval = raw_trial.get("expected_retrieval", label == "preserved")
        if not isinstance(expected_retrieval, bool):
            raise RepositoryCorpusError(f"{identifier}: expected_retrieval must be a boolean")
        if retrieval_case == "declared-term" and "retrieval_terms" not in capture:
            raise RepositoryCorpusError(
                f"{identifier}: declared-term retrieval cases require retrieval_terms"
            )
        raw_partition = raw_trial.get("retrieval_partition")
        if retrieval_case == "declared-term":
            if version >= 3 and raw_partition not in {"calibration", "holdout"}:
                raise RepositoryCorpusError(
                    f"{identifier}: declared-term retrieval cases require a calibration or holdout partition"
                )
        elif raw_partition is not None:
            raise RepositoryCorpusError(
                f"{identifier}: retrieval_partition is only valid for declared-term cases"
            )
        trial_sources = (
            set(cast(dict[object, object], raw_trial.get("initial_files", {})))
            | set(cast(dict[object, object], raw_trial.get("capture_files", {})))
            | set(cast(dict[object, object], raw_trial.get("change_files", {})))
        )
        if retrieval_case == "declared-term" and trial_sources & set(distractor_files):
            raise RepositoryCorpusError(
                f"{identifier}: retrieval distractor files conflict with trial files"
            )
        trials.append(
            RepositoryTrial(
                identifier=identifier,
                family=_required_string(raw_trial, "family", identifier),
                semantic_case=_required_string(raw_trial, "semantic_case", identifier),
                label_rationale=_required_string(raw_trial, "label_rationale", identifier),
                label=label,
                initial_files=_sources(raw_trial.get("initial_files"), identifier, "initial_files"),
                capture_files=_sources(raw_trial.get("capture_files"), identifier, "capture_files"),
                capture=capture,
                change_files=_sources(raw_trial.get("change_files"), identifier, "change_files"),
                distractor_files=(distractor_files if retrieval_case == "declared-term" else {}),
                distractor_captures=(
                    distractor_captures if retrieval_case == "declared-term" else ()
                ),
                retrieval_case=cast(str, retrieval_case),
                retrieval_partition=cast(str | None, raw_partition),
                expected_retrieval=expected_retrieval,
                retrieval_prompt=_required_string(raw_trial, "retrieval_prompt", identifier),
                expected_stale_reasons=_stale_reasons(
                    raw_trial.get("expected_stale_reasons"), identifier
                ),
            )
        )
    cases_by_family: dict[str, list[str]] = {}
    for trial in trials:
        cases_by_family.setdefault(trial.family, []).append(trial.semantic_case)
    for family, cases in cases_by_family.items():
        if len(cases) > 1 and len(set(cases)) < 2:
            raise RepositoryCorpusError(
                f"{family}: multi-sample families require distinct semantic cases"
            )
    return version, tuple(sorted(trials, key=lambda trial: trial.identifier))


def evaluate_repository_corpus(
    corpus_path: Path,
    repositories_root: Path,
    runtime_root: Path,
) -> RepositoryEvaluationResult:
    """Run labeled trials through hook commands and the MCP stdio process."""
    version, trials = load_repository_corpus(corpus_path)
    repositories_root.mkdir(parents=True, exist_ok=True)
    outcomes: list[TrialOutcome] = []
    operational: list[OperationalOutcome] = []
    for trial in trials:
        outcome, failures = _run_trial(trial, repositories_root / trial.identifier, runtime_root)
        if outcome is not None:
            if trial.retrieval_case == "declared-term":
                baseline, baseline_failures = _run_trial(
                    trial,
                    repositories_root / f"{trial.identifier}-without-retrieval-terms",
                    runtime_root,
                    include_retrieval_terms=False,
                )
                operational.extend(baseline_failures)
                if baseline is None:
                    operational.append(
                        _failure(trial, "counterfactual_failure", "term baseline was unavailable")
                    )
                else:
                    outcome = replace(
                        outcome,
                        term_baseline_target_retrieved=baseline.target_retrieved,
                        term_baseline_context_returned=baseline.context_returned,
                        term_baseline_returned_claim_count=baseline.returned_claim_count,
                    )
            outcomes.append(outcome)
        operational.extend(failures)
    ordered_outcomes = tuple(sorted(outcomes, key=lambda outcome: outcome.identifier))
    matrix = _matrix(ordered_outcomes)
    families = _families(ordered_outcomes)
    return RepositoryEvaluationResult(
        corpus_version=version,
        attempted_count=len(trials),
        sample_count=len(ordered_outcomes),
        trials=ordered_outcomes,
        matrix=matrix,
        metrics=_metrics(matrix),
        retrieval_metrics=_retrieval_metrics(ordered_outcomes),
        retrieval_partitions=_retrieval_partitions(ordered_outcomes),
        families=families,
        macro_family_accuracy=(
            sum(cast(float, family.accuracy.rate) for family in families) / len(families)
            if families
            else None
        ),
        operational_outcomes=tuple(
            sorted(
                operational, key=lambda outcome: (outcome.identifier, outcome.kind, outcome.detail)
            )
        ),
    )


def assert_repository_baseline(result: RepositoryEvaluationResult, baseline_path: Path) -> None:
    """Require a checked-in baseline to state the exact observed evaluation result."""
    loaded = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("version") not in {1, 2, 3}:
        raise RepositoryCorpusError("repository baseline version must be 1, 2, or 3")
    baseline = cast(dict[object, object], loaded)
    baseline_version = cast(int, baseline["version"])
    if baseline.get("corpus_version") != result.corpus_version:
        raise RepositoryCorpusError("repository baseline corpus_version differs")
    if baseline.get("sample_count") != result.sample_count:
        raise RepositoryCorpusError("repository baseline sample_count differs")
    if baseline_version >= 2 and baseline.get("attempted_count") != result.attempted_count:
        raise RepositoryCorpusError("repository baseline attempted_count differs")
    _assert_mapping(baseline.get("matrix"), _matrix_mapping(result.matrix), "matrix")
    raw_metrics = baseline.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise RepositoryCorpusError("repository baseline metrics must be an object")
    for name, metric in _metric_mapping(result.metrics).items():
        _assert_mapping(raw_metrics.get(name), metric, f"metrics.{name}")
    if baseline_version >= 2:
        expected_families = [
            {
                "family": item.family,
                "sample_count": item.sample_count,
                "matrix": _matrix_mapping(item.matrix),
                "accuracy": _metric_value(item.accuracy),
            }
            for item in result.families
        ]
        if baseline.get("families") != expected_families:
            raise RepositoryCorpusError("repository baseline families differs")
        if baseline.get("macro_family_accuracy") != result.macro_family_accuracy:
            raise RepositoryCorpusError("repository baseline macro_family_accuracy differs")
    if baseline_version == 3:
        _assert_mapping(
            baseline.get("retrieval_metrics"),
            _retrieval_metric_mapping(result.retrieval_metrics),
            "retrieval_metrics",
        )
        expected_partitions = [
            _retrieval_partition_mapping(item) for item in result.retrieval_partitions
        ]
        if baseline.get("retrieval_partitions") != expected_partitions:
            raise RepositoryCorpusError("repository baseline retrieval_partitions differs")
    expected_operational = [
        {"id": item.identifier, "kind": item.kind, "detail": item.detail}
        for item in result.operational_outcomes
    ]
    if baseline.get("operational_outcomes") != expected_operational:
        raise RepositoryCorpusError("repository baseline operational_outcomes differs")
    if baseline_version == 3:
        expected_trials = [
            {
                "id": item.identifier,
                "family": item.family,
                "label": item.label,
                "lifecycle_status": item.lifecycle_status,
                "retrieval_case": item.retrieval_case,
                "retrieval_partition": item.retrieval_partition,
                "expected_retrieval": item.expected_retrieval,
                "target_retrieved": item.target_retrieved,
                "context_returned": item.context_returned,
                "returned_claim_count": item.returned_claim_count,
                "term_baseline_target_retrieved": item.term_baseline_target_retrieved,
                "term_baseline_context_returned": item.term_baseline_context_returned,
                "term_baseline_returned_claim_count": item.term_baseline_returned_claim_count,
            }
            for item in result.trials
        ]
    else:
        expected_trials = [
            {
                "id": item.identifier,
                **({"family": item.family} if baseline_version == 2 else {}),
                "label": item.label,
                "lifecycle_status": item.lifecycle_status,
                "retrieval_status": item.lifecycle_status,
            }
            for item in result.trials
        ]
    if baseline.get("trials") != expected_trials:
        raise RepositoryCorpusError("repository baseline trials differs")


def repository_baseline_document(result: RepositoryEvaluationResult) -> dict[str, object]:
    """Render one complete version-three evaluator result for review and storage."""
    return {
        "version": 3,
        "corpus_version": result.corpus_version,
        "attempted_count": result.attempted_count,
        "sample_count": result.sample_count,
        "matrix": _matrix_mapping(result.matrix),
        "metrics": _metric_mapping(result.metrics),
        "retrieval_metrics": _retrieval_metric_mapping(result.retrieval_metrics),
        "retrieval_partitions": [
            _retrieval_partition_mapping(item) for item in result.retrieval_partitions
        ],
        "families": [
            {
                "family": item.family,
                "sample_count": item.sample_count,
                "matrix": _matrix_mapping(item.matrix),
                "accuracy": _metric_value(item.accuracy),
            }
            for item in result.families
        ],
        "macro_family_accuracy": result.macro_family_accuracy,
        "operational_outcomes": [
            {"id": item.identifier, "kind": item.kind, "detail": item.detail}
            for item in result.operational_outcomes
        ],
        "trials": [_trial_mapping_v3(item) for item in result.trials],
    }


def _trial_mapping_v3(item: TrialOutcome) -> dict[str, object]:
    return {
        "id": item.identifier,
        "family": item.family,
        "label": item.label,
        "lifecycle_status": item.lifecycle_status,
        "retrieval_case": item.retrieval_case,
        "retrieval_partition": item.retrieval_partition,
        "expected_retrieval": item.expected_retrieval,
        "target_retrieved": item.target_retrieved,
        "context_returned": item.context_returned,
        "returned_claim_count": item.returned_claim_count,
        "term_baseline_target_retrieved": item.term_baseline_target_retrieved,
        "term_baseline_context_returned": item.term_baseline_context_returned,
        "term_baseline_returned_claim_count": item.term_baseline_returned_claim_count,
    }


def _retrieval_partition_mapping(item: RetrievalPartitionEvaluation) -> dict[str, object]:
    return {
        "partition": item.partition,
        "sample_count": item.sample_count,
        "metrics": _retrieval_metric_mapping(item.metrics),
    }


def _run_trial(
    trial: RepositoryTrial,
    repository: Path,
    runtime_root: Path,
    *,
    include_retrieval_terms: bool = True,
) -> tuple[TrialOutcome | None, list[OperationalOutcome]]:
    failures: list[OperationalOutcome] = []
    shutil.rmtree(repository, ignore_errors=True)
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "evaluation@example.test")
    _git(repository, "config", "user.name", "Repository evaluation")
    managed_paths = (
        set(trial.initial_files)
        | set(trial.capture_files)
        | set(trial.change_files)
        | set(trial.distractor_files)
    )
    _replace_sources(repository, trial.initial_files, managed_paths)
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "initial repository blueprint")

    capture_start = _hook(
        runtime_root, repository, "UserPromptSubmit", "capture", trial.retrieval_prompt
    )
    if isinstance(capture_start, str):
        return None, [_failure(trial, "hook_failure", capture_start)]
    _replace_sources(
        repository, _sources_with_distractors(trial.capture_files, trial), managed_paths
    )
    capture_arguments = dict(trial.capture)
    if not include_retrieval_terms:
        capture_arguments.pop("retrieval_terms", None)
    capture_response = _capture(runtime_root, repository, capture_arguments)
    if isinstance(capture_response, str):
        _hook(runtime_root, repository, "Stop", "capture")
        return None, [_failure(trial, "capture_failure", capture_response)]
    for distractor in trial.distractor_captures:
        distractor_arguments = dict(distractor)
        if not include_retrieval_terms:
            distractor_arguments.pop("retrieval_terms", None)
        distractor_response = _capture(runtime_root, repository, distractor_arguments)
        if isinstance(distractor_response, str):
            _hook(runtime_root, repository, "Stop", "capture")
            return None, [_failure(trial, "capture_failure", distractor_response)]
    capture_stop = _hook(runtime_root, repository, "Stop", "capture")
    if isinstance(capture_stop, str):
        return None, [_failure(trial, "hook_failure", capture_stop)]
    capture_status = _memory_status(repository, str(trial.capture["claim"]))
    if capture_status != "active":
        return None, [_failure(trial, "capture_failure", f"persisted status: {capture_status}")]
    for distractor in trial.distractor_captures:
        distractor_status = _memory_status(repository, str(distractor["claim"]))
        if distractor_status != "active":
            return None, [
                _failure(
                    trial,
                    "capture_failure",
                    f"distractor persisted status: {distractor_status}",
                )
            ]
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "capture labeled claim")

    change_start = _hook(
        runtime_root, repository, "UserPromptSubmit", "change", trial.retrieval_prompt
    )
    if isinstance(change_start, str):
        return None, [_failure(trial, "hook_failure", change_start)]
    _replace_sources(
        repository, _sources_with_distractors(trial.change_files, trial), managed_paths
    )
    change_stop = _hook(runtime_root, repository, "Stop", "change")
    if isinstance(change_stop, str):
        return None, [_failure(trial, "hook_failure", change_stop)]
    lifecycle_status, stale_reasons = _memory_observation(repository, str(trial.capture["claim"]))
    if lifecycle_status not in {"active", "stale"}:
        return None, [
            _failure(trial, "unresolved_locator", f"persisted status: {lifecycle_status}")
        ]
    if trial.expected_stale_reasons is not None and stale_reasons != trial.expected_stale_reasons:
        return None, [_failure(trial, "stale_reason_mismatch", str(stale_reasons))]

    retrieval = _hook(
        runtime_root, repository, "UserPromptSubmit", "retrieval", trial.retrieval_prompt
    )
    if isinstance(retrieval, str):
        return None, [_failure(trial, "hook_failure", retrieval)]
    context = _additional_context(retrieval)
    claim = str(trial.capture["claim"])
    returned_claims = _returned_claims(context)
    return (
        TrialOutcome(
            identifier=trial.identifier,
            family=trial.family,
            label=trial.label,
            lifecycle_status=lifecycle_status,
            retrieval_case=trial.retrieval_case,
            retrieval_partition=trial.retrieval_partition,
            expected_retrieval=trial.expected_retrieval,
            target_retrieved=claim in returned_claims,
            context_returned=bool(returned_claims),
            returned_claim_count=len(returned_claims),
            term_baseline_target_retrieved=None,
            term_baseline_context_returned=None,
            term_baseline_returned_claim_count=None,
        ),
        failures,
    )


def _matrix(outcomes: tuple[TrialOutcome, ...]) -> ConfusionMatrix:
    return ConfusionMatrix(
        true_stale=sum(
            outcome.label == "changed" and outcome.lifecycle_status == "stale"
            for outcome in outcomes
        ),
        false_stale=sum(
            outcome.label == "preserved" and outcome.lifecycle_status == "stale"
            for outcome in outcomes
        ),
        missed_change=sum(
            outcome.label == "changed" and outcome.lifecycle_status == "active"
            for outcome in outcomes
        ),
        true_active=sum(
            outcome.label == "preserved" and outcome.lifecycle_status == "active"
            for outcome in outcomes
        ),
    )


def _families(outcomes: tuple[TrialOutcome, ...]) -> tuple[FamilyEvaluation, ...]:
    names = sorted({outcome.family for outcome in outcomes})
    results: list[FamilyEvaluation] = []
    for name in names:
        family_outcomes = tuple(outcome for outcome in outcomes if outcome.family == name)
        matrix = _matrix(family_outcomes)
        results.append(
            FamilyEvaluation(
                family=name,
                sample_count=len(family_outcomes),
                matrix=matrix,
                accuracy=_rate(
                    matrix.true_stale + matrix.true_active,
                    len(family_outcomes),
                ),
            )
        )
    return tuple(results)


def _metrics(matrix: ConfusionMatrix) -> EvaluationMetrics:
    return EvaluationMetrics(
        stale_recall=_rate(matrix.true_stale, matrix.true_stale + matrix.missed_change),
        stale_precision=_rate(matrix.true_stale, matrix.true_stale + matrix.false_stale),
        specificity=_rate(matrix.true_active, matrix.true_active + matrix.false_stale),
        unnecessary_revalidation_rate=_rate(
            matrix.false_stale, matrix.false_stale + matrix.true_active
        ),
        missed_semantic_change_rate=_rate(
            matrix.missed_change, matrix.missed_change + matrix.true_stale
        ),
        overall_accuracy=_rate(
            matrix.true_stale + matrix.true_active,
            matrix.true_stale + matrix.false_stale + matrix.missed_change + matrix.true_active,
        ),
    )


def _retrieval_metrics(
    outcomes: tuple[TrialOutcome, ...],
) -> RetrievalEvaluationMetrics:
    expected = tuple(outcome for outcome in outcomes if outcome.expected_retrieval)
    excluded = tuple(outcome for outcome in outcomes if not outcome.expected_retrieval)
    term_assisted = tuple(
        outcome
        for outcome in outcomes
        if outcome.retrieval_case == "declared-term" and outcome.expected_retrieval
    )
    declared_terms = tuple(
        outcome for outcome in outcomes if outcome.retrieval_case == "declared-term"
    )
    term_excluded = tuple(outcome for outcome in declared_terms if not outcome.expected_retrieval)
    baseline_hits = sum(outcome.term_baseline_target_retrieved is True for outcome in term_assisted)
    assisted_hits = sum(outcome.target_retrieved for outcome in term_assisted)
    returned_claim_count = sum(outcome.returned_claim_count for outcome in declared_terms)
    baseline_returned_claim_count = sum(
        outcome.term_baseline_returned_claim_count or 0 for outcome in declared_terms
    )
    assisted_correct = sum(_retrieval_success(outcome) for outcome in outcomes)
    baseline_correct = sum(_counterfactual_success(outcome) for outcome in outcomes)
    return RetrievalEvaluationMetrics(
        recall=_rate(sum(outcome.target_retrieved for outcome in expected), len(expected)),
        exclusion_rate=_rate(
            sum(_retrieval_success(outcome) for outcome in excluded), len(excluded)
        ),
        precision=_rate(
            sum(outcome.target_retrieved for outcome in term_assisted),
            returned_claim_count,
        ),
        overall_accuracy=_rate(assisted_correct, len(outcomes)),
        without_terms_overall_accuracy=_rate(baseline_correct, len(outcomes)),
        term_baseline_recall=_rate(baseline_hits, len(term_assisted)),
        term_assisted_recall=_rate(assisted_hits, len(term_assisted)),
        term_baseline_exclusion_rate=_rate(
            sum(outcome.term_baseline_context_returned is False for outcome in term_excluded),
            len(term_excluded),
        ),
        term_assisted_exclusion_rate=_rate(
            sum(not outcome.context_returned for outcome in term_excluded),
            len(term_excluded),
        ),
        term_baseline_precision=_rate(baseline_hits, baseline_returned_claim_count),
        term_assisted_precision=_rate(assisted_hits, returned_claim_count),
        term_net_gain=assisted_correct - baseline_correct,
    )


def _retrieval_partitions(
    outcomes: tuple[TrialOutcome, ...],
) -> tuple[RetrievalPartitionEvaluation, ...]:
    partitions = sorted(
        {
            outcome.retrieval_partition
            for outcome in outcomes
            if outcome.retrieval_partition is not None
        }
    )
    return tuple(
        RetrievalPartitionEvaluation(
            partition=partition,
            sample_count=sum(outcome.retrieval_partition == partition for outcome in outcomes),
            metrics=_retrieval_metrics(
                tuple(outcome for outcome in outcomes if outcome.retrieval_partition == partition)
            ),
        )
        for partition in partitions
    )


def _retrieval_success(outcome: TrialOutcome) -> bool:
    if outcome.expected_retrieval:
        return outcome.target_retrieved
    if outcome.retrieval_case == "standard":
        return not outcome.target_retrieved
    return not outcome.context_returned


def _counterfactual_success(outcome: TrialOutcome) -> bool:
    if outcome.term_baseline_target_retrieved is None:
        return _retrieval_success(outcome)
    if outcome.expected_retrieval:
        return outcome.term_baseline_target_retrieved
    return outcome.term_baseline_context_returned is False


def _rate(count: int, denominator: int) -> RateMetric:
    if denominator == 0:
        return RateMetric(count, denominator, None, None)
    rate = count / denominator
    z_score = 1.959963984540054
    z_squared = z_score * z_score
    center = (rate + z_squared / (2 * denominator)) / (1 + z_squared / denominator)
    spread = (
        z_score
        * sqrt(rate * (1 - rate) / denominator + z_squared / (4 * denominator * denominator))
        / (1 + z_squared / denominator)
    )
    return RateMetric(
        count, denominator, rate, (max(0.0, center - spread), min(1.0, center + spread))
    )


def _matrix_mapping(matrix: ConfusionMatrix) -> dict[str, int]:
    return {
        "true_stale": matrix.true_stale,
        "false_stale": matrix.false_stale,
        "missed_change": matrix.missed_change,
        "true_active": matrix.true_active,
    }


def _metric_mapping(
    metrics: EvaluationMetrics,
) -> dict[str, dict[str, int | float | list[float] | None]]:
    return {
        "stale_recall": _metric_value(metrics.stale_recall),
        "stale_precision": _metric_value(metrics.stale_precision),
        "specificity": _metric_value(metrics.specificity),
        "unnecessary_revalidation_rate": _metric_value(metrics.unnecessary_revalidation_rate),
        "missed_semantic_change_rate": _metric_value(metrics.missed_semantic_change_rate),
        "overall_accuracy": _metric_value(metrics.overall_accuracy),
    }


def _metric_value(metric: RateMetric) -> dict[str, int | float | list[float] | None]:
    return {
        "count": metric.count,
        "denominator": metric.denominator,
        "rate": metric.rate,
        "wilson_95": list(metric.wilson_interval) if metric.wilson_interval is not None else None,
    }


def _retrieval_metric_mapping(
    metrics: RetrievalEvaluationMetrics,
) -> dict[str, object]:
    return {
        "recall": _metric_value(metrics.recall),
        "exclusion_rate": _metric_value(metrics.exclusion_rate),
        "precision": _metric_value(metrics.precision),
        "overall_accuracy": _metric_value(metrics.overall_accuracy),
        "without_terms_overall_accuracy": _metric_value(metrics.without_terms_overall_accuracy),
        "term_baseline_recall": _metric_value(metrics.term_baseline_recall),
        "term_assisted_recall": _metric_value(metrics.term_assisted_recall),
        "term_baseline_exclusion_rate": _metric_value(metrics.term_baseline_exclusion_rate),
        "term_assisted_exclusion_rate": _metric_value(metrics.term_assisted_exclusion_rate),
        "term_baseline_precision": _metric_value(metrics.term_baseline_precision),
        "term_assisted_precision": _metric_value(metrics.term_assisted_precision),
        "term_net_gain": metrics.term_net_gain,
    }


def _assert_mapping(
    value: object,
    expected: Mapping[str, object],
    name: str,
) -> None:
    if not isinstance(value, dict) or value != expected:
        raise RepositoryCorpusError(f"repository baseline {name} differs")


def _required_string(data: dict[object, object], field: str, identifier: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise RepositoryCorpusError(f"{identifier}: {field} is required")
    return value


def _sources(value: object, identifier: str, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise RepositoryCorpusError(f"{identifier}: {field} must contain source files")
    sources: dict[str, str] = {}
    for path, content in value.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise RepositoryCorpusError(f"{identifier}: {field} sources must map paths to text")
        _relative_path(path, identifier)
        sources[path] = content
    return sources


def _capture_definition(value: object, identifier: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RepositoryCorpusError(f"{identifier}: capture must be an object")
    capture = cast(dict[object, object], value)
    for field in ("kind", "claim", "durability_reason"):
        _required_string(capture, field, identifier)
    evidence = capture.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise RepositoryCorpusError(f"{identifier}: capture evidence must be a non-empty list")
    if not all(isinstance(item, dict) for item in evidence):
        raise RepositoryCorpusError(f"{identifier}: capture evidence items must be objects")
    return {str(key): item for key, item in capture.items() if isinstance(key, str)}


def _retrieval_distractors(
    value: object,
) -> tuple[dict[str, str], tuple[dict[str, object], ...]]:
    if value is None:
        return {}, ()
    if not isinstance(value, dict):
        raise RepositoryCorpusError("retrieval_distractors must be an object")
    files = _sources(value.get("files"), "retrieval_distractors", "files")
    raw_captures = value.get("captures")
    if not isinstance(raw_captures, list) or not raw_captures:
        raise RepositoryCorpusError("retrieval_distractors captures must be a non-empty list")
    captures = tuple(
        _capture_definition(item, f"retrieval_distractors[{index}]")
        for index, item in enumerate(raw_captures)
    )
    claims = [str(capture["claim"]) for capture in captures]
    if len(set(claims)) != len(claims):
        raise RepositoryCorpusError("retrieval_distractor claims must be distinct")
    return files, captures


def _stale_reasons(value: object, identifier: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise RepositoryCorpusError(f"{identifier}: expected_stale_reasons must be a non-empty map")
    reasons: dict[str, str] = {}
    for key, reason in value.items():
        if not isinstance(key, str) or not isinstance(reason, str):
            raise RepositoryCorpusError(
                f"{identifier}: expected_stale_reasons must map text to text"
            )
        reasons[key] = reason
    return reasons


def _relative_path(path: str, identifier: str) -> Path:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or path in {"", "."}:
        raise RepositoryCorpusError(f"{identifier}: source path must be a relative file path")
    return Path(*candidate.parts)


def _replace_sources(root: Path, sources: dict[str, str], managed_paths: set[str]) -> None:
    for path in managed_paths - set(sources):
        (root / _relative_path(path, "repository")).unlink(missing_ok=True)
    for path, content in sources.items():
        target = root / _relative_path(path, "repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _sources_with_distractors(sources: dict[str, str], trial: RepositoryTrial) -> dict[str, str]:
    return {**sources, **trial.distractor_files}


def _git(repository: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=repository, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")


def _hook(
    runtime_root: Path,
    repository: Path,
    event: str,
    turn_id: str,
    prompt: str | None = None,
) -> dict[str, object] | str:
    scripts = {
        "UserPromptSubmit": "user_prompt_submit.py",
        "PostToolUse": "post_tool_use.py",
        "Stop": "stop.py",
    }
    environment = os.environ.copy()
    environment.update(
        {
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(runtime_root / ".venv"),
        }
    )
    payload: dict[str, object] = {"turn_id": turn_id, "cwd": str(repository)}
    if prompt is not None:
        payload["prompt"] = prompt
    result = subprocess.run(
        [
            "sh",
            str(runtime_root / "scripts" / "run-python.sh"),
            str(runtime_root / "hooks" / scripts[event]),
        ],
        cwd=repository,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return result.stderr.strip() or "hook process failed"
    try:
        output = cast(dict[str, object], json.loads(result.stdout))
    except json.JSONDecodeError:
        return "hook did not return JSON"
    message = output.get("systemMessage")
    if isinstance(message, str) and (" failed:" in message or " is inactive:" in message):
        return message
    return output


def _capture(runtime_root: Path, repository: Path, arguments: dict[str, object]) -> str | None:
    environment = os.environ.copy()
    environment.update(
        {
            "MEMORY_STALE_SKIP_SYNC": "1",
            "MEMORY_STALE_PROJECT_ENVIRONMENT": str(runtime_root / ".venv"),
        }
    )
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "memory.capture", "arguments": arguments},
    }
    result = subprocess.run(
        ["sh", str(runtime_root / "scripts" / "run-python.sh"), "-m", "memory_stale.mcp_server"],
        cwd=repository,
        env=environment,
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return result.stderr.strip() or "MCP process failed"
    try:
        response = cast(dict[str, object], json.loads(result.stdout))
        tool_result = cast(dict[str, object], response["result"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return "MCP process returned an invalid response"
    if tool_result.get("isError") is True:
        content = tool_result.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                return text
        return "memory.capture returned an error"
    return None


def _memory_status(repository: Path, claim: str) -> str | None:
    status, _reasons = _memory_observation(repository, claim)
    return status


def _memory_observation(repository: Path, claim: str) -> tuple[str | None, dict[str, str] | None]:
    directory = repository / ".agents" / "skills" / ".agent-memory" / "memories"
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[2].strip() != claim:
            continue
        data = yaml.safe_load(parts[1])
        if isinstance(data, dict):
            extension = data.get("memory_stale")
            observation = extension if isinstance(extension, dict) else data
            status = observation.get("status")
            if isinstance(status, str):
                raw_reasons = observation.get("stale_reasons")
                if raw_reasons is None:
                    return status, None
                if isinstance(raw_reasons, dict) and all(
                    isinstance(key, str) and isinstance(reason, str)
                    for key, reason in raw_reasons.items()
                ):
                    return status, cast(dict[str, str], raw_reasons)
                return status, None
    return None, None


def _additional_context(output: dict[str, object]) -> str:
    specific = output.get("hookSpecificOutput")
    if not isinstance(specific, dict):
        return ""
    context = specific.get("additionalContext")
    return context if isinstance(context, str) else ""


def _returned_claims(context: str) -> tuple[str, ...]:
    marker = "Memory Stale active context:\n"
    _before, separator, retrieval_context = context.partition(marker)
    if not separator:
        return ()
    return tuple(
        line.removeprefix("- ") for line in retrieval_context.splitlines() if line.startswith("- ")
    )


def _failure(trial: RepositoryTrial, kind: str, detail: str) -> OperationalOutcome:
    return OperationalOutcome(trial.identifier, kind, detail)

"""Deterministic evaluation of labeled staleness scenarios."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from memory_stale.lifecycle import RefEvidence, reconcile
from memory_stale.symbol_index import SymbolIndexer


class CorpusError(ValueError):
    """Raised when a labeled corpus cannot be evaluated safely."""


@dataclass(frozen=True)
class Scenario:
    identifier: str
    label: str
    evidence: str
    before: dict[str, str]
    after: dict[str, str]


@dataclass(frozen=True)
class ScenarioResult:
    identifier: str
    label: str
    lifecycle_status: str


@dataclass(frozen=True)
class EvaluationResult:
    scenarios: list[ScenarioResult]
    unnecessary_revalidation_rate: float
    missed_semantic_change_rate: float


def load_corpus(path: Path) -> list[Scenario]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise CorpusError("corpus version must be 1")
    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise CorpusError("corpus scenarios must be a non-empty list")
    scenarios: list[Scenario] = []
    identifiers: set[str] = set()
    for item in raw_scenarios:
        if not isinstance(item, dict):
            raise CorpusError("scenario must be an object")
        identifier = _required(item, "id", "scenario")
        if identifier in identifiers:
            raise CorpusError(f"{identifier}: duplicate id")
        identifiers.add(identifier)
        label = _required(item, "label", identifier)
        if label not in {"preserved", "changed"}:
            raise CorpusError(f"{identifier}: label must be preserved or changed")
        evidence = _required(item, "evidence", identifier)
        if ":" not in evidence:
            raise CorpusError(f"{identifier}: evidence must be a symbol locator")
        before = _sources(item.get("before"), identifier, "before")
        after = _sources(item.get("after"), identifier, "after")
        scenarios.append(Scenario(identifier, label, evidence, before, after))
    return scenarios


def _required(data: dict[object, object], field: str, identifier: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise CorpusError(f"{identifier}: {field} is required")
    return value


def _sources(value: object, identifier: str, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise CorpusError(f"{identifier}: {field} must contain source files")
    sources = {
        path: content
        for path, content in value.items()
        if isinstance(path, str) and isinstance(content, str)
    }
    if len(sources) != len(value):
        raise CorpusError(f"{identifier}: {field} sources must map paths to text")
    return sources


def _write_sources(root: Path, sources: dict[str, str]) -> None:
    for path, content in sources.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def evaluate_corpus(corpus_path: Path, fixtures_root: Path) -> EvaluationResult:
    """Run the public lifecycle with scenario labels deliberately held separate."""
    scenarios = load_corpus(corpus_path)
    fixtures_root.mkdir(parents=True, exist_ok=True)
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        root = fixtures_root / scenario.identifier
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        _write_sources(root, scenario.before)
        baseline_signature = SymbolIndexer(root).signature(scenario.evidence)
        capture: dict[str, object] = {
            "kind": "behavior",
            "claim": f"Corpus scenario {scenario.identifier}",
            "durability_reason": "Labeled evaluation fixture.",
            "evidence": [
                {
                    "type": "symbol",
                    "role": "primary",
                    "locator": scenario.evidence,
                    "fingerprint": baseline_signature,
                }
            ],
        }
        captured = reconcile([], [capture], {})
        shutil.rmtree(root)
        root.mkdir()
        _write_sources(root, scenario.after)
        current_signature = SymbolIndexer(root).signature(scenario.evidence)
        final = reconcile(
            captured,
            [],
            {f"symbol:{scenario.evidence}": RefEvidence(current_signature)},
        )
        results.append(ScenarioResult(scenario.identifier, scenario.label, final[0].status))
    ordered = sorted(results, key=lambda result: result.identifier)
    preserved = [result for result in ordered if result.label == "preserved"]
    changed = [result for result in ordered if result.label == "changed"]
    unnecessary = sum(result.lifecycle_status == "stale" for result in preserved) / len(preserved)
    missed = sum(result.lifecycle_status == "active" for result in changed) / len(changed)
    return EvaluationResult(ordered, unnecessary, missed)

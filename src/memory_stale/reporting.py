"""Project configuration and optional static HTML reporting."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import tomli

from memory_stale.lifecycle import Memory


@dataclass(frozen=True)
class Config:
    context_budget: int = 1500
    auto_report: bool = False
    report_path: Path = Path("memory-report.html")
    top_k: int = 5


class ConfigError(ValueError):
    """Raised for invalid project configuration."""


def load_config(repository: Path) -> Config:
    path = repository / ".agents" / "skills" / ".agent-memory" / "config.toml"
    if not path.is_file():
        return Config()
    with path.open("rb") as stream:
        data = cast(dict[str, object], tomli.load(stream))
    budget = data.get("context_budget", 1500)
    top_k = data.get("top_k", 5)
    auto_report = data.get("auto_report", False)
    report_text = data.get("report_path", "memory-report.html")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise ConfigError("context_budget must be a positive integer")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
        raise ConfigError("top_k must be a positive integer")
    if not isinstance(auto_report, bool):
        raise ConfigError("auto_report must be a boolean")
    if not isinstance(report_text, str) or not report_text:
        raise ConfigError("report_path must be a non-empty relative path")
    report_path = Path(report_text)
    if report_path.is_absolute() or ".." in report_path.parts:
        raise ConfigError("report_path must stay inside the repository")
    return Config(
        context_budget=budget,
        auto_report=auto_report,
        report_path=report_path,
        top_k=top_k,
    )


def _render(memories: list[Memory]) -> str:
    rows = []
    groups: dict[str, list[Memory]] = {}
    for memory in memories:
        groups.setdefault(memory.claim_id or memory.id, []).append(memory)
    for claim_id, revisions in sorted(groups.items()):
        rows.append(f'<tr class="claim"><th colspan="11">Claim {html.escape(claim_id)}</th></tr>')
        for memory in sorted(revisions, key=lambda revision: revision.id):
            evidence = "<br>".join(
                html.escape(f"{item.type} · {item.role} · {item.locator} · {item.fingerprint}")
                for item in memory.evidence
            )
            graph = "<br>".join(
                [f"supported_by: {html.escape(', '.join(memory.supported_by))}"]
                + [
                    html.escape(f"depends_on: {edge.source} → {edge.target}")
                    for edge in memory.dependencies
                ]
            )
            reasons = "<br>".join(
                f"{html.escape(ref)}: {html.escape(reason)}"
                for ref, reason in sorted((memory.stale_reasons or {}).items())
            )
            retrieval_terms = "<br>".join(html.escape(term) for term in memory.retrieval_terms)
            rows.append(
                "<tr>"
                f"<td>{html.escape(memory.id)}</td>"
                f"<td>{html.escape(memory.status)}</td>"
                f"<td>{html.escape(memory.kind)}</td>"
                f"<td>{html.escape(memory.claim)}</td>"
                f"<td>{html.escape(memory.durability_reason)}</td>"
                f"<td>{evidence}</td><td>{graph}</td><td>{retrieval_terms}</td><td>{reasons}</td>"
                f"<td>{html.escape(memory.observed_commit or '')}</td>"
                f"<td>{html.escape(memory.observed_at or '')}</td></tr>"
            )
    body = "".join(rows) or '<tr><td colspan="11">No memories.</td></tr>'
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Memory Stale</title>'
        "<style>body{font-family:system-ui;margin:2rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:.5rem;text-align:left;vertical-align:top}"
        ".claim th{background:#eee}</style>"
        "</head><body><h1>Memory Stale report</h1>"
        "<p><code>active</code> means recorded evidence is unchanged; "
        "<code>stale</code> means evidence requires revalidation. Neither state "
        "proves claim truth or falsehood.</p><table><thead><tr><th>Revision</th><th>Status</th>"
        "<th>Kind</th><th>Claim</th><th>Durability</th><th>Evidence</th><th>Graph</th>"
        "<th>Retrieval terms</th><th>Reasons</th>"
        "<th>Observed commit</th><th>Observed at</th>"
        f"</tr></thead><tbody>{body}</tbody></table></body></html>\n"
    )


def write_report(
    repository: Path, memories: list[Memory], *, requested: bool = False
) -> Path | None:
    config = load_config(repository)
    if not requested and not config.auto_report:
        return None
    path = repository / config.report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        temporary.write_text(_render(memories), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path

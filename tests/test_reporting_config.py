from pathlib import Path

import pytest

from memory_stale.evidence import EvidenceEdge, EvidenceItem
from memory_stale.lifecycle import Memory
from memory_stale.reporting import ConfigError, load_config, write_report


def test_config_defaults_overrides_and_invalid_values(tmp_path: Path) -> None:
    assert load_config(tmp_path).context_budget == 1500
    config_dir = tmp_path / ".agents" / "skills" / ".agent-memory"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        'context_budget = 700\nauto_report = true\nreport_path = "health/report.html"\n',
        encoding="utf-8",
    )
    loaded = load_config(tmp_path)
    assert (loaded.context_budget, loaded.auto_report, loaded.report_path) == (
        700,
        True,
        Path("health/report.html"),
    )
    (config_dir / "config.toml").write_text("context_budget = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="context_budget"):
        load_config(tmp_path)


def test_html_report_escapes_content_and_is_explicit_by_default(tmp_path: Path) -> None:
    memory = Memory(
        "one",
        "behavior",
        "stale",
        "Use <safe> output.",
        "Avoid & bugs.",
        (EvidenceItem("symbol", "primary", "web.py:render", "sig"),),
        {"symbol:web.py:render": "changed via symbol:web.py:render -> symbol:policy.py:rule"},
        supported_by=("symbol:web.py:render",),
        dependencies=(EvidenceEdge("symbol:web.py:render", "symbol:policy.py:rule"),),
    )
    assert write_report(tmp_path, [memory], requested=False) is None
    path = write_report(tmp_path, [memory], requested=True)
    assert path == tmp_path / "memory-report.html"
    html = path.read_text(encoding="utf-8")
    assert "Use &lt;safe&gt; output." in html
    assert "Avoid &amp; bugs." in html
    assert "web.py:render" in html and "changed" in html
    assert "Graph" in html and "depends_on: symbol:web.py:render → symbol:policy.py:rule" in html
    assert "Claim one" in html
    assert "Observed commit" in html

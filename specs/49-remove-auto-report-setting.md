# 49 — Remove the inert `auto_report` setting

## Problem Statement

[Spec 29](29-explicit-html-report-generation.md) made the HTML health report
explicit: `Stop` never writes it, even when `auto_report = true`. The setting
survived anyway. The installer still writes `auto_report = false` with a
comment claiming the report is generated after each completed turn, and
`load_config` still parses and validates the key. A project owner reading the
installed configuration is told about a behavior that does not exist, and a
non-boolean value is rejected for a setting that does nothing.

## Solution

Remove `auto_report` from the product. The installer no longer writes it, and
configuration loading no longer reads or validates it. A legacy
`auto_report` entry in an existing `config.toml` is ignored, whatever its
value, so existing installations keep working without edits. The report is
generated only through the `memory.report` MCP tool, as before.

## User Stories

1. As a project owner, I want the installed configuration to list only
   settings that have an effect, so that I am not misled about automatic
   reports.
2. As a project owner with an older installation, I want a leftover
   `auto_report` line to be ignored, so that my configuration keeps loading.

## Implementation Decisions

- Public seams: the project installer (`install_project.install`), which
  writes the default `config.toml`, and `memory_stale.reporting.load_config`.
- `DEFAULT_MEMORY_CONFIG` drops the `auto_report` key and its comment.
- `Config` drops the `auto_report` field; `load_config` stops reading it.
- `write_report` writes only when explicitly requested; the
  `requested=False` path returns `None`, matching spec 29.

## Testing Decisions

- Slice 1: install into a temporary Git repository and assert the written
  `config.toml` contains no `auto_report` key.
- Slice 2: a `config.toml` with `auto_report = "yes"` loads without
  `ConfigError` and keeps the other configured values.
- The existing end-to-end test proving `Stop` writes no report while a
  legacy `auto_report = true` is present stays unchanged.

## Out of Scope

- Any automatic report generation.
- Rewriting existing `config.toml` files to delete the legacy key.
- README changes: the README already omits the key.

# 07 — Configuration and HTML report

## Problem Statement

Users need to control the context budget and reporting without generating noise on every task.

## Solution

Read project configuration and generate HTML only on request or when automatic reporting is enabled.

## User Stories

1. As a user, I want to adjust the context budget per project.
2. As a user, I want to request a memory health report.
3. As a user, I want to opt into generating a report automatically after changes.

## Implementation Decisions

- Configuration lives at `<repo>/.agents/skills/.agent-memory/config.toml`.
- The default retrieval budget is 1,500 tokens.
- Reporting is explicit by default; automatic reporting is a configuration option.
- HTML shows active and stale memories, refs, and reasons; it is not the primary interface.

## Testing Decisions

- Seam confirmed by continuous authorization: configuration is loaded by the public function from the repository root, and the report is observed in the final HTML file, including the explicit or automatic generation decision.
- Test defaults, valid and invalid overrides, and missing configuration.
- Test HTML with an empty corpus, active and stale memories, and escaped characters.
- Test that no report is produced without a request or configuration.

## Out of Scope

- A served dashboard, reactive frontend, or remote metric delivery.

## Further Notes

- The HTML file location will be configurable.

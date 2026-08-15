---
name: memory-stale
description: Maintain deterministic, code-anchored project memory through the bundled Codex lifecycle hooks.
---

# Memory Stale

Memory Stale runs automatically during Codex turns. An injected `active` memory
means only that its recorded evidence still matches the capture; it does not
prove claim truth or complete provenance. A `stale` memory requires
revalidation because evidence changed, disappeared, or could not be resolved;
it does not prove the claim false. Treat active memories as project context,
while continuing to verify claims against the current code before making
changes.

The project-local installation requires a Git working tree. If a hook reports that Memory Stale is
inactive or encountered an error, continue the user's task normally and surface
the actionable message without treating memory maintenance as a blocker.

At `Stop`, Memory Stale automatically captures every added or semantically
changed resolvable symbol in a supported source file. When a semantic change
cannot be attributed to a named symbol, it uses a source-file record instead.
Do not ask the user to call `memory.capture`, and do not need to call it merely
to record ordinary code changes. Configuration, Markdown, unsupported
languages, comments, and formatting-only edits do not produce automatic
records.

Automatic records are deterministic provenance, not semantic summaries. A
record such as `added symbol app/main.py:version` does not establish the
symbol's purpose, behavior, design rationale, or user-facing contract. When a
completed change establishes any durable code-backed fact, call
`memory.capture` with a precise claim and appropriate evidence.

When the user invokes `/memory-stale dream`, call the local `memory.dream` MCP
tool. Review only the stale or broken items it reports. Use `memory.capture` for
new durable facts supported by code; never rewrite a healthy active memory
without verifiable evidence. Report created memories, newly stale memories, and
errors at the end of the same flow.

When revalidation establishes the same claim with changed code evidence, capture
it again. The engine preserves the prior evidence revision for audit and exposes
only the new active revision in ordinary context. Repeating an identical
revision is safe and idempotent.

When adding a richer explicit claim, provide an `evidence` array rather than legacy `refs`. Every
item has `type`, `role`, and `locator`. Use at least one changed `primary` item;
unchanged `supporting` items are permitted but must resolve. Supported types are
`symbol`, `test`, `config`, and `schema`. Symbol and test locators use
`path:symbol`; config and schema locators use an exact JSON Pointer such as
`settings.yaml#/authentication/mfa`. Do not use whole-file evidence in an
explicit MCP capture or invent a fallback when an item cannot resolve.

When one evidence item depends on another, declare it in that item's nested
`depends_on` array. A dependency uses the same typed locator and is stored as
supporting evidence. A string dependency reference may target an already
declared `type:locator` node when a cycle must be represented. Do not infer
relationships from imports or call sites. Explain the deterministic invalidation
path returned by Dream or the report when a transitive node becomes stale.

When the user asks for the memory health report, call `memory.report` and return
the generated local path. Do not generate the report on ordinary turns.

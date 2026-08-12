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

The plugin requires a Git working tree. If a hook reports that Memory Stale is
inactive or encountered an error, continue the user's task normally and surface
the actionable message without treating memory maintenance as a blocker.

When the user invokes `/memory-stale dream`, call the local `memory.dream` MCP
tool. Review only the stale or broken items it reports. Use `memory.capture` for
new durable facts supported by code; never rewrite a healthy active memory
without verifiable evidence. Report created memories, newly stale memories, and
errors at the end of the same flow.

When revalidation establishes the same claim with changed code evidence, capture
it again. The engine preserves the prior evidence revision for audit and exposes
only the new active revision in ordinary context. Repeating an identical
revision is safe and idempotent.

When capturing, provide an `evidence` array rather than legacy `refs`. Every
item has `type`, `role`, and `locator`. Use at least one changed `primary` item;
unchanged `supporting` items are permitted but must resolve. Supported types are
`symbol`, `test`, `config`, and `schema`. Symbol and test locators use
`path:symbol`; config and schema locators use an exact JSON Pointer such as
`settings.yaml#/authentication/mfa`. Do not use whole-file evidence or invent a
fallback when an item cannot resolve.

When the user asks for the memory health report, call `memory.report` and return
the generated local path. Do not generate the report on ordinary turns unless
project configuration enables automatic reporting.

---
name: memory-stale
description: Maintain deterministic, code-anchored project memory through the bundled Codex lifecycle hooks.
---

# Memory Stale

Memory Stale runs automatically during Codex turns. Treat its injected active
memories as project context, while continuing to verify claims against the
current code before making changes.

The plugin requires a Git working tree. If a hook reports that Memory Stale is
inactive or encountered an error, continue the user's task normally and surface
the actionable message without treating memory maintenance as a blocker.

When the user invokes `/memory-stale dream`, call the local `memory.dream` MCP
tool. Review only the stale or broken items it reports. Use `memory.capture` for
new durable facts supported by code; never rewrite a healthy active memory
without verifiable evidence. Report created memories, newly stale memories, and
errors at the end of the same flow.

When the user asks for the memory health report, call `memory.report` and return
the generated local path. Do not generate the report on ordinary turns unless
project configuration enables automatic reporting.

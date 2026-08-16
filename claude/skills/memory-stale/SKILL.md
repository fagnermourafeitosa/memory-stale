---
name: memory-stale
description: Maintain deterministic, code-anchored project memory through Memory Stale lifecycle hooks and MCP tools.
---

# Memory Stale

Memory Stale runs automatically during Claude Code turns. Active memory means its recorded evidence still matches the capture; stale memory must be revalidated because its evidence changed, disappeared, or no longer resolves.

When a task changes supported code, call `memory.capture` before the final response once per coherent change. The claim must describe what the resulting implementation does or guarantees, and evidence must cover every relevant changed location. Automatic provenance recorded at Stop does not replace this semantic capture.

Use typed `evidence` with a changed primary item. Supported explicit types are `symbol`, `test`, `config`, and `schema`; do not use source-file evidence for an explicit capture. Call `memory.dream` only for `/memory-stale dream`, and call `memory.report` only when the user asks for the health report.

If a hook reports a memory-maintenance problem, continue the user's coding work and surface the actionable message; Memory Stale must not block the task.

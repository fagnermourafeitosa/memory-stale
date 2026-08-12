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

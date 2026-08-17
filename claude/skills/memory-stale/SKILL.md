---
name: memory-stale
description: Maintain deterministic, code-anchored project memory through Memory Stale lifecycle hooks and MCP tools.
---

# Memory Stale

Memory Stale runs automatically during Claude Code turns. Active memory means its recorded evidence still matches the capture; stale memory must be revalidated because its evidence changed, disappeared, or no longer resolves.

Write semantic memory in the same natural language as the user's prompt. Do
not translate semantic memory to English or default to English. The claim,
durability reason, and retrieval terms must use that prompt language so the
lexical retriever compares text in the language that originated the memory.
For mixed-language prompts, use the main user-facing language and preserve
technical identifiers, paths, symbols, and version strings as written. If the
prompt has no natural-language prose, use English as the stable fallback.

Each prompt injects at most the project's configured `top_k` active memories
(five when omitted), selected by deterministic retrieval ranking before the
token budget is applied.

When a task changes supported code, call `memory.capture` before the final response once per coherent change. The claim must describe what the resulting implementation does or guarantees, and evidence must cover every relevant changed location. Automatic provenance recorded at Stop does not replace this semantic capture.

Use typed `evidence` with a changed primary item. Supported explicit types are `symbol`, `test`, `config`, and `schema`; do not use source-file evidence for an explicit capture. Call `memory.dream` only for `/memory-stale dream`, and call `memory.report` only when the user asks for the health report.

Optionally add up to eight short `retrieval_terms` to a semantic capture when
later work may use durable product wording that neither the claim nor locator
spells. You choose these literal terms while writing the claim; Memory Stale
does not infer entities or synonyms. For example:

```json
{
  "claim": "Login verifies a second factor before granting access.",
  "retrieval_terms": ["MFA", "second-factor authentication"]
}
```

Terms support lexical retrieval only. They are not evidence and cannot make a
stale revision active. Prefer vocabulary specific enough not to describe
unrelated memories. A later prompt must also match the claim or an evidence
locator; a term alone cannot inject the memory.

If a hook reports a memory-maintenance problem, continue the user's coding work and surface the actionable message; Memory Stale must not block the task.

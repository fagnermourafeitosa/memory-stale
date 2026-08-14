# 02 — Local `memory.capture` MCP tool

## Problem Statement

The hook knows which symbols changed but not the final meaning of the change. Codex itself must provide a structured claim without another LLM.

## Solution

Provide a local `memory.capture` MCP tool through which Codex records a memory candidate during the task itself.

## User Stories

1. As Codex, I want to send a structured final decision to the local integration.
2. As a maintainer, I want to reject claims without evidence in changed code.
3. As a user, I want the initial request and diff summary not to become memory.

## Implementation Decisions

- The local MCP server uses stdio JSON-RPC transport. Its Codex CLI registration
  points to the target project's installed runtime; the process uses the
  current Git repository and the single active turn to locate its ephemeral
  ledger. This discovery detail is superseded by spec 26.
- Required input: `kind`, `claim`, `refs`, and `durability_reason`.
- `kind`: `behavior`, `contract`, `constraint`, `architecture`, or `operation`.
- The skill requires a checklist: durable behavior, real risk of future error, evidence in the final code, and more than task history.
- Each ref must resolve and must have changed during the current task.
- Repetition with the same kind, normalized claim, and refs is idempotent.
- A valid candidate becomes available to `Stop`; the MCP tool does not write final memory by itself.

## Testing Decisions

- Seam confirmed by continuous execution authorization: start the real MCP server, negotiate JSON-RPC over stdio, and call `memory.capture` in temporary Git repositories whose turn was started by the hooks.
- Test the required schema, closed enum, missing or unchanged refs, and idempotent repetition.
- Test that a valid capture does not persist memory before the lifecycle runs.

## Out of Scope

- Claim generation by an external model or semantic deduplication.

## Further Notes

- The skill guides Codex; MCP validates the structural contract.

---
type: Memory Stale Claim
title: GET /api/teams/germany/defenders returns exactly two German defenders in
  the defenders JSON field, enforced by a fixed-cardinality response schema and
  a regression test.
description: This is the endpoint's public response contract and must remain synchronized
  with its schema, implementation, and regression test.
sources:
  - id: symbol:app/api/teams.py:GermanDefendersResponse
    resource: app/api/teams.py:GermanDefendersResponse
  - id: symbol:app/api/teams.py:german_defenders
    resource: app/api/teams.py:german_defenders
  - id: test:tests/api/test_teams.py:test_german_defenders_returns_two_players
    resource: tests/api/test_teams.py:test_german_defenders_returns_two_players
generated:
  by: process:memory-stale
  at: '2026-08-17T01:16:59.552400+00:00'
verified:
  - by: process:memory-stale
    at: '2026-08-17T01:16:59.552400+00:00'
status: stable
memory_stale:
  schema_version: 5
  claim_id: a21a51563b6b770cacdc
  revision_id: 4d269f796c036c55e80f
  kind: contract
  status: active
  durability_reason: This is the endpoint's public response contract and must remain
    synchronized with its schema, implementation, and regression test.
  evidence:
    - source_id: symbol:app/api/teams.py:GermanDefendersResponse
      type: symbol
      role: primary
      fingerprint: v2:30e84aa1ccaf5b5cd4059e08ad7412d4862d8be623dc93b3d6833f97045748b5
    - source_id: symbol:app/api/teams.py:german_defenders
      type: symbol
      role: primary
      fingerprint: v2:6cccdeeb8c75a1618a0fce7a989917c3ab98070e55bb3d994b8aec6592a8961a
    - source_id: test:tests/api/test_teams.py:test_german_defenders_returns_two_players
      type: test
      role: primary
      fingerprint: v2:b1ced6520e69ba03cf85f7d50382328d6035c843ac8e1c9f0f367a02520c2335
  supported_by:
    - symbol:app/api/teams.py:GermanDefendersResponse
    - symbol:app/api/teams.py:german_defenders
    - test:tests/api/test_teams.py:test_german_defenders_returns_two_players
  dependencies: []
  stale_reasons: null
  observed_commit: f281852e627e38dfe2a210ebea5638e00b2623d4
  observed_at: '2026-08-17T01:16:59.552400+00:00'
  legacy_id: null
---

GET /api/teams/germany/defenders returns exactly two German defenders in the defenders JSON field, enforced by a fixed-cardinality response schema and a regression test.

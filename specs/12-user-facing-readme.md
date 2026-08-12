# 12 — User-facing README

## Problem Statement

The README describes the architecture well but does not provide a clear adoption
journey. It lacks prerequisites, local installation, first use, complete
configuration, and a simple way to verify that retrieval and staleness work.
Some descriptions also diverge from the implemented product.

## Solution

Reorganize the README as a public product page: begin with the user outcome,
present a short example, explain installation and normal use, and move internal
details later. Correct the contract for hooks and the three MCP tools, and
separate delivered features from the future roadmap.

## User Stories

1. As a user, I want to understand the plugin's value quickly and install it without knowing its internal architecture.
2. As a user, I want to know where memory lives, what I should version, and how to verify retrieval and staleness.
3. As an advanced user, I want to configure the budget and report with copyable examples.
4. As a potential contributor, I want to distinguish current state, limitations, and actual future work.

## Observable Test Seam

The highest seam is the rendered `README.md` itself as the public contract.
Review verifies that commands, paths, configuration, languages, hooks, MCP tools,
states, and defaults match the current manifests and code.

## Expected Behavior

- The value proposition and automatic flow are clear before implementation details.
- Prerequisites and local installation do not promise a public distribution that does not yet exist.
- The README includes first use, verification, configuration, and versioning.
- The three MCP tools and the split between Codex judgment and deterministic validation are described correctly.
- The roadmap contains only work that has not been delivered.

## Implementation Constraints

- Keep the README in English, matching the existing public documentation.
- Do not introduce a human-facing CLI as the primary surface.
- Do not promise a public release, file fallback, embeddings, or another LLM.
- Do not invent marketplace commands that depend on a nonexistent publication.
- Preserve Git, `uv`, local storage, and language limitations.

## Testing Decisions

- Documentation-only change: do not fabricate a red-green test.
- Check links, headings, TOML examples, paths, tool names, and defaults through textual search and comparison with code.
- Run `ruff format --check`, `ruff check`, mypy, and pytest to ensure the documentation does not accompany accidental production changes.

## Out of Scope

- Publishing a marketplace package or release.
- Changing the manifest, runtime, configuration, ranking, or lifecycle.
- Creating a site, screenshots, video, or external documentation.

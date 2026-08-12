# 19 — English repository contracts

## Problem Statement

The repository's public documentation and code are written for an international
audience, but `AGENTS.md` and most numbered specs are written partly or entirely
in Portuguese. Mixed-language governance makes contribution rules harder to
scan, creates inconsistent terminology, and limits reuse by contributors and
agents that operate primarily in English.

## Solution

Translate `AGENTS.md` and every numbered spec into clear technical English while
preserving their requirements, numbering, observable seams, scope boundaries,
and authorization rules. Establish English as the required language for future
repository instructions and specs.

## User Stories

1. As an international contributor, I want repository instructions in English, so that I can follow the workflow without translation.
2. As an agent, I want every spec to use one language consistently, so that domain terms and constraints remain unambiguous.
3. As a maintainer, I want translations to preserve the existing contracts, so that a language change does not silently alter behavior.
4. As a reviewer, I want spec numbering and structure preserved, so that history and cross-references remain stable.
5. As a maintainer, I want future specs written in English, so that the repository does not return to mixed-language governance.
6. As a contributor, I want code identifiers and product vocabulary preserved where appropriate, so that translated prose still matches the implementation.

## Implementation Decisions

- `AGENTS.md` and all numbered specs will use English for headings and prose.
- Existing spec numbers, filenames, decisions, testing seams, and out-of-scope boundaries will remain unchanged.
- Translation may improve grammar and terminology but will not add, remove, or weaken product behavior.
- Code identifiers, commands, paths, state names, MCP tool names, and established product terms remain literal.
- `AGENTS.md` will explicitly state that repository instructions and specs must be written in English.
- New specs created during this change, including this spec, will already comply with the English-only rule.
- README translation is not required because it is already written in English.

## Testing Decisions

- Highest observable seam confirmed: human-readable repository instructions and numbered implementation contracts.
- This is a documentation-only change; no artificial failing production test will be created.
- Review will confirm that every numbered spec retains its existing contract structure and that no Portuguese contract prose remains.
- Cross-references, commands, identifiers, and numbered ordering will be checked mechanically where practical.
- The repository's full quality gates will run before the documentation change is considered complete.

## Out of Scope

- Changing plugin behavior or public interfaces.
- Renumbering specs or renaming existing spec files solely to translate filenames.
- Translating code identifiers, commands, paths, or product names.
- Rewriting the README or changing its product positioning.
- Publishing, pushing, tagging, or opening a pull request.

## Further Notes

- This spec governs the language of future specs as a repository workflow rule.

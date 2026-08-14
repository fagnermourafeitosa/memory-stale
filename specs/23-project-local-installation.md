# 23 — Project-local installation without Codex Plugins

**Status: Superseded in part by spec 26 (2026-08-13)**

Spec 26 supersedes every requirement here that keeps MCP discovery in the
target `.mcp.json` or forbids the Codex CLI's global MCP registration. The
skill, hooks, Python runtime, durable memory, and task state remain
project-local; the global entry is discovery metadata that points to the
installed project runtime.

## Problem Statement

Memory Stale is currently distributed as a Codex Plugin. Its manifest controls
skill discovery, MCP registration, hook discovery, runtime paths, and writable
plugin data. A user must install the plugin through a global marketplace-style
configuration, which makes activation machine-wide and couples the product to
the Codex Plugin mechanism.

Users need Memory Stale to be an explicit, reviewable project capability. A
repository that contains the installed artifacts must run Memory Stale; a
repository that does not contain them must not. Installation must not change
`~/.codex`, require a global installation, or duplicate the Python engine.

## Solution

Make this repository an install source for a project-local Codex skill with its
associated hooks, MCP registration, and one bundled Python runtime. A documented
installer copies the required artifacts into a target Git repository and merges
the local Codex configuration without modifying global Codex state.

The installed layout is deliberately small and project-scoped:

```text
<target>/.agents/skills/memory-stale/
├── SKILL.md
├── hooks/
├── scripts/
├── src/memory_stale/
├── pyproject.toml
└── uv.lock

<target>/.codex/hooks.json
<target>/.mcp.json
<target>/.git/memory-stale/runtime/
```

The target-local hook configuration invokes the copied scripts. The copied
bootstrap discovers its own installed root and writes its virtual environment,
uv cache, and grammar cache below the target repository's Git directory. The
target-local MCP configuration starts the same bootstrap and therefore imports
the same copied Python package. No artifact refers to `PLUGIN_ROOT`,
`PLUGIN_DATA`, a personal marketplace, or a plugin manifest.

## User Stories

1. As a project owner, I want to install Memory Stale by providing its source
   repository to Codex, so that the project gains memory maintenance without a
   Codex Plugin installation.
2. As a project owner, I want all activation artifacts committed or reviewable
   in my project, so that adopting Memory Stale is an explicit repository
   decision.
3. As a project owner, I want an unrelated repository to remain unaffected, so
   that Memory Stale is never implicitly enabled globally.
4. As a Codex user, I want the existing `memory-stale` skill to remain the
   primary interface, so that normal memory behavior and the Dream workflow are
   unchanged.
5. As a Codex user, I want the three lifecycle hooks to continue loading
   context, recording writes, and reconciling memory, so that project-local
   installation preserves automatic behavior.
6. As a Codex user, I want `memory.capture`, `memory.dream`, and
   `memory.report` to remain available, so that the skill can keep its current
   structured operations.
7. As a maintainer, I want hooks and MCP to use one copied runtime, so that
   changes to the deterministic engine are never duplicated between adapters.
8. As a project owner, I want existing `.codex/hooks.json` and `.mcp.json`
   entries preserved, so that installation composes with existing local Codex
   integrations.
9. As a project owner, I want a name collision to fail with an actionable
   message, so that installation never silently replaces another MCP server.
10. As a user, I want first-run Python dependencies and caches isolated inside
    the target repository's Git metadata, so that no global Python environment
    or Codex configuration is required.
11. As a user, I want failure outside a Git worktree to remain non-blocking, so
    that the existing lifecycle failure contract is preserved.
12. As a reviewer, I want the repository to contain no plugin manifest or
    plugin-oriented public instructions, so that the product boundary is clear.
13. As a future Codex user, I want a concise documented prompt and installer
    command, so that Codex can install the local integration from the public
    repository URL.

## Implementation Decisions

### Confirmed test seam

The highest observable seam is a real installation into a fresh temporary Git
repository followed by execution of the hook commands registered in the target
repository's `.codex/hooks.json` and a real stdio MCP process registered in the
target repository's `.mcp.json`. The test observes only target files, hook JSON,
MCP responses, and the target Git directory's local runtime state.

This seam matches the requested end-to-end target-project flow: source artifacts
are copied, local Codex configuration is registered, a turn begins, a capture
is sent through MCP, and the Stop hook persists an active memory. Existing unit
and lifecycle tests remain supporting coverage rather than a replacement for
this installation seam.

### Distribution boundary

- Delete `.codex-plugin/plugin.json`; do not replace it with any plugin
  manifest, marketplace metadata, cachebuster, or global registration.
- Keep `skills/memory-stale/SKILL.md` as the canonical Codex-facing interface.
- Keep the deterministic Python package independent from Codex transport. Hook
  files and the MCP server remain thin adapters around the existing core.
- Add a narrow installer as a distribution helper, not as a user-facing memory
  command or alternative product surface.
- The installer receives a target repository path, requires that it be a Git
  worktree, and copies one canonical runtime into the target skill directory.
- The installer preserves unrelated local configuration, rejects malformed JSON
  and conflicting `memory-stale` MCP registrations, and makes all new or
  changed configuration deterministic and reviewable.
- The installed bootstrap derives the installed skill root from its own path;
  it derives cache paths from the current target Git worktree. It must not read
  or write global Codex or Python configuration.

### Codex integration boundary

- The target `.codex/hooks.json` registers `UserPromptSubmit`, `PostToolUse`,
  and `Stop` commands that invoke the copied bootstrap and existing hook
  adapters. Existing matchers, timeouts, status messages, and non-blocking JSON
  contracts are retained.
- The target `.mcp.json` registers a local stdio `memory-stale` server that
  invokes the same bootstrap and `memory_stale.mcp_server` module. MCP remains
  required because the skill invokes its tools for capture, Dream, and reports.
- Relative integration commands are resolved from the target repository root;
  the bootstrap itself does not assume the source repository's location.
- The runtime's virtual environment, uv cache, and tree-sitter cache live below
  `.git/memory-stale/runtime` in the target repository. Durable memory continues
  to live below `.agents/skills/.agent-memory`, and turn state continues to live
  below `.git/memory-stale/tasks`.

### Documentation and terminology

- Update the public README, project instructions, current architecture diagrams,
  scripts, test names, and active specifications to use project-local skill
  terminology rather than plugin terminology.
- Historical implementation context may be retained only when it explains a
  migration decision; it must not prescribe Plugin installation.
- Document the intended natural-language installation request and the
  corresponding safe installer invocation. Do not claim automated remote clone
  behavior from the runtime itself.
- Make the README a concise product entry point: lead with the user outcome,
  installation, and ordinary use; move implementation detail behind compact
  sections; and avoid historical migration narrative in the public journey.
- Include two Mermaid flow diagrams: one for discovery/classification before
  context injection and one for candidate creation, validation, and persistence.
  They must distinguish Codex's semantic judgment from deterministic local
  evidence validation, and show stale memories are excluded rather than silently
  repaired.

## Testing Decisions

- First red-green slice: a fresh target Git repository installs from a copied
  source tree, obtains `.agents/skills/memory-stale`, `.codex/hooks.json`, and
  `.mcp.json`, then runs the registered prompt hook without plugin environment
  variables. The test must initially fail because the installer does not exist.
- Second slice: the installed MCP command performs `memory.capture` for an
  active turn, and the installed Stop hook writes an active target memory. This
  proves skill-facing MCP and hooks share the installed runtime.
- Test installation alongside unrelated existing hook and MCP configuration;
  assert those entries are preserved. Test an existing incompatible
  `memory-stale` MCP entry fails without changing it.
- Test first-run bootstrap creates the virtual environment and caches under the
  target `.git/memory-stale/runtime` directory, never in the source tree,
  home directory, or a plugin data directory.
- Continue executing existing lifecycle, MCP, retrieval, parser, and evaluator
  suites. Rename harness vocabulary where needed without weakening assertions.
- Validate rendered Markdown structure and Mermaid syntax through direct review;
  documentation-only work does not require a fabricated red test.
- Before completion run format check, lint, strict mypy, and the full test suite
  required by the repository contract.

## Out of Scope

- Installing, changing, or deleting anything in `~/.codex` or any global Codex
  marketplace configuration.
- Publishing a package, pushing, committing, tagging, or opening a pull
  request.
- A remote installer that downloads code itself; Codex may clone the supplied
  source URL and invoke the bundled local installer.
- Changing the deterministic memory model, supported grammars, evidence schema,
  lifecycle semantics, or retrieval policy.
- Replacing the MCP protocol with natural-language parsing or another LLM.

## Further Notes

The `to-spec` workflow requests issue-tracker publication with a
`ready-for-agent` label. No issue tracker or matching label configuration is
available in this repository, and the user authorized only local repository
work. Publication is therefore intentionally deferred.

The completed implementation removes the plugin manifest and source-level
plugin configuration, installs one runtime beneath the target local skill,
merges the target's hook and MCP configuration without global writes, and
validates both the normal lifecycle and configuration-conflict behavior through
temporary Git repositories.

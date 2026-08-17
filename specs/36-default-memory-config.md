# 36 — Default durable memory configuration on installation

## Problem Statement

Installing Memory Stale leaves its optional configuration implicit. Project
owners can use the built-in defaults, but cannot discover the available
settings or review them in the installed project without consulting the
runtime source. The durable memory directory is also not present until a
memory is captured, which makes the installed project layout less explicit.

## Solution

Create a default `config.toml` in the project-local durable memory directory
during the first installation. The file records the same configuration values
the runtime currently uses when configuration is absent. It documents that the
HTML health report remains opt-in and is not generated automatically.

## User Stories

1. As a project owner, I want a newly installed Memory Stale project to contain
   an explicit default configuration, so that I can discover and review its
   settings locally.
2. As a project owner, I want the default retrieval budget recorded in the
   installed project, so that I can adjust project context size without
   inspecting source code.
3. As a project owner, I want HTML reporting to remain disabled by default, so
   that installation and ordinary work do not create report artifacts.
4. As a project owner, I want the report output location documented in the
   default configuration, so that I can opt in predictably when I need an
   audit view.
5. As an existing Memory Stale user, I want reinstallation to preserve a
   customized configuration, so that an update does not overwrite team
   settings.
6. As a Codex or Claude Code user, I want the same default behavior whether or
   not configuration was previously present, so that installing the explicit
   file does not change retrieval or reporting semantics.

## Implementation Decisions

- The installer creates the durable memory configuration only on first
  project-local installation.
- The created file contains the runtime defaults: a 1,500-token context
  budget, disabled automatic HTML reporting, and the default report filename.
- The file includes concise comments describing each setting and that HTML
  reporting is opt-in.
- Installation must not create a report itself.
- Existing configuration remains untouched during repeat installation.
- The runtime continues to accept a missing configuration file for backwards
  compatibility with previously installed projects.
- Public documentation describes the default configuration as an installed,
  editable project artifact and clarifies that the HTML report feature remains
  available only on explicit request or opt-in.

## Testing Decisions

- Confirmed highest observable seam: install from a copied source tree into a
  fresh temporary Git repository, then inspect the target project's durable
  memory configuration.
- The installation test verifies the file exists, its values load through the
  public configuration interface, no HTML report is created, and the durable
  memory directory is distinct from the installed runtime directory.
- A repeat-installation test verifies a user-modified configuration is
  preserved.
- Existing configuration tests remain coverage for missing-file backwards
  compatibility and validation of malformed or invalid values.

## Out of Scope

- Removing or redesigning the optional HTML health report.
- Automatically generating reports during installation or ordinary turns.
- Moving the durable memory store below the installed skill directory.
- Changing retrieval ranking, lifecycle behavior, configuration schema, or
  global MCP registration.

## Further Notes

- The repository does not provide an issue tracker or a `ready-for-agent`
  label, so the required local specification is intentionally not published
  externally.
- The public report command is still implemented; uncertainty about prior
  removal is resolved by preserving its current opt-in behavior rather than
  expanding this installation change into a report redesign.

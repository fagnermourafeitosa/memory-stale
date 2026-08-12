#!/usr/bin/env python3
"""Codex PostToolUse adapter."""

from __future__ import annotations

from memory_stale.hook_runtime import run_post_tool_use

if __name__ == "__main__":
    raise SystemExit(run_post_tool_use())

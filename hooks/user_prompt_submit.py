#!/usr/bin/env python3
"""Codex UserPromptSubmit adapter."""

from __future__ import annotations

from memory_stale.hook_runtime import run_user_prompt_submit

if __name__ == "__main__":
    raise SystemExit(run_user_prompt_submit())

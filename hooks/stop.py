#!/usr/bin/env python3
"""Codex Stop adapter."""

from __future__ import annotations

from memory_stale.hook_runtime import run_stop

if __name__ == "__main__":
    raise SystemExit(run_stop())

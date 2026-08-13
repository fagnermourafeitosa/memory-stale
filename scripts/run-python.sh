#!/bin/sh
set -eu

MEMORY_STALE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if MEMORY_STALE_GIT_DIR=$(git -C "$PWD" rev-parse --absolute-git-dir 2>/dev/null); then
  MEMORY_STALE_RUNTIME_DATA=${MEMORY_STALE_RUNTIME_DATA:-"$MEMORY_STALE_GIT_DIR/memory-stale/runtime"}
else
  MEMORY_STALE_RUNTIME_DATA=${MEMORY_STALE_RUNTIME_DATA:-"${TMPDIR:-/tmp}/memory-stale-runtime"}
fi

export VIRTUAL_ENV=
export UV_CACHE_DIR="$MEMORY_STALE_RUNTIME_DATA/uv-cache"
export UV_PROJECT_ENVIRONMENT="${MEMORY_STALE_PROJECT_ENVIRONMENT:-$MEMORY_STALE_RUNTIME_DATA/.venv}"
export MEMORY_STALE_GRAMMAR_CACHE="$MEMORY_STALE_RUNTIME_DATA/tree-sitter-cache"
export PYTHONPATH="$MEMORY_STALE_ROOT/src"

if [ "${MEMORY_STALE_SKIP_SYNC:-0}" != "1" ]; then
  uv sync --quiet --project "$MEMORY_STALE_ROOT" --frozen --no-dev
fi
exec uv run --quiet --project "$MEMORY_STALE_ROOT" --frozen --no-sync python "$@"

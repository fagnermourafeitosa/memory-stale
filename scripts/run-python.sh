#!/bin/sh
set -eu

: "${PLUGIN_ROOT:?PLUGIN_ROOT is required}"
: "${PLUGIN_DATA:?PLUGIN_DATA is required}"

export VIRTUAL_ENV=
export UV_CACHE_DIR="$PLUGIN_DATA/uv-cache"
export UV_PROJECT_ENVIRONMENT="${MEMORY_STALE_PROJECT_ENVIRONMENT:-$PLUGIN_DATA/.venv}"
export MEMORY_STALE_GRAMMAR_CACHE="$PLUGIN_DATA/tree-sitter-cache"
export PYTHONPATH="$PLUGIN_ROOT/src"

if [ "${MEMORY_STALE_SKIP_SYNC:-0}" != "1" ]; then
  uv sync --quiet --project "$PLUGIN_ROOT" --frozen --no-dev
fi
exec uv run --quiet --project "$PLUGIN_ROOT" --frozen --no-sync python "$@"

#!/bin/sh
set -eu

SCRIPT_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIRECTORY/install_project.py" "${SCRIPT_DIRECTORY%/scripts}" "$@"

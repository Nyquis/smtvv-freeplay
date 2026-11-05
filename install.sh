#!/usr/bin/env bash
# Thin launcher: the installer itself is installer.py (standard library only).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
    echo "ERROR: python3 was not found. In Desktop Mode it is normally available;"
    echo "       open Konsole and run this script there."
    exit 1
fi

exec "$PY" "$HERE/installer.py" "$@"

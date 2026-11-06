#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Nyquis
# SPDX-FileCopyrightText: 2026 the countlessbats/smtvv-freeplay authors
# SPDX-License-Identifier: MIT AND Apache-2.0
# Modified by Nyquis from the upstream MIT project; see LICENSING.md.

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

#!/usr/bin/env bash
# Compile defs, then launch the Textual TUI from the project venv.
set -euo pipefail
cd "$(dirname "$0")"

command -v scsynth >/dev/null || { echo "!! install supercollider first"; exit 1; }
VENV="../.venv/bin/python"
test -x "$VENV" || { echo "!! venv missing — run: python3 -m venv ../.venv && ../.venv/bin/pip install textual"; exit 1; }

echo "== compiling defs =="
QT_QPA_PLATFORM=offscreen timeout 40 sclang drone.scd >/dev/null
exec "$VENV" tui.py

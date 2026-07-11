#!/usr/bin/env bash
# Compile the drone defs, then launch the verbal-drone REPL (which boots scsynth).
set -euo pipefail
cd "$(dirname "$0")"

command -v scsynth >/dev/null || { echo "!! install supercollider first"; exit 1; }

echo "== compiling drone defs =="
QT_QPA_PLATFORM=offscreen timeout 40 sclang drone.scd
test -f defs/droneVoice.scsyndef || { echo "!! def compile failed"; exit 1; }
test -f defs/fxReverb.scsyndef   || { echo "!! def compile failed"; exit 1; }

echo "== launching foundry =="
exec python3 foundry.py

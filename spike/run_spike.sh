#!/usr/bin/env bash
# Phase-0 spike runner: compile def -> boot scsynth (via PipeWire's JACK) ->
# drive it over OSC -> tear down. Throwaway validation, not production.
set -euo pipefail
cd "$(dirname "$0")"

command -v scsynth >/dev/null || { echo "!! scsynth not found. Install supercollider first."; exit 1; }
command -v sclang  >/dev/null || { echo "!! sclang not found. Install supercollider first."; exit 1; }

echo "== [1/3] compiling SynthDef with sclang (offline, no server) =="
# timeout guards against sclang dropping to interactive mode on a parse error
# (it would otherwise hang forever waiting on stdin).
QT_QPA_PLATFORM=offscreen timeout 40 sclang build_defs.scd
test -f defs/spikeVoice.scsyndef || { echo "!! def not written (sclang parse error? check output above)"; exit 1; }

echo "== [2/3] booting scsynth on UDP 57110 via pw-jack =="
# SC_JACK_DEFAULT_OUTPUTS auto-wires scsynth's out ports to the system sink.
export SC_JACK_DEFAULT_OUTPUTS="system:playback_1,system:playback_2"
pw-jack scsynth -u 57110 >/tmp/scsynth.log 2>&1 &
SC_PID=$!
trap 'kill $SC_PID 2>/dev/null || true' EXIT

# Wait for "SuperCollider 3 server ready." (up to ~8s)
for i in $(seq 1 40); do
  grep -q "server ready" /tmp/scsynth.log && break
  sleep 0.2
  kill -0 $SC_PID 2>/dev/null || { echo "!! scsynth died on boot:"; cat /tmp/scsynth.log; exit 1; }
done
grep -q "server ready" /tmp/scsynth.log || { echo "!! scsynth not ready in time:"; cat /tmp/scsynth.log; exit 1; }
echo "   scsynth ready (pid $SC_PID)"

echo "== [3/3] driving over OSC — LISTEN =="
python3 drive.py

echo "== spike complete. scsynth log at /tmp/scsynth.log =="

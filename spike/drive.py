#!/usr/bin/env python3
"""Phase-0 spike driver.

Proves the one load-bearing assumption behind the whole project:
a NON-sclang process can drive scsynth over OSC to (1) make sound and
(2) mutate a running node's parameter LIVE, glitch-free.

Now waits for the server's async /done reply before starting the voice —
the previous version fired /s_new before /d_load had finished loading.

Assumes scsynth is already listening on UDP 57110. Run via run_spike.sh.
"""
import math
import os
import time

from osc import Client

DEFDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defs")
NODE = 1000          # our voice's node id
ROOT_GROUP = 0       # scsynth's default root group
ADD_TO_HEAD = 0


def main():
    c = Client("127.0.0.1", 57110)

    # 1) Load the compiled def(s). NOTE: /d_load on a single file is a silent
    #    no-op on scsynth 3.11 (returns /done, loads nothing); /d_loadDir on the
    #    folder is reliable. And /done alone can't be trusted here — confirm the
    #    def actually registered via /status before starting the voice.
    print(f"[drive] /d_loadDir {DEFDIR} — loading + confirming...")
    c.send("/d_loadDir", DEFDIR)
    c.wait_for("/done", timeout=4.0)
    deadline = time.monotonic() + 3.0
    n = 0
    while time.monotonic() < deadline:
        c.send("/status")
        n = c.wait_for("/status.reply", 2.0)[4]   # numLoadedSynthDefs
        if n >= 1:
            break
        time.sleep(0.1)
    if n < 1:
        raise RuntimeError("loadDir reported /done but 0 synthdefs registered")
    print(f"[drive] {n} synthdef(s) registered, confirmed")

    # 2) Start the voice. It begins sounding immediately (gate defaults to 1).
    print("[drive] /s_new spikeVoice -> node", NODE)
    c.send("/s_new", "spikeVoice", NODE, ADD_TO_HEAD, ROOT_GROUP,
           "freq", 110.0, "cutoff", 300.0, "amp", 0.2)
    # A /fail would arrive here if the node couldn't start; a brief listen catches it.
    early = c.recv(timeout=0.25)
    if early and early[0] == "/fail":
        raise RuntimeError(f"/s_new failed: {early[1]}")
    time.sleep(0.3)

    # 3) THE TEST: sweep the filter cutoff live over ~3.5s. If this is smooth
    #    with no clicks/zipper, live parameter mutation over OSC is viable and
    #    the state->engine reconcile model holds.
    print("[drive] sweeping cutoff live (listen for a smooth filter sweep)...")
    steps = 175
    dur = 3.5
    for i in range(steps):
        phase = i / steps
        tri = 1.0 - abs(2.0 * phase - 1.0)          # 0->1->0
        cutoff = 300.0 * math.pow(3500.0 / 300.0, tri)  # 300 -> ~3500 -> 300 Hz
        c.send("/n_set", NODE, "cutoff", float(cutoff))
        time.sleep(dur / steps)

    # 4) Release via the envelope gate, then let it ring out.
    print("[drive] gate off, releasing")
    c.send("/n_set", NODE, "gate", 0.0)
    time.sleep(0.5)

    c.close()
    print("[drive] done. If you heard a clean sweep with no clicks -> Phase 0 PASSES.")


if __name__ == "__main__":
    main()

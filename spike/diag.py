#!/usr/bin/env python3
"""Diagnostic: interrogate scsynth about what it actually loaded."""
import os, time
from osc import Client

DEF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defs", "spikeVoice.scsyndef")
c = Client("127.0.0.1", 57110)

def status(label):
    c.send("/status")
    r = c.wait_for("/status.reply", 2.0)
    # fields: _, ugens, synths, groups, synthdefs, avgCPU, peakCPU, nomSR, actSR
    print(f"[{label}] synths={r[2]} groups={r[3]} synthdefs={r[4]}")

status("boot")

print(f"[diag] /d_load {DEF}")
c.send("/d_load", DEF)
print("  ->", c.wait_for("/done", 4.0))
status("after d_load")

print("[diag] /s_new spikeVoice 2000")
c.send("/s_new", "spikeVoice", 2000, 0, 0)
early = c.recv(0.4)
print("  reply:", early)
status("after s_new")

# ask the server to print its node tree (with control values) to its own log
c.send("/g_dumpTree", 0, 1)
time.sleep(0.3)
c.close()
print("[diag] done — check /tmp/scsynth.log for the dumped tree")

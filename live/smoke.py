#!/usr/bin/env python3
"""Non-interactive end-to-end check: boot the drone, then drive it with two
spoken instructions via the agent. Proves the full Phase-1 loop makes + mutates
sound. Run from run.sh's dir. Makes ~12s of audio."""
import time
from agent import Agent
from engine import Engine
from graph import Graph, resolve

graph = Graph(); engine = Engine(graph); agent = Agent()
print("booting..."); engine.boot()
print("drone live — listen (3s of the base sound)"); time.sleep(3)

for instruction in [
    "make it much darker and add a lot of space",
    "drop the pitch a whole octave and make the filter wobble slowly and deeply",
]:
    print(f"\n> {instruction}")
    try:
        ops, say = agent.act(graph, instruction)
    except Exception as e:
        print("  agent error:", e); continue
    print("  say:", say)
    for op in ops:
        try:
            node, param = resolve(op.get("node"), op.get("param"))
            old, new = graph.set(node, param, op.get("value"))
            if new != old:
                engine.push(node, param, new)
                print(f"    {node}.{param}: {old:g} -> {new:g}")
        except Exception as ex:
            print(f"    skip {op}: {ex}")
    print("  listening 4s..."); time.sleep(4)

print("\nshutting down"); engine.shutdown()

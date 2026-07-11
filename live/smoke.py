#!/usr/bin/env python3
"""Non-interactive end-to-end check: boot the drone, then drive it with spoken
instructions — including growing the effect chain. Makes ~16s of audio."""
import time
from agent import Agent
from engine import Engine
from graph import Graph

graph = Graph(); engine = Engine(graph); agent = Agent(backend="local")
print("booting..."); engine.boot()
print("drone live — listen (3s of the base sound)"); time.sleep(3)

for instruction in [
    "make it much darker and add a lot of space",
    "add a slow tapey delay with lots of feedback",
    "drop the pitch a whole octave and make the filter wobble slowly and deeply",
]:
    print(f"\n> {instruction}")
    try:
        ops, say = agent.act(graph, instruction)
    except Exception as e:
        print("  agent error:", e); continue
    print("  say:", say)
    for op in ops:
        kind = op.get("op", "set")
        try:
            if kind == "add":
                fx = graph.add_effect(op["type"]); engine.spawn_effect(fx)
                print(f"    + added {fx['key']} ({fx['type']})")
            elif kind == "remove":
                node, _ = graph.resolve(op.get("node"), op.get("node"))
                fx = graph.remove_effect(node)
                if fx:
                    engine.free_effect(fx); print(f"    - removed {node}")
            else:
                node, param = graph.resolve(op.get("node"), op.get("param"))
                old, new = graph.set(node, param, op.get("value"))
                if new != old:
                    engine.push(node, param, new)
                    print(f"    {node}.{param}: {old:g} -> {new:g}")
        except Exception as ex:
            print(f"    skip {op}: {ex}")
    print("  listening 4s..."); time.sleep(4)

print("\nshutting down"); engine.shutdown()

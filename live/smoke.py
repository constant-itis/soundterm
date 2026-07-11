#!/usr/bin/env python3
"""Non-interactive end-to-end check: boot the drone, then drive it with spoken
instructions — sculpt, add a drum, play a note sequence. ~20s of audio."""
import time
from agent import Agent
from engine import Engine
from graph import Graph

graph = Graph(); engine = Engine(graph); agent = Agent(backend="local")
print("booting..."); engine.boot()
print("drone live — listen (3s)"); time.sleep(3)

for instruction in [
    "make it darker and add some space",
    "add a drum beat around 100 bpm",
    "add a sequencer playing a little minor riff",
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
                mod = graph.add_module(op["type"]); engine.spawn_module(mod)
                print(f"    + added {mod['key']} ({mod['type']})")
            elif kind == "remove":
                node, _ = graph.resolve(op.get("node"), op.get("node"))
                mod = graph.remove_module(node)
                if mod:
                    engine.free_module(mod); print(f"    - removed {node}")
            else:
                node, param = graph.resolve(op.get("node"), op.get("param"))
                old, new = graph.set(node, param, op.get("value"))
                if new != old:
                    engine.push(node, param, new)
                    print(f"    {node}.{param}: {old:g} -> {new:g}")
        except Exception as ex:
            print(f"    skip {op}: {ex}")
    print("  listening 5s..."); time.sleep(5)

print("\nshutting down"); engine.shutdown()

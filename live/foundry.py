#!/usr/bin/env python3
"""foundry — the verbal drone (Phase 1: agent loop, no TUI yet).

Boots a living drone, then reshapes it from typed instructions:
    > darker and more space
    > wobblier, drop the pitch an octave
Type /help for commands. Ctrl-C or /quit to leave.
"""
import os
import sys

from agent import Agent
from engine import Engine
from graph import Graph, resolve

# ---- tiny ANSI palette (semantic tokens — the "CSS for the TUI" starts here) ----
DIM = "\033[2m"; BOLD = "\033[1m"; RST = "\033[0m"
AMBER = "\033[38;5;179m"; TEAL = "\033[38;5;73m"; RED = "\033[38;5;167m"
GREY = "\033[38;5;245m"


def show_state(graph):
    for node, ps in graph.params.items():
        vals = "  ".join(f"{GREY}{k}{RST} {v:g}" for k, v in ps.items())
        print(f"  {TEAL}{node}{RST}  {vals}")


HELP = f"""{BOLD}commands{RST}
  {AMBER}<anything>{RST}   describe how the sound should change (goes to the agent)
  {AMBER}/state{RST}       show the current patch
  {AMBER}/save [f]{RST}    save patch to f (default patch.json)
  {AMBER}/panic{RST}       duck to silence
  {AMBER}/help{RST}        this
  {AMBER}/quit{RST}        leave"""


def main():
    graph = Graph()
    engine = Engine(graph)
    agent = Agent()

    print(f"{DIM}booting scsynth + drone...{RST}")
    engine.boot()
    print(f"{BOLD}{AMBER}foundry{RST} — the drone is live. describe changes, /help for commands.\n")
    show_state(graph)
    print()

    try:
        while True:
            try:
                line = input(f"{AMBER}>{RST} ").strip()
            except EOFError:
                break
            if not line:
                continue

            if line in ("/quit", "/q"):
                break
            elif line == "/help":
                print(HELP)
            elif line == "/state":
                show_state(graph)
            elif line == "/panic":
                engine.panic()
                print(f"{RED}silenced{RST} (set a level to bring it back)")
            elif line.startswith("/save"):
                parts = line.split(maxsplit=1)
                path = parts[1] if len(parts) > 1 else "patch.json"
                graph.save(path)
                print(f"{GREY}saved -> {path}{RST}")
            elif line.startswith("/"):
                print(f"{RED}unknown command{RST} — /help")
            else:
                handle_prompt(agent, engine, graph, line)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{DIM}shutting down...{RST}")
        engine.shutdown()


def handle_prompt(agent, engine, graph, text):
    try:
        ops, say = agent.act(graph, text)
    except Exception as e:
        print(f"{RED}agent error:{RST} {e}")
        return

    applied = []
    for op in ops:
        try:
            node, param = resolve(op.get("node"), op.get("param"))
            old, new = graph.set(node, param, op.get("value"))
        except (KeyError, TypeError, ValueError):
            print(f"  {RED}skip{RST} {op.get('node')}.{op.get('param')} (unknown or bad value)")
            continue
        if new != old:
            engine.push(node, param, new)
            applied.append(f"{node}.{param} {old:g}{AMBER}{new:g}{RST}")

    if say:
        print(f"  {TEAL}{say}{RST}")
    if applied:
        for a in applied:
            print(f"    {a}")
    elif not ops:
        print(f"  {GREY}(no change){RST}")


if __name__ == "__main__":
    sys.exit(main())

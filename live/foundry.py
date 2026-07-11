#!/usr/bin/env python3
"""foundry — the verbal drone (Phase 1: agent loop, no TUI yet).

Boots a living drone, then reshapes it from typed instructions and grows its
effect chain by conversation:
    > darker and more space
    > add a slow tapey delay
    > wobblier, drop the pitch an octave
Type /help for commands. Ctrl-C or /quit to leave.
"""
import os
import sys

from agent import Agent
from engine import Engine
from graph import Graph

# ---- tiny ANSI palette (semantic tokens — the "CSS for the TUI" starts here) ----
DIM = "\033[2m"; BOLD = "\033[1m"; RST = "\033[0m"
AMBER = "\033[38;5;179m"; TEAL = "\033[38;5;73m"; RED = "\033[38;5;167m"
GREY = "\033[38;5;245m"


def show_state(graph):
    for node in graph.node_keys():
        ps = graph.node_params(node)
        m = graph._mod(node)
        label = f"{node} {DIM}({m['type']}){RST}" if m else node
        vals = "  ".join(f"{GREY}{k}{RST} {v:g}" for k, v in ps.items())
        print(f"  {TEAL}{label}{RST}  {vals}")


def banner(agent):
    print(f"{BOLD}{AMBER}foundry{RST} — the drone is live "
          f"{DIM}[model: {agent.backend}]{RST}. describe changes, /help for commands.\n")


HELP = f"""{BOLD}commands{RST}
  {AMBER}<anything>{RST}     describe how the sound should change (goes to the agent)
  {AMBER}/state{RST}         show the current patch + effect chain
  {AMBER}/model <m>{RST}     switch agent: local | opus | sonnet | haiku
  {AMBER}/save [f]{RST}      save patch to f (default patch.json)
  {AMBER}/panic{RST}         duck to silence
  {AMBER}/help{RST}          this
  {AMBER}/quit{RST}          leave"""


def main():
    graph = Graph()
    engine = Engine(graph)
    agent = Agent(backend=os.environ.get("FOUNDRY_MODEL", "local"))

    print(f"{DIM}booting scsynth + drone...{RST}")
    engine.boot()
    banner(agent)
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
            elif line.startswith("/model"):
                parts = line.split(maxsplit=1)
                if len(parts) > 1:
                    agent.backend = parts[1].strip()
                print(f"{GREY}model: {agent.backend}{RST}")
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

    changes = []
    for op in ops:
        kind = op.get("op", "set")
        try:
            if kind == "add":
                mod = graph.add_module(op["type"])
                engine.spawn_module(mod)
                changes.append(f"{TEAL}+ added{RST} {mod['key']} ({mod['type']})")
            elif kind == "remove":
                node, _ = graph.resolve(op.get("node"), op.get("node"))
                mod = graph.remove_module(node)
                if mod:
                    engine.free_module(mod)
                    changes.append(f"{RED}- removed{RST} {node}")
            else:  # set
                node, param = graph.resolve(op.get("node"), op.get("param"))
                old, new = graph.set(node, param, op.get("value"))
                if new != old:
                    engine.push(node, param, new)
                    changes.append(f"{node}.{param} {old:g}{AMBER}{new:g}{RST}")
        except (KeyError, TypeError, ValueError):
            print(f"  {RED}skip{RST} {op} (unknown node/param/type)")

    if say:
        print(f"  {TEAL}{say}{RST}")
    for c in changes:
        print(f"    {c}")
    if not changes and not say:
        print(f"  {GREY}(no change){RST}")


if __name__ == "__main__":
    sys.exit(main())

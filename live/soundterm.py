#!/usr/bin/env python3
"""soundterm — the verbal drone (Phase 1: agent loop, no TUI yet).

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

PATCH_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patches"))
EXPORT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exports"))

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
    print(f"{BOLD}{AMBER}soundterm{RST} — the drone is live "
          f"{DIM}[model: {agent.backend}]{RST}. describe changes, /help for commands.\n")


HELP = f"""{BOLD}commands{RST}
  {AMBER}<anything>{RST}     describe how the sound should change (goes to the agent)
  {AMBER}/state{RST}         show the current patch + effect chain
  {AMBER}/model <m>{RST}     switch agent: local | opus | sonnet | haiku
  {AMBER}/save [name]{RST}   save the whole patch (default 'patch')
  {AMBER}/load <name>{RST}   load a saved patch · {AMBER}/patches{RST} to list
  {AMBER}/export [name]{RST} record the master to a WAV (again to stop)
  {AMBER}/panic{RST}         duck to silence
  {AMBER}/help{RST}          this
  {AMBER}/quit{RST}          leave"""


def _patch_path(name):
    return os.path.join(PATCH_DIR, name + ".json")


def _list_patches():
    try:
        return sorted(f[:-5] for f in os.listdir(PATCH_DIR) if f.endswith(".json"))
    except FileNotFoundError:
        return []


def main():
    graph = Graph()
    engine = Engine(graph)
    agent = Agent(backend=os.environ.get("SOUNDTERM_MODEL", "local"))

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
                name = parts[1].strip() if len(parts) > 1 else "patch"
                os.makedirs(PATCH_DIR, exist_ok=True)
                graph.save(_patch_path(name))
                print(f"{GREY}saved -> {name}{RST}")
            elif line.startswith("/patches"):
                print(f"{GREY}patches: {', '.join(_list_patches()) or '(none)'}{RST}")
            elif line.startswith("/export"):
                if engine.is_exporting():
                    path = engine.stop_export()
                    print(f"{GREY}■ saved recording -> {os.path.basename(path)}{RST}")
                else:
                    parts = line.split(maxsplit=1)
                    name = parts[1].strip() if len(parts) > 1 else "take"
                    os.makedirs(EXPORT_DIR, exist_ok=True)
                    engine.start_export(os.path.join(EXPORT_DIR, name + ".wav"))
                    print(f"{RED}● REC{RST} -> {name}.wav (/export again to stop)")
            elif line.startswith("/load"):
                parts = line.split(maxsplit=1)
                if len(parts) > 1 and os.path.exists(_patch_path(parts[1].strip())):
                    graph.load(_patch_path(parts[1].strip()))
                    engine.rebuild_from_graph()
                    print(f"{GREY}loaded <- {parts[1].strip()}{RST}")
                    show_state(graph)
                else:
                    print(f"{RED}no such patch{RST} — /patches to list")
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

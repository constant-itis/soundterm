#!/usr/bin/env python3
"""soundterm TUI — a visual rack over the live patch.

Non-destructive: reuses the SAME engine/graph/agent as the REPL. Each module is a
box in a horizontal rack; each param is a bar you drag with the mouse. The prompt
bar talks to the agent; the +buttons add modules by hand. Both edit one live patch.
"""
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, HorizontalScroll
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Static

from agent import Agent
from engine import Engine
from graph import Graph, MODULE_REGISTRY

# semantic tokens (the themeable palette — same ones the doc/README use)
AMBER = "#f2b84b"; TEAL = "#45d6c9"; GREY = "#8a95a6"; TRACK = "#2c3646"
LABEL_W = 16


class ParamRow(Widget):
    """One draggable parameter bar: name + value + a fill bar. Drag maps x -> value."""
    can_focus = True

    def __init__(self, node, param, lo, hi, value, on_change):
        super().__init__(id=f"row-{node}-{param}")
        self.node, self.param = node, param
        self.lo, self.hi = float(lo), float(hi)
        self._value = float(value)
        self.on_change = on_change
        self._drag = False

    def render(self):
        w = max(self.size.width, LABEL_W + 3)
        barw = max(1, w - LABEL_W - 1)
        frac = 0.0 if self.hi == self.lo else (self._value - self.lo) / (self.hi - self.lo)
        frac = min(1.0, max(0.0, frac))
        fill = round(frac * barw)
        val = f"{self._value:g}"
        markup = (f"[{GREY}]{self.param[:9]:<9}[/][{AMBER}]{val:>6}[/] "
                  f"[{AMBER}]{'█' * fill}[/][{TRACK}]{'─' * (barw - fill)}[/]")
        return Text.from_markup(markup)

    def _apply(self, x):
        w = max(self.size.width, LABEL_W + 3)
        if x < LABEL_W:
            return
        barw = max(1, w - LABEL_W - 1)
        frac = min(1.0, max(0.0, (x - LABEL_W) / barw))
        self._value = self.lo + frac * (self.hi - self.lo)
        self.refresh()
        self.on_change(self.node, self.param, self._value)

    def set_value(self, v):
        self._value = float(v)
        self.refresh()

    def on_mouse_down(self, e):
        self.capture_mouse(); self._drag = True; self._apply(e.x)

    def on_mouse_move(self, e):
        if self._drag:
            self._apply(e.x)

    def on_mouse_up(self, e):
        self._drag = False; self.release_mouse()


class ModulePanel(Vertical):
    """A bordered box for one node, holding its param bars."""

    def __init__(self, node, graph, on_change):
        super().__init__(id=f"panel-{node}", classes="module")
        self.node, self.graph, self.on_change = node, graph, on_change

    def on_mount(self):
        m = self.graph._mod(self.node)
        self.border_title = f"{self.node} · {m['type']}" if m else self.node
        specs = self.graph.specs_for(self.node)
        params = self.graph.node_params(self.node)
        for p, (lo, hi, _desc) in specs.items():
            self.mount(ParamRow(self.node, p, lo, hi, params[p], self.on_change))


class Soundterm(App):
    TITLE = "soundterm"
    BINDINGS = [("ctrl+q", "quit", "quit")]
    CSS = f"""
    Screen {{ background: #0c0f14; }}
    #rack {{ height: 1fr; padding: 1 1 0 1; }}
    .module {{ width: 34; height: auto; border: round {TRACK}; border-title-color: {AMBER};
               padding: 0 1; margin: 0 2 1 0; background: #12171f; }}
    ParamRow {{ height: 1; }}
    ParamRow:focus {{ background: #1c2430; }}
    #status {{ height: 1; color: {TEAL}; padding: 0 1; background: #171d27; }}
    #addbar {{ height: 3; padding: 1 1 0 1; }}
    .addbtn {{ margin: 0 2 0 0; min-width: 9; border: none; height: 1; background: #1c2430; color: {AMBER}; }}
    #prompt {{ border: round {AMBER}; }}
    Header {{ background: #171d27; }}
    """

    def __init__(self, model="haiku"):
        super().__init__()
        self.graph = Graph()
        self.engine = Engine(self.graph)
        self.agent = Agent(backend=model)
        self.last_status = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield HorizontalScroll(id="rack")
        yield Static("booting scsynth + drone…", id="status")
        with Horizontal(id="addbar"):
            for t in MODULE_REGISTRY:
                yield Button(f"+{t}", id=f"add-{t}", classes="addbtn")
        yield Input(placeholder="describe a change…  (darker and more space · add a drum · /model haiku)",
                    id="prompt")
        yield Footer()

    def on_mount(self):
        self._boot()

    @work(thread=True)
    def _boot(self):
        try:
            self.engine.boot()
        except Exception as e:
            self.call_from_thread(self._set_status, f"boot failed: {e}")
            return
        self.call_from_thread(self._after_boot)

    def _after_boot(self):
        rack = self.query_one("#rack")
        for node in self.graph.node_keys():
            rack.mount(ModulePanel(node, self.graph, self._on_param))
        self._set_status(f"live · model {self.agent.backend} · drag a bar, click +, or type a change")

    # ---- edits --------------------------------------------------------------
    def _on_param(self, node, param, value):
        _old, new = self.graph.set(node, param, value)
        self.engine.push(node, param, new)

    def on_button_pressed(self, event):
        t = event.button.id.split("-", 1)[1]
        mod = self.graph.add_module(t)
        self.engine.spawn_module(mod)
        self.query_one("#rack").mount(ModulePanel(mod["key"], self.graph, self._on_param))
        self._set_status(f"+ added {mod['key']}")

    def on_input_submitted(self, event):
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("/model"):
            parts = text.split()
            if len(parts) > 1:
                self.agent.backend = parts[1]
            self._set_status(f"model {self.agent.backend}")
            return
        self._set_status(f"… {text}")
        self._run_agent(text)

    @work(thread=True, exclusive=True, group="agent")
    def _run_agent(self, text):
        try:
            ops, say = self.agent.act(self.graph, text)
        except Exception as e:
            self.call_from_thread(self._set_status, f"agent error: {e}")
            return
        self.call_from_thread(self._apply_ops, ops, say)

    def _apply_ops(self, ops, say):
        for op in ops:
            kind = op.get("op", "set")
            try:
                if kind == "add":
                    mod = self.graph.add_module(op["type"])
                    self.engine.spawn_module(mod)
                    self.query_one("#rack").mount(ModulePanel(mod["key"], self.graph, self._on_param))
                elif kind == "remove":
                    node, _ = self.graph.resolve(op.get("node"), op.get("node"))
                    mod = self.graph.remove_module(node)
                    if mod:
                        self.engine.free_module(mod)
                        try:
                            self.query_one(f"#panel-{node}").remove()
                        except Exception:
                            pass
                else:
                    node, param = self.graph.resolve(op.get("node"), op.get("param"))
                    _old, new = self.graph.set(node, param, op.get("value"))
                    self.engine.push(node, param, new)
                    try:
                        self.query_one(f"#row-{node}-{param}", ParamRow).set_value(new)
                    except Exception:
                        pass
            except Exception:
                pass
        self._set_status(say or "done")

    def _set_status(self, msg):
        self.last_status = msg
        self.query_one("#status", Static).update(msg)

    def on_unmount(self):
        try:
            self.engine.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    import os
    Soundterm(model=os.environ.get("SOUNDTERM_MODEL", "haiku")).run()

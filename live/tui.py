#!/usr/bin/env python3
"""soundterm TUI — a visual rack over the live patch.

Non-destructive: reuses the SAME engine/graph/agent as the REPL. Each module is a
box in a horizontal rack; each param is a bar you drag with the mouse. The prompt
bar talks to the agent; the +buttons add modules by hand. Both edit one live patch.
"""
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, HorizontalScroll
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
    BINDINGS = [("space", "toggle_module", "start/stop")]

    def action_toggle_module(self):
        self.app.toggle_module(self.node)

    def __init__(self, node, param, lo, hi, value, on_change):
        super().__init__(id=f"row-{node}-{param}")
        self.node, self.param = node, param
        self.lo, self.hi = float(lo), float(hi)
        self._value = float(value)
        self.on_change = on_change
        self._drag = False
        self._mod_src = None       # set to a CV source key when a cable drives this

    def render(self):
        w = max(self.size.width, LABEL_W + 3)
        barw = max(1, w - LABEL_W - 1)
        if self._mod_src:                                  # driven by a patch cable
            src = f"«{self._mod_src}"[:LABEL_W - 1]
            markup = (f"[{TEAL}]~{self.param[:8]:<8}[/][{TEAL}]{src:>6}[/] "
                      f"[{TEAL}]{'┈' * barw}[/]")
            return Text.from_markup(markup)
        frac = 0.0 if self.hi == self.lo else (self._value - self.lo) / (self.hi - self.lo)
        frac = min(1.0, max(0.0, frac))
        fill = round(frac * barw)
        val = f"{self._value:g}"
        markup = (f"[{GREY}]{self.param[:9]:<9}[/][{AMBER}]{val:>6}[/] "
                  f"[{AMBER}]{'█' * fill}[/][{TRACK}]{'─' * (barw - fill)}[/]")
        return Text.from_markup(markup)

    def set_modulated(self, src):
        self._mod_src = src
        self.refresh()

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
        if getattr(e, "button", 1) == 3:                   # right-click → patch menu
            self.app.open_param_menu(self.node, self.param, e.screen_x, e.screen_y)
            e.stop()
            return
        if self._mod_src:                                  # a cable owns this param
            self.focus()
            return
        self.focus(); self.capture_mouse(); self._drag = True; self._apply(e.x)

    def on_mouse_move(self, e):
        if self._drag:
            self._apply(e.x)

    def on_mouse_up(self, e):
        self._drag = False; self.release_mouse()


class StepRow(Widget):
    """A compact 16-step on/off lane: one row, click a cell to toggle it. Replaces a
    stack of 16 bars for drum voices. Grouped in 4s so the beat is easy to read."""
    can_focus = True

    def __init__(self, node, step_keys, values, on_change):
        super().__init__(id=f"steprow-{node}")
        self.node = node
        self.keys = step_keys                       # ordered step0..stepN
        self.vals = [float(v) for v in values]
        self.on_change = on_change

    def render(self):
        cells = []
        for i, v in enumerate(self.vals):
            mark, color = ("▓▓", AMBER) if v > 0 else ("··", TRACK)
            cells.append(f"[{color}]{mark}[/]")
            if i % 4 == 3 and i < len(self.vals) - 1:
                cells.append(" ")
        return Text.from_markup(f"[{GREY}]steps[/] " + "".join(cells))

    def _cell_at(self, x):
        pos = 6                                     # width of "steps "
        for i in range(len(self.vals)):
            if pos <= x < pos + 2:
                return i
            pos += 2
            if i % 4 == 3:
                pos += 1
        return None

    def on_mouse_down(self, e):
        if getattr(e, "button", 1) == 3:                   # right-click → module menu
            self.app.open_module_menu(self.node, e.screen_x, e.screen_y)
            e.stop()
            return
        self.focus()
        i = self._cell_at(e.x)
        if i is not None:
            self.vals[i] = 0.0 if self.vals[i] > 0 else 1.0
            self.refresh()
            self.on_change(self.node, self.keys[i], self.vals[i])

    def set_step(self, param, value):
        if param in self.keys:
            self.vals[self.keys.index(param)] = float(value)
            self.refresh()


class ModulePanel(Vertical):
    """A bordered box for one node, holding its param bars (and a step lane if any)."""

    def __init__(self, node, graph, on_change):
        super().__init__(id=f"panel-{node}", classes="module")
        self.node, self.graph, self.on_change = node, graph, on_change

    def on_mount(self):
        self._render_title()
        specs = self.graph.specs_for(self.node)
        params = self.graph.node_params(self.node)
        step_keys = sorted((p for p in specs if p.startswith("step")),
                           key=lambda s: int(s[4:]))
        onoff = bool(step_keys) and all(specs[k][1] <= 1.0 for k in step_keys)
        for p, (lo, hi, _desc) in specs.items():
            if onoff and p.startswith("step"):
                continue                            # shown as a compact StepRow instead
            self.mount(ParamRow(self.node, p, lo, hi, params[p], self.on_change))
        if onoff:
            self.mount(StepRow(self.node, step_keys, [params[k] for k in step_keys],
                               self.on_change))

    def _render_title(self):
        m = self.graph._mod(self.node)
        label = f"{self.node} · {m['type']}" if m else self.node
        glyph = "▶" if self.graph.is_enabled(self.node) else "■"
        self.border_title = f"{glyph} {label}"

    def set_enabled(self, on):
        self.set_class(not on, "stopped")
        self._render_title()

    def on_mouse_down(self, e):
        if getattr(e, "button", 1) == 3:                   # right-click the box → menu
            self.app.open_module_menu(self.node, e.screen_x, e.screen_y)
            e.stop()


class MenuItem(Static):
    """One clickable row in a context menu. Runs its callback (which also closes the
    menu) on click."""
    def __init__(self, label, cb):
        super().__init__(label, classes="ctxitem")
        self._cb = cb

    def on_mouse_down(self, e):
        e.stop()
        self._cb()


class ContextMenu(Container):
    """A small floating menu. Lives on the `overlay` layer inside a full-screen
    backdrop that closes it on click-away; the app positions it at the cursor."""
    def __init__(self, items, x, y):
        super().__init__(id="ctxbackdrop")
        self._items = items                 # [(label, callback)]
        self._at = (x, y)

    def compose(self) -> ComposeResult:
        menu = Vertical(id="ctxmenu")
        menu.styles.offset = self._at
        with menu:
            for label, cb in self._items:
                yield MenuItem(label, cb)

    def on_mouse_down(self, e):             # click-away (backdrop) closes
        e.stop()
        self.remove()


class Soundterm(App):
    TITLE = "soundterm"
    BINDINGS = [("ctrl+q", "quit", "quit"), ("escape", "close_menu", "close menu")]
    CSS = f"""
    Screen {{ background: #0c0f14; layers: base overlay; }}
    #rack {{ height: 1fr; padding: 1 1 0 1; }}
    #ctxbackdrop {{ layer: overlay; width: 100%; height: 100%; background: $background 0%; }}
    #ctxmenu {{ width: auto; height: auto; border: round {AMBER}; background: #12171f; }}
    .ctxitem {{ width: auto; height: 1; padding: 0 1; color: {AMBER}; }}
    .ctxitem:hover {{ background: {AMBER}; color: #12171f; }}
    .module {{ width: 34; height: auto; border: round {TRACK}; border-title-color: {AMBER};
               padding: 0 1; margin: 0 2 1 0; background: #12171f; }}
    .module.stopped {{ border: round #333b47; border-title-color: {GREY}; background: #0e1219; }}
    ParamRow {{ height: 1; }}
    ParamRow:focus {{ background: #1c2430; }}
    StepRow {{ height: 1; }}
    StepRow:focus {{ background: #1c2430; }}
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
        with HorizontalScroll(id="addbar"):
            for t, reg in MODULE_REGISTRY.items():
                if reg.get("hidden"):
                    continue
                yield Button(f"+{t}", id=f"add-{t}", classes="addbtn")
            yield Button("● sample", id="sample", classes="addbtn")
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
        self._set_status(f"live · model {self.agent.backend} · drag a bar · space=start/stop · click + · type a change")

    # ---- edits --------------------------------------------------------------
    def _on_param(self, node, param, value):
        _old, new = self.graph.set(node, param, value)
        self.engine.push(node, param, new)

    def toggle_module(self, node):
        on = self.graph.toggle(node)
        self.engine.apply_enabled(node)
        try:
            self.query_one(f"#panel-{node}", ModulePanel).set_enabled(on)
        except Exception:
            pass
        self._set_status(f"{'▶ started' if on else '■ stopped'} {node}")

    def add_module_ui(self, mtype):
        """Add a module + spawn it + mount its panel. Shared by the +buttons and the
        right-click menus. Returns the new module dict."""
        mod = self.graph.add_module(mtype)
        self.engine.spawn_module(mod)
        self.query_one("#rack").mount(ModulePanel(mod["key"], self.graph, self._on_param))
        return mod

    def on_button_pressed(self, event):
        if event.button.id == "sample":
            self._apply_ops([{"op": "sample", "seconds": 4.0}], "● sampling…")
            return
        t = event.button.id.split("-", 1)[1]
        mod = self.add_module_ui(t)
        self._set_status(f"+ added {mod['key']}")

    def _finish_sample(self, buf):
        """Second half of a capture: the buffer is full, spawn a looping sampler."""
        mod = self.graph.add_sampler(buf)
        self.engine.spawn_module(mod)
        self.query_one("#rack").mount(ModulePanel(mod["key"], self.graph, self._on_param))
        self._set_status(f"captured → {mod['key']} · looping (space to stop)")

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
                    node = self.graph.resolve_node(op.get("node"))
                    for e in self.graph.edges_touching(node):   # pull cables first
                        self.engine.disconnect(e)
                        self._mark_modulated(e["dst"], e["param"], None)
                    mod = self.graph.remove_module(node)
                    if mod:
                        self.engine.free_module(mod)
                        try:
                            self.query_one(f"#panel-{node}").remove()
                        except Exception:
                            pass
                elif kind == "connect":
                    src = self.graph.resolve_node(op.get("src"))
                    dst, param = self.graph.resolve(op.get("node"), op.get("param"))
                    self.graph.connect(src, dst, param)
                    self.engine.connect({"src": src, "dst": dst, "param": param})
                    self._mark_modulated(dst, param, src)
                elif kind == "disconnect":
                    src = self.graph.resolve_node(op.get("src"))
                    dst, param = self.graph.resolve(op.get("node"), op.get("param"))
                    if self.graph.disconnect(src, dst, param):
                        self.engine.disconnect({"src": src, "dst": dst, "param": param})
                        self._mark_modulated(dst, param, None)
                elif kind == "toggle":
                    node = self.graph.resolve_node(op.get("node"))
                    val = op.get("value")
                    on = (self.graph.set_enabled(node, bool(val)) if val is not None
                          else self.graph.toggle(node))
                    self.engine.apply_enabled(node)
                    try:
                        self.query_one(f"#panel-{node}", ModulePanel).set_enabled(on)
                    except Exception:
                        pass
                elif kind == "sample":
                    secs = max(0.2, min(30.0, float(op.get("seconds") or 4.0)))
                    buf, dur = self.engine.start_capture(secs)
                    # buffer fills in real time; spawn the sampler when it's full
                    self.set_timer(dur + 0.2, lambda b=buf: self._finish_sample(b))
                else:
                    node, param = self.graph.resolve(op.get("node"), op.get("param"))
                    _old, new = self.graph.set(node, param, op.get("value"))
                    self.engine.push(node, param, new)
                    try:
                        self.query_one(f"#row-{node}-{param}", ParamRow).set_value(new)
                    except Exception:
                        try:
                            self.query_one(f"#steprow-{node}", StepRow).set_step(param, new)
                        except Exception:
                            pass
            except Exception:
                pass
        self._set_status(say or "done")

    # ---- right-click context menus (tooling: they only emit graph ops) ------
    def _cv_keys(self):
        return [m["key"] for m in self.graph.modules if m["role"] == "cv"]

    def _patch(self, src, node, param):
        self._apply_ops([{"op": "connect", "src": src, "node": node, "param": param}],
                        f"~ patched {src} → {node}.{param}")

    def _unpatch(self, src, node, param):
        self._apply_ops([{"op": "disconnect", "src": src, "node": node, "param": param}],
                        f"pulled {src} ⇹ {node}.{param}")

    def _add_and_patch(self, mtype, node, param):
        mod = self.add_module_ui(mtype)
        self._patch(mod["key"], node, param)

    def _param_menu_items(self, node, param):
        """Menu for a right-clicked param bar. A modulated param can only be unpatched
        (an /n_map control takes a single source); otherwise offer every existing CV
        source, plus add-a-source-and-patch shortcuts."""
        mods = self.graph.modulators_of(node, param)
        if mods:
            return [(f"✕ unpatch from {s}", lambda s=s: self._unpatch(s, node, param))
                    for s in mods]
        items = [(f"◦ patch from {k}", lambda k=k: self._patch(k, node, param))
                 for k in self._cv_keys()]
        for t in ("lfo", "arp"):                       # add-and-patch in one gesture
            items.append((f"＋ {t} → patch here",
                          lambda t=t: self._add_and_patch(t, node, param)))
        return items

    def _module_menu_items(self, node):
        items = []
        on = self.graph.is_enabled(node)
        if self.graph.bypass_param(node) is not None:
            items.append((f"{'■ stop' if on else '▶ start'} {node}",
                          lambda: self._apply_ops(
                              [{"op": "toggle", "node": node, "value": not on}], "")))
        if node not in ("drone", "reverb"):            # fixed endpoints stay
            items.append((f"✕ remove {node}",
                          lambda: self._apply_ops([{"op": "remove", "node": node}], "")))
        return items

    def open_param_menu(self, node, param, x, y):
        self._show_menu(self._param_menu_items(node, param), x, y)

    def open_module_menu(self, node, x, y):
        self._show_menu(self._module_menu_items(node), x, y)

    def _show_menu(self, items, x, y):
        self._close_menu()
        if not items:
            return
        # each pick closes the menu, then runs its op
        wrapped = [(label, (lambda cb=cb: (self._close_menu(), cb())))
                   for label, cb in items]
        w, h = max(1, self.size.width), max(1, self.size.height)
        x = max(0, min(int(x), w - 24))
        y = max(0, min(int(y), h - len(items) - 2))
        self.mount(ContextMenu(wrapped, x, y))

    def _close_menu(self):
        for m in self.query(ContextMenu):
            m.remove()

    def action_close_menu(self):
        self._close_menu()

    def _mark_modulated(self, node, param, src):
        """Reflect a connect/disconnect on the target's param bar."""
        try:
            self.query_one(f"#row-{node}-{param}", ParamRow).set_modulated(src)
        except Exception:
            pass

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

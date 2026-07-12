"""The patch state — the single source of truth. The agent and the keyboard both
edit THIS; the engine reconciles the running sound to match it.

Chain:  drone -> [source voices] -> [effects] -> reverb
  drone/reverb are fixed endpoints. Modules are added/removed by conversation:
    - source voices (drum, seq) ADD signal onto the bus (Out.ar)
    - effects (delay, tremolo, drive) process the bus in place (ReplaceOut)
"""
import json

# fixed endpoints: node -> param -> (min, max, description)
PARAM_SPECS = {
    "drone": {
        "freq":     (20.0, 2000.0, "root pitch in Hz (lower = deeper)"),
        "detune":   (0.0, 0.5, "spread between the 3 saws (0 tight .. 0.5 seasick)"),
        "cutoff":   (40.0, 12000.0, "low-pass cutoff in Hz = brightness"),
        "res":      (0.05, 1.0, "filter resonance (0.05 soft .. 1.0 whistling)"),
        "sub":      (0.0, 1.0, "sub-octave sine level (weight/body)"),
        "noise":    (0.0, 0.5, "pink-noise air/hiss level"),
        "drive":    (1.0, 8.0, "saturation (1 clean .. 8 filthy)"),
        "lfoRate":  (0.01, 8.0, "filter movement speed in Hz"),
        "lfoDepth": (0.0, 0.9, "filter movement amount"),
        "amp":      (0.0, 0.6, "drone level (set 0 to mute the pad)"),
    },
    "reverb": {
        "mix":  (0.0, 1.0, "wet/dry = amount of space"),
        "room": (0.0, 1.0, "room size (tail length)"),
        "damp": (0.0, 1.0, "high-freq damping (0 bright .. 1 dark)"),
        "amp":  (0.0, 1.0, "master output level"),
    },
}

_STEP = (0.0, 127.0, "MIDI note for this step (0 = rest; e.g. c3=48 e3=52 g3=55 c4=60)")

# 16-step on/off gate shared by the drum voices
_ONOFF = (0.0, 1.0, "step: 1 = hit, 0 = rest")
_STEPS16 = {f"step{i}": _ONOFF for i in range(16)}


def _pat16(on):
    """A 16-step default pattern from a list of 'on' step indices."""
    return {f"step{i}": (1.0 if i in on else 0.0) for i in range(16)}


# addable modules: type -> role, SynthDef name, param specs, defaults
MODULE_REGISTRY = {
    # --- source voices (add signal) ---
    "drum": {"role": "source", "def": "drumVoice", "specs": {
        "bpm":   (40.0, 220.0, "tempo in BPM"),
        "tone":  (30.0, 120.0, "kick pitch"),
        "decay": (0.05, 1.0, "kick length"),
        "level": (0.0, 1.0, "drum level"),
        "hat":   (0.0, 1.0, "hi-hat level"),
    }, "defaults": {"bpm": 120.0, "tone": 55.0, "decay": 0.35, "level": 0.5, "hat": 0.3}},
    # --- stepped drum voices (each its own module + 16-step pattern) -------------
    "kick": {"role": "source", "def": "kickVoice", "specs": {
        "bpm": (40.0, 220.0, "tempo in BPM"), "tone": (30.0, 120.0, "kick pitch"),
        "decay": (0.05, 1.0, "kick length"), "level": (0.0, 1.0, "kick level"),
        **_STEPS16},
        "defaults": {"bpm": 120.0, "tone": 50.0, "decay": 0.3, "level": 0.9,
                     **_pat16([0, 4, 8, 12])}},
    "snare": {"role": "source", "def": "snareVoice", "specs": {
        "bpm": (40.0, 220.0, "tempo in BPM"), "tone": (120.0, 500.0, "snare body pitch"),
        "decay": (0.05, 0.6, "snare length"), "level": (0.0, 1.0, "snare level"),
        **_STEPS16},
        "defaults": {"bpm": 120.0, "tone": 220.0, "decay": 0.18, "level": 0.7,
                     **_pat16([4, 12])}},
    "hat": {"role": "source", "def": "hatVoice", "specs": {
        "bpm": (40.0, 220.0, "tempo in BPM"), "tone": (3000.0, 14000.0, "hat brightness"),
        "decay": (0.01, 0.3, "hat length"), "level": (0.0, 1.0, "hat level"),
        **_STEPS16},
        "defaults": {"bpm": 120.0, "tone": 9000.0, "decay": 0.05, "level": 0.4,
                     **_pat16([0, 2, 4, 6, 8, 10, 12, 14])}},
    "clap": {"role": "source", "def": "clapVoice", "specs": {
        "bpm": (40.0, 220.0, "tempo in BPM"), "tone": (600.0, 3000.0, "clap tone"),
        "decay": (0.05, 0.5, "clap length"), "level": (0.0, 1.0, "clap level"),
        **_STEPS16},
        "defaults": {"bpm": 120.0, "tone": 1500.0, "decay": 0.2, "level": 0.6,
                     **_pat16([4, 12])}},
    "seq": {"role": "source", "def": "seqVoice", "specs": {
        "bpm":    (40.0, 220.0, "tempo in BPM (plays 8th notes)"),
        "cutoff": (60.0, 12000.0, "sequencer filter brightness"),
        "res":    (0.05, 1.0, "filter resonance"),
        "amp":    (0.0, 0.6, "sequencer level"),
        "decay":  (0.03, 1.0, "note length"),
        "step0": _STEP, "step1": _STEP, "step2": _STEP, "step3": _STEP,
        "step4": _STEP, "step5": _STEP, "step6": _STEP, "step7": _STEP,
    }, "defaults": {"bpm": 120.0, "cutoff": 2000.0, "res": 0.3, "amp": 0.3, "decay": 0.25,
                    "step0": 48, "step1": 0, "step2": 55, "step3": 0,
                    "step4": 60, "step5": 0, "step6": 55, "step7": 0}},
    # --- effects (process the bus) ---
    "delay":   {"role": "effect", "def": "fxDelay", "specs": {
        "time": (0.02, 1.0, "delay time in s"), "fb": (0.0, 0.9, "feedback / repeats"),
        "mix": (0.0, 1.0, "wet amount")},
        "defaults": {"time": 0.3, "fb": 0.4, "mix": 0.4}},
    "tremolo": {"role": "effect", "def": "fxTremolo", "specs": {
        "rate": (0.1, 12.0, "tremolo rate in Hz"), "depth": (0.0, 1.0, "tremolo depth")},
        "defaults": {"rate": 5.0, "depth": 0.5}},
    "drive":   {"role": "effect", "def": "fxDrive", "specs": {
        "amount": (1.0, 50.0, "distortion drive"), "mix": (0.0, 1.0, "wet amount")},
        "defaults": {"amount": 6.0, "mix": 0.6}},
    # --- sampler (hidden: created by a `sample` capture, not the +bar) -----------
    "sampler": {"role": "source", "def": "sampler", "hidden": True, "specs": {
        "rate": (0.25, 4.0, "playback speed / pitch (1 = as recorded)"),
        "amp":  (0.0, 1.0, "sample level")},
        "defaults": {"rate": 1.0, "amp": 0.6}},
}

# the one param per node that acts as its gain/bypass: set it to 0 and a source goes
# silent, an insert effect passes audio straight through. start/stop flips an
# `enabled` flag whose ONLY effect is that the engine sends 0 for this param — the
# stored value is untouched, so "start" restores the sound exactly.
BYPASS_PARAM_FIXED = {"drone": "amp", "reverb": "mix"}
BYPASS_PARAM_TYPE = {"drum": "level", "seq": "amp",
                     "kick": "level", "snare": "level", "hat": "level", "clap": "level",
                     "delay": "mix", "tremolo": "depth", "drive": "mix",
                     "sampler": "amp"}

INITIAL = {
    "drone": {
        "freq": 55.0, "detune": 0.08, "cutoff": 700.0, "res": 0.35,
        "sub": 0.35, "noise": 0.04, "drive": 1.4,
        "lfoRate": 0.08, "lfoDepth": 0.25, "amp": 0.32,
    },
    "reverb": {"mix": 0.32, "room": 0.72, "damp": 0.5, "amp": 0.9},
}


class Graph:
    def __init__(self):
        self.params = {n: dict(p) for n, p in INITIAL.items()}
        self.modules = []          # ordered [{key, type, role, params, id}]
        self.enabled = {}          # node key -> bool; absent = running (True)
        self._counters = {}

    # ---- lookup -------------------------------------------------------------
    def _mod(self, key):
        return next((m for m in self.modules if m["key"] == key), None)

    def specs_for(self, node):
        if node in PARAM_SPECS:
            return PARAM_SPECS[node]
        m = self._mod(node)
        return MODULE_REGISTRY[m["type"]]["specs"] if m else None

    def node_params(self, node):
        if node in self.params:
            return self.params[node]
        m = self._mod(node)
        return m["params"] if m else None

    def node_keys(self):
        srcs = [m["key"] for m in self.modules if m["role"] == "source"]
        fx = [m["key"] for m in self.modules if m["role"] == "effect"]
        return ["drone"] + srcs + fx + ["reverb"]

    # ---- edits --------------------------------------------------------------
    def clamp(self, node, param, value):
        lo, hi, _ = self.specs_for(node)[param]
        return max(lo, min(hi, float(value)))

    def set(self, node, param, value):
        specs = self.specs_for(node)
        if specs is None or param not in specs:
            raise KeyError(f"{node}.{param}")
        store = self.node_params(node)
        old = store[param]
        new = self.clamp(node, param, value)
        store[param] = new
        return old, new

    def add_module(self, mtype):
        if mtype not in MODULE_REGISTRY:
            raise KeyError(f"unknown module type: {mtype}")
        reg = MODULE_REGISTRY[mtype]
        self._counters[mtype] = self._counters.get(mtype, 0) + 1
        key = f"{mtype}{self._counters[mtype]}"
        mod = {"key": key, "type": mtype, "role": reg["role"],
               "params": dict(reg["defaults"]), "id": None}
        self.modules.append(mod)
        return mod

    def add_sampler(self, buf):
        """A sampler is an add_module bound to a captured buffer number."""
        mod = self.add_module("sampler")
        mod["buf"] = int(buf)
        return mod

    def remove_module(self, key):
        m = self._mod(key)
        if m:
            self.modules.remove(m)
            self.enabled.pop(key, None)
        return m

    # ---- start / stop (non-destructive mute/bypass) -------------------------
    def bypass_param(self, node):
        if node in BYPASS_PARAM_FIXED:
            return BYPASS_PARAM_FIXED[node]
        m = self._mod(node)
        return BYPASS_PARAM_TYPE.get(m["type"]) if m else None

    def is_enabled(self, node):
        return self.enabled.get(node, True)

    def set_enabled(self, node, on):
        if node not in self.node_keys():
            raise KeyError(node)
        self.enabled[node] = bool(on)
        return self.enabled[node]

    def toggle(self, node):
        return self.set_enabled(node, not self.is_enabled(node))

    def resolve_node(self, node_raw):
        """Like resolve() but node-only — for ops that name a module with no param."""
        tokens = [t for t in str(node_raw or "").split(".") if t]
        node = next((t for t in tokens if t in self.node_keys()), None)
        if node is None:
            for t in tokens:
                matches = [m["key"] for m in self.modules if m["type"] == t]
                if len(matches) == 1:
                    node = matches[0]
                    break
        if node is None:
            raise KeyError(f"no known node in {node_raw!r}")
        return node

    def resolve(self, node_raw, param_raw):
        """Find a real (node, param) from whatever the model sent — it may dot things
        together, or name a module by type ('seq') instead of key ('seq1')."""
        tokens = []
        for s in (node_raw, param_raw):
            if s:
                tokens += str(s).split(".")
        keys = self.node_keys()
        node = next((t for t in tokens if t in keys), None)
        if node is None:
            for t in tokens:
                matches = [m["key"] for m in self.modules if m["type"] == t]
                if len(matches) == 1:
                    node = matches[0]
                    break
        if node is None:
            raise KeyError(f"no known node in {node_raw!r}/{param_raw!r}")
        specs = self.specs_for(node)
        param = next((t for t in tokens if t in specs), None)
        if param is None:
            raise KeyError(f"no known param in {node_raw!r}/{param_raw!r}")
        return node, param

    # ---- text for the agent / the human ------------------------------------
    def catalog(self):
        lines = []
        for node in self.node_keys():
            specs, cur = self.specs_for(node), self.node_params(node)
            m = self._mod(node)
            label = f"{node} (a {m['type']})" if m else node
            step_keys = sorted((p for p in specs if p.startswith("step")),
                               key=lambda s: int(s[4:]))
            for p, (lo, hi, desc) in specs.items():
                if p.startswith("step"):
                    continue
                lines.append(f"  {label}.{p} = {cur[p]:g}  [{lo:g}..{hi:g}]  {desc}")
            if step_keys:                                     # compact the 8/16-step lanes
                if all(specs[k][1] <= 1.0 for k in step_keys):
                    pat = "".join("x" if cur[k] > 0 else "." for k in step_keys)
                    lines.append(f"  {label}.steps = {pat}  (set stepN 1=hit 0=rest)")
                else:
                    notes = " ".join(f"{cur[k]:g}" for k in step_keys)
                    lines.append(f"  {label}.steps = [{notes}]  (MIDI notes, 0=rest; set stepN)")
        return "\n".join(lines)

    def module_menu(self):
        parts = []
        for t, reg in MODULE_REGISTRY.items():
            if reg.get("hidden"):
                continue
            names = [p for p in reg["specs"] if not p.startswith("step")]
            if any(p.startswith("step") for p in reg["specs"]):
                names.append("step0..N")
            parts.append(f"{t} [{reg['role']}] ({'/'.join(names)})")
        return "; ".join(parts)

    def save(self, path):
        with open(path, "w") as f:
            json.dump({"params": self.params, "modules": self.modules,
                       "enabled": self.enabled}, f, indent=2)

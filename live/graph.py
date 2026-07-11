"""The patch state — the single source of truth. The agent and the keyboard both
edit THIS; the engine reconciles the running sound to match it.

The chain is drone -> [insertable effects, in order] -> reverb. drone and reverb
are fixed endpoints; effects are added/removed by conversation (Layer-1 modularity).
"""
import json

# fixed endpoints: node -> param -> (min, max, description-for-the-agent)
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
        "amp":      (0.0, 0.6, "drone level"),
    },
    "reverb": {
        "mix":  (0.0, 1.0, "wet/dry = amount of space"),
        "room": (0.0, 1.0, "room size (tail length)"),
        "damp": (0.0, 1.0, "high-freq damping (0 bright .. 1 dark)"),
        "amp":  (0.0, 1.0, "master output level"),
    },
}

# insertable effect types: type -> param specs, plus a matching defaults table.
EFFECT_SPECS = {
    "delay":   {"time": (0.02, 1.0, "delay time in s"),
                "fb":   (0.0, 0.9, "feedback / number of repeats"),
                "mix":  (0.0, 1.0, "wet amount")},
    "tremolo": {"rate":  (0.1, 12.0, "tremolo rate in Hz"),
                "depth": (0.0, 1.0, "tremolo depth")},
    "drive":   {"amount": (1.0, 50.0, "distortion drive"),
                "mix":    (0.0, 1.0, "wet amount")},
}
EFFECT_DEFAULTS = {
    "delay":   {"time": 0.3, "fb": 0.4, "mix": 0.4},
    "tremolo": {"rate": 5.0, "depth": 0.5},
    "drive":   {"amount": 6.0, "mix": 0.6},
}
# type -> the compiled SynthDef name
EFFECT_DEF = {"delay": "fxDelay", "tremolo": "fxTremolo", "drive": "fxDrive"}

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
        self.effects = []          # ordered list of {key, type, params, id} (id set by engine)
        self._counters = {}

    # ---- lookup -------------------------------------------------------------
    def _fx(self, key):
        return next((e for e in self.effects if e["key"] == key), None)

    def specs_for(self, node):
        if node in PARAM_SPECS:
            return PARAM_SPECS[node]
        fx = self._fx(node)
        return EFFECT_SPECS[fx["type"]] if fx else None

    def node_params(self, node):
        if node in self.params:
            return self.params[node]
        fx = self._fx(node)
        return fx["params"] if fx else None

    def node_keys(self):
        return ["drone"] + [e["key"] for e in self.effects] + ["reverb"]

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

    def add_effect(self, etype):
        if etype not in EFFECT_SPECS:
            raise KeyError(f"unknown effect type: {etype}")
        self._counters[etype] = self._counters.get(etype, 0) + 1
        key = f"{etype}{self._counters[etype]}"
        fx = {"key": key, "type": etype, "params": dict(EFFECT_DEFAULTS[etype]), "id": None}
        self.effects.append(fx)
        return fx

    def remove_effect(self, key):
        fx = self._fx(key)
        if fx:
            self.effects.remove(fx)
        return fx

    def resolve(self, node_raw, param_raw):
        """Find a real (node, param) from whatever the model sent. LLMs are sloppy:
        they send node='drone.cutoff'/param='cutoff', refer to an effect by its type
        ('delay') instead of key ('delay1'), or dot everything together."""
        tokens = []
        for s in (node_raw, param_raw):
            if s:
                tokens += str(s).split(".")
        keys = self.node_keys()
        node = next((t for t in tokens if t in keys), None)
        if node is None:  # allow referring to an effect by its type if unambiguous
            for t in tokens:
                matches = [e["key"] for e in self.effects if e["type"] == t]
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
            label = node
            fx = self._fx(node)
            if fx:
                label = f"{node} (a {fx['type']})"
            for p, (lo, hi, desc) in specs.items():
                lines.append(f"  {label}.{p} = {cur[p]:g}  [{lo:g}..{hi:g}]  {desc}")
        return "\n".join(lines)

    def effect_menu(self):
        return ", ".join(f"{t} ({'/'.join(EFFECT_SPECS[t])})" for t in EFFECT_SPECS)

    def save(self, path):
        with open(path, "w") as f:
            json.dump({"params": self.params, "effects": self.effects}, f, indent=2)

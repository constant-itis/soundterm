"""The patch state — the single source of truth. The agent and the keyboard both
edit THIS; the engine reconciles the running sound to match it.

Phase 1 keeps the graph tiny and fixed (drone -> reverb), but it's already a real
node/param model: values live here, get clamped here, and serialize to disk here.
"""
import json

# node -> param -> (min, max, description-for-the-agent)
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

# A pleasant starting drone so the app makes a good sound the instant it opens.
INITIAL = {
    "drone": {
        "freq": 55.0, "detune": 0.08, "cutoff": 700.0, "res": 0.35,
        "sub": 0.35, "noise": 0.04, "drive": 1.4,
        "lfoRate": 0.08, "lfoDepth": 0.25, "amp": 0.32,
    },
    "reverb": {"mix": 0.32, "room": 0.72, "damp": 0.5, "amp": 0.9},
}


def resolve(node_raw, param_raw):
    """Find a real (node, param) from whatever the model sent. LLMs are sloppy about
    the split — they send node='drone.cutoff'/param='cutoff', or even both fields as
    'drone.freq'. Tokenize everything on '.' and pick the node+param that actually
    exist in the spec."""
    tokens = []
    for s in (node_raw, param_raw):
        if s:
            tokens += str(s).split(".")
    node = next((t for t in tokens if t in PARAM_SPECS), None)
    if not node:
        raise KeyError(f"no known node in {node_raw!r}/{param_raw!r}")
    param = next((t for t in tokens if t in PARAM_SPECS[node]), None)
    if not param:
        raise KeyError(f"no known param in {node_raw!r}/{param_raw!r}")
    return node, param


class Graph:
    def __init__(self):
        # deep-ish copy of INITIAL
        self.params = {n: dict(p) for n, p in INITIAL.items()}

    def clamp(self, node, param, value):
        lo, hi, _ = PARAM_SPECS[node][param]
        return max(lo, min(hi, float(value)))

    def set(self, node, param, value):
        """Validate + clamp a single param. Returns (old, new) or raises KeyError."""
        if node not in PARAM_SPECS or param not in PARAM_SPECS[node]:
            raise KeyError(f"{node}.{param}")
        old = self.params[node][param]
        new = self.clamp(node, param, value)
        self.params[node][param] = new
        return old, new

    def catalog(self):
        """Human/agent-readable list of params, ranges and current values."""
        lines = []
        for node, specs in PARAM_SPECS.items():
            for p, (lo, hi, desc) in specs.items():
                cur = self.params[node][p]
                lines.append(f"  {node}.{p} = {cur:g}  [{lo:g}..{hi:g}]  {desc}")
        return "\n".join(lines)

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.params, f, indent=2)

    def load(self, path):
        with open(path) as f:
            data = json.load(f)
        for node, ps in data.items():
            for p, v in ps.items():
                if node in PARAM_SPECS and p in PARAM_SPECS[node]:
                    self.params[node][p] = self.clamp(node, p, v)

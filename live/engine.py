"""Engine: owns the scsynth process and reconciles the running sound to the Graph.

Nothing here reasons about music — it boots the server, wires the drone->fx->reverb
chain through a private bus, spawns/frees effects in order, and pushes param changes.
"""
import os
import subprocess
import time

from graph import MODULE_REGISTRY
from osc import Client

HERE = os.path.dirname(os.path.abspath(__file__))
DEFDIR = os.path.join(HERE, "defs")
LOG = "/tmp/soundterm-scsynth.log"

PORT = 57110
FX_BUS = 16            # private stereo audio bus (16,17) — above hardware I/O
DRONE_ID = 1000
REVERB_ID = 1001
FX_ID_BASE = 1100      # effect node ids count up from here
ADD_TO_HEAD = 0
ADD_TO_TAIL = 1
ADD_BEFORE = 2
ADD_AFTER = 3


class Engine:
    def __init__(self, graph):
        self.graph = graph
        self.proc = None
        self.osc = None
        self._next_fx_id = FX_ID_BASE
        self._next_buf = 0            # sample buffers count up from 0
        self.sr = 48000.0             # server sample rate, read on boot

    # ---- lifecycle ----------------------------------------------------------
    def boot(self):
        env = dict(os.environ, SC_JACK_DEFAULT_OUTPUTS="system:playback_1,system:playback_2")
        logf = open(LOG, "w")
        self.proc = subprocess.Popen(
            ["pw-jack", "scsynth", "-u", str(PORT)],
            stdout=logf, stderr=subprocess.STDOUT, env=env,
        )
        self._wait_ready()
        self.osc = Client("127.0.0.1", PORT)
        self._load_defs()
        self.sr = self._read_sr()
        # drone at head of root group; reverb right after it. Effects insert between.
        self.osc.send("/s_new", "droneVoice", DRONE_ID, ADD_TO_HEAD, 0, "out", FX_BUS)
        self.osc.send("/s_new", "fxReverb", REVERB_ID, ADD_AFTER, DRONE_ID, "in", FX_BUS, "out", 0)
        early = self.osc.recv(0.3)
        if early and early[0] == "/fail":
            raise RuntimeError(f"node spawn failed: {early[1]}")
        self.reconcile_all()

    def _wait_ready(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"scsynth died on boot — see {LOG}")
            try:
                with open(LOG) as f:
                    if "server ready" in f.read():
                        return
            except FileNotFoundError:
                pass
            time.sleep(0.15)
        raise RuntimeError(f"scsynth not ready in {timeout}s — see {LOG}")

    def _load_defs(self):
        # /d_loadDir is reliable (single-file /d_load no-ops on scsynth 3.11);
        # confirm via /status because /done alone can lie. 13 defs expected.
        self.osc.send("/d_loadDir", DEFDIR)
        self.osc.wait_for("/done", 4.0)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            self.osc.send("/status")
            if self.osc.wait_for("/status.reply", 2.0)[4] >= 13:
                return
            time.sleep(0.1)
        raise RuntimeError("synthdefs did not register")

    def _read_sr(self):
        """Nominal sample rate from /status.reply (arg index 7, an OSC double)."""
        try:
            self.osc.send("/status")
            return float(self.osc.wait_for("/status.reply", 2.0)[7]) or 48000.0
        except (TimeoutError, IndexError, ValueError):
            return 48000.0

    # ---- node ids -----------------------------------------------------------
    def _node_id(self, node):
        if node == "drone":
            return DRONE_ID
        if node == "reverb":
            return REVERB_ID
        m = self.graph._mod(node)
        return m["id"] if m else None

    # ---- param reconcile ----------------------------------------------------
    def _effective(self, node, param, value):
        """The value actually sent. A stopped node sends 0 for its bypass param
        (silent source / dry-through effect); every other param passes unchanged."""
        if param == self.graph.bypass_param(node) and not self.graph.is_enabled(node):
            return 0.0
        return float(value)

    def push(self, node, param, value):
        nid = self._node_id(node)
        if nid is not None:
            self.osc.send("/n_set", nid, param, self._effective(node, param, value))

    def apply_enabled(self, node):
        """Re-push the node's bypass param so a start/stop toggle takes effect."""
        bp = self.graph.bypass_param(node)
        if bp is not None:
            self.push(node, bp, self.graph.node_params(node)[bp])

    def reconcile_all(self):
        for node in self.graph.node_keys():
            for p, v in self.graph.node_params(node).items():
                self.push(node, p, v)

    # ---- modules (voices + effects) ----------------------------------------
    def spawn_module(self, mod):
        """Insert a just-added module into the live chain. Source voices ADD onto the
        bus and go right after the drone; effects process the bus right before reverb.
        Both placements keep the order drone -> sources -> effects -> reverb."""
        reg = MODULE_REGISTRY[mod["type"]]
        mod["id"] = self._next_fx_id
        self._next_fx_id += 1
        if reg["role"] == "source":
            args = [reg["def"], mod["id"], ADD_AFTER, DRONE_ID, "out", FX_BUS]
            if mod["type"] == "sampler":
                args += ["buf", int(mod.get("buf", 0))]
            self.osc.send("/s_new", *args)
        else:
            self.osc.send("/s_new", reg["def"], mod["id"], ADD_BEFORE, REVERB_ID, "bus", FX_BUS)
        early = self.osc.recv(0.2)
        if early and early[0] == "/fail":
            raise RuntimeError(f"module spawn failed: {early[1]}")
        for p, v in mod["params"].items():
            self.osc.send("/n_set", mod["id"], p, float(v))

    def free_module(self, mod):
        if mod and mod.get("id") is not None:
            self.osc.send("/n_free", mod["id"])

    # ---- sampling -----------------------------------------------------------
    def start_capture(self, seconds=4.0, in_bus=0):
        """Rip `seconds` of the live stereo master (bus `in_bus`) into a fresh
        buffer. Returns (bufnum, seconds); the recorder self-frees when full. The
        caller waits ~seconds, then spawns a sampler bound to the returned buffer."""
        buf = self._next_buf
        self._next_buf += 1
        frames = max(1, int(self.sr * seconds))
        self.osc.send("/b_alloc", buf, frames, 2)
        self.osc.wait_for("/done", 4.0)
        rid = self._next_fx_id
        self._next_fx_id += 1
        self.osc.send("/s_new", "capture", rid, ADD_TO_TAIL, 0, "buf", buf, "in", in_bus)
        early = self.osc.recv(0.2)
        if early and early[0] == "/fail":
            raise RuntimeError(f"capture failed: {early[1]}")
        return buf, seconds

    def panic(self):
        self.osc.send("/n_set", DRONE_ID, "amp", 0.0)

    def shutdown(self):
        try:
            if self.osc:
                self.osc.send("/g_freeAll", 0)
                self.osc.send("/quit")
                self.osc.close()
        except OSError:
            pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

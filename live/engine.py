"""Engine: owns the scsynth process and reconciles the running sound to the Graph.

Nothing here reasons about music — it just boots the server, wires the fixed
drone->reverb chain through a private bus, and pushes param changes over OSC.
"""
import os
import subprocess
import time

from osc import Client

HERE = os.path.dirname(os.path.abspath(__file__))
DEFDIR = os.path.join(HERE, "defs")
LOG = "/tmp/foundry-scsynth.log"

PORT = 57110
FX_BUS = 16            # private stereo audio bus (16,17) — above hardware I/O
DRONE_ID = 1000
REVERB_ID = 1001
ADD_TO_HEAD = 0
ADD_AFTER = 3


class Engine:
    def __init__(self, graph):
        self.graph = graph
        self.proc = None
        self.osc = None

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
        self._spawn_nodes()
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
        # /d_loadDir on the folder is reliable (single-file /d_load is a no-op on
        # scsynth 3.11); confirm via /status because /done alone can lie.
        self.osc.send("/d_loadDir", DEFDIR)
        self.osc.wait_for("/done", 4.0)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            self.osc.send("/status")
            if self.osc.wait_for("/status.reply", 2.0)[4] >= 2:
                return
            time.sleep(0.1)
        raise RuntimeError("synthdefs did not register")

    def _spawn_nodes(self):
        # drone -> FX_BUS (head of root group); reverb reads FX_BUS -> out 0, placed
        # right AFTER the drone so it processes in the correct order.
        self.osc.send("/s_new", "droneVoice", DRONE_ID, ADD_TO_HEAD, 0, "out", FX_BUS)
        self.osc.send("/s_new", "fxReverb", REVERB_ID, ADD_AFTER, DRONE_ID,
                      "in", FX_BUS, "out", 0)
        early = self.osc.recv(0.3)
        if early and early[0] == "/fail":
            raise RuntimeError(f"node spawn failed: {early[1]}")

    def _node_id(self, node):
        return DRONE_ID if node == "drone" else REVERB_ID

    def push(self, node, param, value):
        """Send one param to the live node (value already clamped by the Graph)."""
        self.osc.send("/n_set", self._node_id(node), param, float(value))

    def reconcile_all(self):
        for node, ps in self.graph.params.items():
            for p, v in ps.items():
                self.push(node, p, v)

    def panic(self):
        """Duck everything to silence without tearing the graph down."""
        for node in self.graph.params:
            self.osc.send("/n_set", self._node_id(node), "amp", 0.0)

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

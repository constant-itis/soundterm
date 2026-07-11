"""The agent: turns a spoken instruction into graph-ops.

It emits the SAME ops the keyboard would — it's a peer editor of the Graph, never a
special path to the audio. Two swappable backends:
  - "local": the 35B on evo-x2 (OpenAI-compatible, no auth) — fast, free, junior
  - a Claude model ("opus"/"sonnet"/"haiku" or a full id): shells out to the `claude`
    CLI in print mode, using your subscription auth (no API key, no per-token bill)
"""
import json
import re
import subprocess
import urllib.request

LOCAL_ENDPOINT = "http://192.168.1.152:8100/v1/chat/completions"
LOCAL_MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

SYSTEM = """You are the control brain of a live modular synthesizer that is already \
playing. The signal chain is: drone -> [source voices] -> [effects] -> reverb. The \
user describes how they want the sound to change; you respond with operations.

ALWAYS reply with ONLY a JSON object (no prose outside it, no code fence). Even when
you are just talking or have nothing to change, reply with empty ops and put your
message in "say":
{"ops": [ <op>, ... ], "say": "<short lowercase message>"}

Each op is one of:
  {"op": "set", "node": "<node>", "param": "<param>", "value": <number>}
  {"op": "add", "type": "<module type>"}
  {"op": "remove", "node": "<module node>"}

Rules:
- For "set", use ABSOLUTE values within range. Read the CURRENT values below and
  compute the new absolute value for relative requests ("darker", "more space").
- To add RHYTHM add a "drum"; to play/sequence NOTES add a "seq". Add a module only
  when the chain lacks that capability; otherwise just set params on what's there.
- A "seq" has step0..step7, each a MIDI note (0 = rest). To play a melody, set the
  steps: middle C is 60, c3=48, so "c3 e3 g3" -> step0=48, step1=52, step2=55, rest 0.
- If the user asks for something impossible, do it the closest supported way and say
  so briefly. Keep moves musical. Multiple ops per reply are fine.
- Use exact node/param names. Never invent params.

CURRENT PATCH (node.param = value [min..max] meaning):
{catalog}

MODULES YOU CAN ADD (type [role] (params)): {modules}"""


class Agent:
    def __init__(self, backend="local"):
        self.backend = backend

    def act(self, graph, text):
        """Return (ops:list[dict], say:str). Raises on transport/parse failure."""
        sys_prompt = (SYSTEM
                      .replace("{catalog}", graph.catalog())
                      .replace("{modules}", graph.module_menu()))
        if self.backend == "local":
            content = self._local(sys_prompt, text)
        else:
            content = self._claude(sys_prompt, text, self.backend)
        return self._parse(content)

    def _local(self, sys_prompt, text):
        payload = {
            "model": LOCAL_MODEL,
            "messages": [{"role": "system", "content": sys_prompt},
                         {"role": "user", "content": text}],
            "temperature": 0.3, "max_tokens": 400,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(
            LOCAL_ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)["choices"][0]["message"]["content"]

    def _claude(self, sys_prompt, text, model):
        # print mode + replaced system prompt = a clean one-shot LLM call under the
        # subscription. `claude-*` full ids and aliases (opus/sonnet/haiku) both work.
        out = subprocess.run(
            ["claude", "-p", text, "--system-prompt", sys_prompt,
             "--model", model, "--output-format", "json"],
            capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {out.stderr.strip()[:200]}")
        return json.loads(out.stdout).get("result", "")

    @staticmethod
    def _parse(content):
        # if the model chatted instead of emitting JSON, don't crash — surface its
        # words as the reply with no ops (a no-op turn).
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return [], content.strip()[:300]
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return [], content.strip()[:300]
        return (data.get("ops", []) or []), (data.get("say", "") or "")

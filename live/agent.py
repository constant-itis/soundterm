"""The agent: turns a spoken instruction into graph-ops.

It emits the SAME ops the keyboard would (set a node's param) — it is a peer
editor of the Graph, never a special path to the audio. Driven by the local 35B
(OpenAI-compatible, no auth); swap ENDPOINT/MODEL for Claude with no other change.
"""
import json
import re
import urllib.request

ENDPOINT = "http://192.168.1.152:8100/v1/chat/completions"
MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"

SYSTEM = """You are the control brain of a live modular drone synthesizer that is \
already playing. The user describes how they want the sound to change. You respond \
by setting parameters.

Reply with ONLY a JSON object, no prose, no code fence:
{"ops": [{"node": "<node>", "param": "<param>", "value": <number>}, ...], "say": "<short confirmation>"}

Rules:
- Use ABSOLUTE values within each param's range. Read the CURRENT values below and
  compute the new absolute value for relative requests ("darker", "more space").
- Change only what the request implies; keep moves musical (small nudges unless
  they ask for a big change). You may set several params in one response.
- "say" is one short lowercase phrase describing what you did.
- Only use the exact node and param names listed. Never invent params.

PARAMS (node.param = current [min..max] meaning):
{catalog}"""


class Agent:
    def __init__(self, endpoint=ENDPOINT, model=MODEL):
        self.endpoint = endpoint
        self.model = model

    def act(self, graph, text):
        """Return (ops:list[dict], say:str). Raises on transport/parse failure."""
        sys_prompt = SYSTEM.replace("{catalog}", graph.catalog())
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
            "max_tokens": 400,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.load(resp)
        content = body["choices"][0]["message"]["content"]
        return self._parse(content)

    @staticmethod
    def _parse(content):
        # tolerate ```json fences / stray prose: grab the largest {...} span
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            raise ValueError(f"no JSON in model reply: {content!r}")
        data = json.loads(m.group(0))
        ops = data.get("ops", []) or []
        say = data.get("say", "") or ""
        return ops, say

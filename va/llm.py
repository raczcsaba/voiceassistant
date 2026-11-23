"""LLM backends. Each exposes .name, .load(), .run(text) -> {"calls": [...], "text": str}, .unload()."""
import json
import os
import pathlib

import requests

from .common import COVERS, DEVICES, ROOMS, SCENES, TOOLS

OPENAI_TOOLS = [{"type": "function", "function": t} for t in TOOLS]
WARMUP = "Turn on the kitchen light."


class Ollama:
    def __init__(self, model, system, think=False, host="http://localhost:11434"):
        self.model, self.system, self.think, self.host = model, system, think, host
        self.name = f"ollama:{model}"
        self._s = requests.Session()

    def _chat(self, text):
        # Small context + short output cap: a tool call is ~20-60 tokens, the prompt ~600.
        body = {"model": self.model, "stream": False, "keep_alive": -1, "tools": OPENAI_TOOLS,
                "options": {"temperature": 0, "num_predict": 96, "num_ctx": 2048},
                "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": text}]}
        if self._think_ok:
            body["think"] = self.think
        r = self._s.post(f"{self.host}/api/chat", json=body, timeout=120)
        if r.status_code == 400 and "think" in r.text and self._think_ok:
            self._think_ok = False  # model has no thinking switch
            return self._chat(text)
        r.raise_for_status()
        return r.json()

    def load(self):
        self._think_ok = True
        self._chat(WARMUP)  # loads weights + caches the system/tools prefix

    def run(self, text):
        msg = self._chat(text)["message"]
        calls = [{"name": c["function"]["name"], "args": _as_dict(c["function"].get("arguments"))}
                 for c in msg.get("tool_calls") or []]
        return {"calls": calls, "text": msg.get("content", "")}

    def unload(self):
        self._s.post(f"{self.host}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=30)


class OllamaJSON(Ollama):
    """Same models, but no native tool calling: the output is forced (grammar-constrained) into one flat
    command object whose fields can only take valid values. Tiny models can't invent ids or malformed calls,
    and the output is ~25 tokens. Works with models that have no tool template at all."""

    SCHEMA = {"type": "object", "properties": {
        "tool": {"type": "string", "enum": [t["name"] for t in TOOLS] + ["none"]},
        "target": {"type": "string", "enum": ROOMS + DEVICES + COVERS + SCENES + ["none"]},
        "action": {"type": "string", "enum": ["on", "off", "open", "close", "stop", "lock", "unlock", "set", "get"]},
        "value": {"type": ["integer", "null"]},
        "attribute": {"type": "string", "enum": ["temperature", "humidity", "state", "none"]}},
        "required": ["tool", "target", "action", "value", "attribute"]}

    def __init__(self, model, system):
        super().__init__(model, system + "\n\n" + JSON_GUIDE)
        self.name = f"ollama-json:{model}"

    def _chat(self, text):
        body = {"model": self.model, "stream": False, "keep_alive": -1, "think": False, "format": self.SCHEMA,
                "options": {"temperature": 0, "num_predict": 64, "num_ctx": 2048},
                "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": text}]}
        r = self._s.post(f"{self.host}/api/chat", json=body, timeout=120)
        if r.status_code == 400 and "think" in r.text:
            body.pop("think")
            r = self._s.post(f"{self.host}/api/chat", json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    def run(self, text):
        msg = self._chat(text)["message"]
        c = _as_dict(msg.get("content"))
        call = flat_to_call(c)
        return {"calls": [call] if call else [], "text": "" if call else msg.get("content", "")}


def flat_to_call(c):
    t, tgt, act, val = c.get("tool"), c.get("target"), c.get("action"), c.get("value")
    if t == "control_light":
        a = {"room": tgt, "action": "off" if act == "off" else "on"}
        if val is not None:
            a["brightness"] = val
        return {"name": t, "args": a}
    if t == "set_climate":
        return {"name": t, "args": {"room": tgt, "temperature": val}}
    if t == "control_cover":
        return {"name": t, "args": {"cover": tgt, "action": act}}
    if t == "control_device":
        return {"name": t, "args": {"device": tgt, "action": act}}
    if t == "activate_scene":
        return {"name": t, "args": {"scene": tgt}}
    if t == "get_state":
        return {"name": t, "args": {"target": tgt, "attribute": c.get("attribute")}}
    return None


JSON_GUIDE = f"""Reply with one JSON command.
tools: control_light(target=room, action=on/off, value=brightness 0-100 or null), set_climate(target=room, value=degrees C),
control_cover(target=cover, action=open/close/stop), control_device(target=device, action=on/off/lock/unlock),
activate_scene(target=scene), get_state(target=room or device, attribute=temperature/humidity/state), none.
rooms: {", ".join(ROOMS)}. devices: {", ".join(DEVICES)}. covers: {", ".join(COVERS)}. scenes: {", ".join(SCENES)}.
Examples:
"switch on the garage light" -> {{"tool":"control_light","target":"garage","action":"on","value":null,"attribute":"none"}}
"bathroom lights to 30 percent" -> {{"tool":"control_light","target":"bathroom","action":"on","value":30,"attribute":"none"}}
"make it 21 degrees in the bedroom" -> {{"tool":"set_climate","target":"bedroom","action":"set","value":21,"attribute":"none"}}
"lower the living room blinds" -> {{"tool":"control_cover","target":"living_room_blinds","action":"close","value":null,"attribute":"none"}}
"unlock the front door" -> {{"tool":"control_device","target":"front_door_lock","action":"unlock","value":null,"attribute":"none"}}
"switch the fan off" -> {{"tool":"control_device","target":"fan","action":"off","value":null,"attribute":"none"}}
"good night" -> {{"tool":"activate_scene","target":"good_night","action":"set","value":null,"attribute":"none"}}
"how humid is the bathroom" -> {{"tool":"get_state","target":"bathroom","action":"get","value":null,"attribute":"humidity"}}"""


class OpenAICompat:
    """Groq (or any OpenAI-compatible endpoint)."""

    def __init__(self, model, system, base_url="https://api.groq.com/openai/v1", key_env="GROQ_API_KEY", label="groq", extra=None):
        self.model, self.system, self.base_url, self.key_env, self.extra = model, system, base_url, key_env, extra or {}
        self.name = f"{label}:{model}"

    def load(self):
        from openai import OpenAI
        self._c = OpenAI(base_url=self.base_url, api_key=os.environ[self.key_env])
        self.run(WARMUP)  # open the HTTPS connection

    def run(self, text):
        r = self._c.chat.completions.create(
            model=self.model, temperature=0, tools=OPENAI_TOOLS, tool_choice="auto",
            messages=[{"role": "system", "content": self.system}, {"role": "user", "content": text}],
            **self.extra)
        m = r.choices[0].message
        calls = [{"name": c.function.name, "args": _as_dict(c.function.arguments)} for c in m.tool_calls or []]
        return {"calls": calls, "text": m.content or ""}

    def unload(self):
        pass


class Claude:
    def __init__(self, model, system, effort="low", thinking=None):
        self.model, self.system, self.effort, self.thinking = model, system, effort, thinking
        self.name = f"claude:{model}" + (f":{thinking['type']}" if thinking else "") + f":{effort}"

    def load(self):
        import anthropic
        self._c = anthropic.Anthropic()
        self._tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in TOOLS]
        self.run(WARMUP)  # open the HTTPS connection

    def run(self, text):
        kw = {"thinking": self.thinking} if self.thinking else {}
        r = self._c.messages.create(
            model=self.model, max_tokens=1024, system=self.system, tools=self._tools,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": text}], **kw)
        calls = [{"name": b.name, "args": b.input} for b in r.content if b.type == "tool_use"]
        txt = "".join(b.text for b in r.content if b.type == "text")
        return {"calls": calls, "text": txt}

    def unload(self):
        pass


def _as_dict(a):
    if isinstance(a, dict):
        return a
    try:
        return json.loads(a or "{}")
    except json.JSONDecodeError:
        return {}


# Local candidates, smallest first. Sizes are download sizes.
LOCAL = {
    "functiongemma-270m": "functiongemma:270m",                          # 0.3 GB, Google, built for function calling
    "granite4-350m": "granite4:350m",                                    # 0.7 GB, IBM, tool calling
    "lfm2-350m": "hf.co/LiquidAI/LFM2-350M-GGUF:Q8_0",                   # 0.4 GB, Liquid AI
    "lfm2.5-1.2b": "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M",    # 0.7 GB, Liquid AI
    "lfm2-1.2b-tool": "hf.co/LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_K_M",       # 0.7 GB, Liquid AI tool-use tune
    "qwen3.5-0.8b": "qwen3.5:0.8b",                                      # 1.3 GB
    "llama3.2-1b": "llama3.2:1b",                                        # 1.3 GB
    "qwen3.5-2b": "qwen3.5:2b",                                          # 2.7 GB, reference from round 1
}


# In-process MLX + constrained compact decoding (va/fastnlu.py). HF repo ids.
MLX = {
    "mlx-granite-350m": "ibm-granite/granite-4.0-350m",
    "mlx-granite-h-350m-8bit": "mlx-community/granite-4.0-h-350m-8bit",
    "mlx-lfm2-350m-8bit": "mlx-community/LFM2-350M-8bit",
    "mlx-lfm2.5-350m-8bit": "mlx-community/LFM2.5-350M-8bit",
    "mlx-functiongemma-8bit": "mlx-community/functiongemma-270m-it-8bit",
    "mlx-lfm2-700m-8bit": "mlx-community/LFM2-700M-8bit",
    "mlx-qwen3.5-0.8b-8bit": "mlx-community/Qwen3.5-0.8B-8bit",
    "mlx-lfm2.5-1.2b-4bit": "mlx-community/LFM2.5-1.2B-Instruct-4bit",
}

# LoRA adapter merged into the weights (mlx_lm fuse) and re-quantized: train/README in the main README.
FUSED = {
    "granite-cmd-q4": "models/granite-350m-cmd-q4",
    "granite-cmd-q8": "models/granite-350m-cmd-q8",
    "granite-cmd-bf16": "models/granite-350m-cmd",
}

# Same parser + a LoRA adapter trained on synthetic commands (train/), no few-shot examples needed.
FINETUNED = {
    "mlx-qwen3.5-0.8b-ft": ("mlx-community/Qwen3.5-0.8B-8bit", "adapters/qwen3.5-0.8b"),
    "mlx-lfm2.5-350m-ft": ("mlx-community/LFM2.5-350M-8bit", "adapters/lfm2.5-350m"),
    "mlx-granite-350m-ft": ("ibm-granite/granite-4.0-350m", "adapters/granite-350m"),
}
DEFAULT = "granite-cmd-q8" if pathlib.Path(FUSED["granite-cmd-q8"]).exists() else "mlx-qwen3.5-0.8b-8bit"

NO_TOOLS = {"lfm2-350m"}  # GGUF has no tool template in Ollama -> JSON mode only


def available(system):
    from .fastnlu import MlxCommandParser
    b = {k: (lambda r=r: MlxCommandParser(r)) for k, r in MLX.items()}
    for k, (r, ad) in FINETUNED.items():
        if (pathlib.Path(ad) / "adapters.safetensors").exists():
            b[k] = lambda r=r, ad=ad: MlxCommandParser(r, adapter=ad, fewshot=False)
    for k, path in FUSED.items():
        if pathlib.Path(path).exists():
            b[k] = lambda path=path: MlxCommandParser(path, fewshot=False, finetuned=True,
                                                      min_conf=0.5, min_conf_sensitive=0.9)
    for k, m in LOCAL.items():
        if k not in NO_TOOLS:
            b[k] = lambda m=m: Ollama(m, system)
        b[k + "-json"] = lambda m=m: OllamaJSON(m, system)
    if os.environ.get("GROQ_API_KEY"):
        b["groq-llama3.1-8b"] = lambda: OpenAICompat("llama-3.1-8b-instant", system)
        b["groq-llama3.3-70b"] = lambda: OpenAICompat("llama-3.3-70b-versatile", system)
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        b["claude-haiku-5.5"] = lambda: Claude("claude-haiku-5-5", system, effort="low", thinking={"type": "disabled"})
    return b

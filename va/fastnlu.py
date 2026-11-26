"""In-process MLX command parser: a small LM picks a compact command, constrained token by token.

Output format (one line):   <tool> <target> <action> <value>      e.g.  "light bedroom on 50"

Why this is fast:
  * the model lives in-process (no HTTP / server), weights in MLX on the GPU
  * the system prompt is prefilled once; each request reuses that KV/state cache
  * every slot only allows valid values *given the earlier slots* (light -> rooms only, front_door_lock ->
    lock/unlock only), enforced by masking logits over a token trie
  * jump-forward: when the trie has a single continuation, those tokens are appended without asking the
    model, so the model only runs at real decision points (~4-6 small forward passes per command)
"""
import copy
import math
import pathlib
import time

try:
    import mlx.core as mx
except ImportError:  # not on Apple Silicon (e.g. CI): the decoding logic stays importable and testable
    mx = None

from .common import COVERS, DEVICES, ROOMS, SCENES

TOOLS = {  # compact tool word -> (real tool name, targets)
    "light": ("control_light", ROOMS),
    "climate": ("set_climate", ROOMS),
    "cover": ("control_cover", COVERS),
    "device": ("control_device", DEVICES),
    "scene": ("activate_scene", SCENES),
    "state": ("get_state", ROOMS + DEVICES),
    "none": (None, []),
}


def actions(tool, target):
    if tool == "light":
        return ["on", "off"]
    if tool == "climate":
        return ["set"]
    if tool == "cover":
        return ["open", "close", "stop"]
    if tool == "device":
        return ["lock", "unlock"] if target == "front_door_lock" else ["on", "off"]
    if tool == "state":
        return ["temperature", "humidity", "state"]
    return []


def values(tool, action):
    if tool == "light" and action == "on":
        return ["none"] + [str(i) for i in range(0, 101)]
    if tool == "climate":
        return [str(i) for i in range(5, 36)]
    return []


GUIDE = f"""Convert the user's request into ONE command line: <tool> <target> <action> <value>
tools: light (target=room, action=on/off, value=brightness 0-100 or none), climate (target=room, action=set, value=degrees C),
cover (target=cover, action=open/close/stop), device (target=device, action=on/off, front_door_lock: lock/unlock),
scene (target=scene), state (target=room or device, action=temperature/humidity/state), none (nothing fits).
rooms: {", ".join(ROOMS)}
devices: {", ".join(DEVICES)}
covers: {", ".join(COVERS)}
scenes: {", ".join(SCENES)}
Answer with the command line only."""

# System prompt for LoRA-fine-tuned models: the adapter has learned the format, so the long guide is not needed.
FT_SYSTEM = "Smart home command parser. Output: <tool> <target> <action> <value>."

# Few-shot examples, given as real chat turns (tiny models copy turns far better than examples inside the
# system prompt). Deliberately different rooms/phrasings from the benchmark test set.
EXAMPLES = [
    ("switch on the garage light", "light garage on none"),
    ("turn the hallway lights off", "light hallway off"),
    ("bathroom lights to 30 percent", "light bathroom on 30"),
    ("lights off everywhere", "light all off"),
    ("make it 21 degrees in the bedroom", "climate bedroom set 21"),
    ("warm up the kitchen to 23", "climate kitchen set 23"),
    ("what's the temperature in the garage", "state garage temperature"),
    ("is the washing machine on", "state washing_machine state"),
    ("lower the living room blinds", "cover living_room_blinds close"),
    ("raise the bedroom blinds", "cover bedroom_blinds open"),
    ("unlock the front door", "device front_door_lock unlock"),
    ("switch the fan off", "device fan off"),
    ("turn on the washing machine", "device washing_machine on"),
    ("good night", "scene good_night"),
    ("I'm leaving the house", "scene away"),
    ("how humid is the bathroom", "state bathroom humidity"),
    ("what's the weather in Paris", "none"),
]



class _Trie:
    def __init__(self):
        self.kids, self.word = {}, None


class MlxCommandParser:
    def __init__(self, repo, system="", adapter=None, fewshot=True, finetuned=False, min_conf=0.0, min_conf_sensitive=0.0):
        self.repo, self.adapter, self.fewshot = repo, adapter, fewshot
        # Confidence gate: the lowest probability (over the FULL vocabulary) the model gave to any decision it
        # made. Below min_conf the command is rejected; door lock/unlock needs min_conf_sensitive.
        self.min_conf, self.min_conf_sensitive = min_conf, min_conf_sensitive
        self.system = FT_SYSTEM if (adapter or finetuned) else (system + "\n\n" if system else "") + GUIDE
        self.name = f"mlx-nlu:{repo.split('/')[-1]}" + (f"+{pathlib.Path(adapter).name}" if adapter else "")
        self._tries = {}

    # ---------- setup ----------
    def load(self):
        from mlx_lm import load
        from mlx_lm.models.cache import make_prompt_cache

        self.model, self.tok = load(self.repo, adapter_path=self.adapter)
        # Shared prefix = everything before the user's text (found by rendering two different user texts).
        a, b = self._prompt("aaaa"), self._prompt("bbbb")
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        self._prefix = a[:n]
        self._prefix_cache = make_prompt_cache(self.model)
        self._forward(self._prefix, self._prefix_cache)
        self.run("Turn on the kitchen light.")  # warm up Metal kernels

    def _prompt(self, text):
        msgs = [{"role": "system", "content": self.system}]
        for q, a in (EXAMPLES if self.fewshot else []):
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": text})
        try:
            s = self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False)
        except TypeError:
            s = self.tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        return self.tok.encode(s, add_special_tokens=False)

    def _forward(self, tokens, cache):
        logits = self.model(mx.array(tokens)[None], cache=cache)[:, -1, :]
        mx.eval(logits)
        return logits[0]

    def _trie(self, words, first):
        key = (tuple(words), first)
        if key not in self._tries:
            root = _Trie()
            for w in words:
                ids = self.tok.encode((w if first else " " + w) + "\n", add_special_tokens=False)
                node = root
                for t in ids[:-1]:  # drop the newline token; it only kept tokenization stable
                    node = node.kids.setdefault(t, _Trie())
                node.word = w
            self._tries[key] = root
        return self._tries[key]

    # ---------- decoding ----------
    def _choose(self, words, first, pending, cache):
        """Pick one of `words`. `pending` = tokens already decided but not yet fed to the model."""
        node = self._trie(words, first)
        while True:
            if node.word is not None and not node.kids:
                return node.word, pending
            if node.word is None and len(node.kids) == 1:  # forced: jump forward without running the model
                t, node = next(iter(node.kids.items()))
                pending.append(t)
                continue
            if node.word is not None:  # word complete but a longer one shares its tokens ("5" vs "50")
                allowed = list(node.kids) + [None]
            else:
                allowed = list(node.kids)
            logits = self._forward(pending, cache)
            lse = mx.logsumexp(logits).item()
            pending = []
            ids = [t for t in allowed if t is not None]
            best = max(ids, key=lambda t: logits[t].item())
            if None in allowed:
                stop = max(logits[s].item() for s in self._stop_ids)
                if stop > logits[best].item():
                    self._conf = min(self._conf, math.exp(stop - lse))
                    return node.word, pending
            self._conf = min(self._conf, math.exp(logits[best].item() - lse))
            pending.append(best)
            node = node.kids[best]

    def run(self, text):
        if not hasattr(self, "_stop_ids"):
            self._stop_ids = list({self.tok.encode("\n", add_special_tokens=False)[-1], self.tok.eos_token_id} - {None})
        toks = self._prompt(text)
        assert toks[:len(self._prefix)] == self._prefix, "chat template prefix changed"
        cache = copy.deepcopy(self._prefix_cache)
        pending = toks[len(self._prefix):]
        self._conf = 1.0

        tool, pending = self._choose(list(TOOLS), True, pending, cache)
        real, targets = TOOLS[tool]
        if real is None:
            return {"calls": [], "text": "Sorry, I can't do that.", "conf": self._conf}
        target, pending = self._choose(targets, False, pending, cache)
        acts = actions(tool, target)
        action, pending = self._choose(acts, False, pending, cache) if acts else (None, pending)
        vals = values(tool, action)
        value, pending = self._choose(vals, False, pending, cache) if vals else (None, pending)
        value = None if value in (None, "none") else int(value)

        if tool == "light":
            args = {"room": target, "action": action}
            if value is not None:
                args["brightness"] = value
        elif tool == "climate":
            args = {"room": target, "temperature": value}
        elif tool == "cover":
            args = {"cover": target, "action": action}
        elif tool == "device":
            args = {"device": target, "action": action}
        elif tool == "scene":
            args = {"scene": target}
        else:
            args = {"target": target, "attribute": action}
        call = {"name": real, "args": args}
        need = self.min_conf_sensitive if target == "front_door_lock" else self.min_conf
        if self._conf < need:
            return {"calls": [], "text": "Sorry, I didn't catch that.", "conf": self._conf, "rejected": call}
        return {"calls": [call], "text": "", "conf": self._conf}

    def unload(self):
        self.model = self._prefix_cache = None
        import gc
        gc.collect()
        mx.clear_cache()


if __name__ == "__main__":
    import sys
    p = MlxCommandParser(sys.argv[1] if len(sys.argv) > 1 else "ibm-granite/granite-4.0-350m")
    p.load()
    for q in ["Dim the bedroom lamp to fifty percent.", "Lock the front door.", "I'm cold, heat the bathroom to 24 degrees.",
              "Turn off all the lights.", "What's the temperature in the kids room?", "Play some jazz."]:
        t = time.perf_counter()
        r = p.run(q)
        print(f"{(time.perf_counter() - t) * 1000:5.0f} ms  {q!r:48} {r['calls'] or r['text']}")

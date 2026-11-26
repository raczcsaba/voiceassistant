"""Constrained decoding in va/fastnlu.py, run with a fake tokenizer and a scripted "model" (no MLX needed).

The fake tokenizer splits numbers into single digits, like the Qwen family does, so the token trie has words
that are prefixes of other words ("1" / "10" / "100").
"""
import re
import types

import numpy as np
import pytest

from va import common, fastnlu
from va.fastnlu import TOOLS, MlxCommandParser, actions, values

VOCAB = 256
USER, ASSISTANT = "<user>", "<assistant>"


class FakeTokenizer:
    eos_token_id = 0

    def __init__(self):
        self.ids = {"<eos>": 0}

    def _id(self, piece):
        if piece not in self.ids:
            self.ids[piece] = len(self.ids)
            assert len(self.ids) < VOCAB
        return self.ids[piece]

    def encode(self, text, add_special_tokens=False):
        pieces = re.findall(r"<user>|<assistant>|\n| ?[A-Za-z_']+| ?\d| ?[^\w\s]| ", text)
        return [self._id(p) for p in pieces]

    def apply_chat_template(self, msgs, add_generation_prompt=True, tokenize=False, **kw):
        return f"{USER}{msgs[-1]['content']}{ASSISTANT}"


class ScriptedModel:
    """Stands in for the LM: the user message is the command it should answer, `strength` sets its confidence.

    `strengths` optionally maps a decision index (0 = tool, 1 = target, ...) to a different strength.
    """

    def __init__(self, tok, strength=12.0, strengths=None):
        self.tok, self.strength, self.strengths = tok, strength, strengths or {}
        self.calls = 0

    def forward(self, tokens, cache):
        cache.extend(tokens)
        self.calls += 1
        u, a = self.tok.ids[USER], self.tok.ids[ASSISTANT]
        start, split = cache.index(u) + 1, cache.index(a)
        target = cache[start:split] + self.tok.encode("\n")
        out = cache[split + 1:]
        logits = np.zeros(VOCAB)
        logits[target[len(out)]] = self.strengths.get(self.calls - 1, self.strength)
        return logits


@pytest.fixture(autouse=True)
def fake_mx(monkeypatch):
    monkeypatch.setattr(fastnlu, "mx", types.SimpleNamespace(logsumexp=lambda x: np.logaddexp.reduce(x)))


def make_parser(**kw):
    model_kw = {k: kw.pop(k) for k in ("strength", "strengths") if k in kw}
    p = MlxCommandParser("fake/model", finetuned=True, fewshot=False, **kw)
    p.tok = FakeTokenizer()
    p.model = ScriptedModel(p.tok, **model_kw)
    p._forward = p.model.forward
    p._prefix, p._prefix_cache = [], []
    return p


class TestVocabulary:
    def test_tool_targets_match_schema(self):
        schema = {t["name"]: t for t in common.TOOLS}
        for word, (real, _targets) in TOOLS.items():
            assert word == "none" or real in schema

    @pytest.mark.parametrize("tool", [t for t in TOOLS if t != "none"])
    def test_every_target_has_valid_actions(self, tool):
        for target in TOOLS[tool][1]:
            if tool != "scene":
                assert actions(tool, target)

    def test_lock_actions(self):
        assert actions("device", "front_door_lock") == ["lock", "unlock"]
        assert actions("device", "tv") == ["on", "off"]

    def test_values(self):
        assert values("light", "on")[0] == "none" and values("light", "on")[-1] == "100"
        assert values("light", "off") == []
        assert values("climate", "set") == [str(i) for i in range(5, 36)]


class TestTrie:
    def test_words_and_shared_prefixes(self):
        p = make_parser()
        root = p._trie(["1", "10", "100", "5"], first=False)
        one = root.kids[p.tok.ids[" 1"]]
        assert one.word == "1"
        ten = one.kids[p.tok.ids["0"]]
        assert ten.word == "10"
        assert ten.kids[p.tok.ids["0"]].word == "100"

    def test_cached(self):
        p = make_parser()
        assert p._trie(["a", "b"], True) is p._trie(["a", "b"], True)


@pytest.mark.parametrize("command, expected", [
    ("light kitchen on none", {"name": "control_light", "args": {"room": "kitchen", "action": "on"}}),
    ("light all off", {"name": "control_light", "args": {"room": "all", "action": "off"}}),
    ("light bedroom on 50", {"name": "control_light", "args": {"room": "bedroom", "action": "on", "brightness": 50}}),
    ("light hallway on 1", {"name": "control_light", "args": {"room": "hallway", "action": "on", "brightness": 1}}),
    ("light hallway on 10", {"name": "control_light", "args": {"room": "hallway", "action": "on", "brightness": 10}}),
    ("light hallway on 100", {"name": "control_light", "args": {"room": "hallway", "action": "on", "brightness": 100}}),
    ("climate bathroom set 24", {"name": "set_climate", "args": {"room": "bathroom", "temperature": 24}}),
    ("cover garage_door open", {"name": "control_cover", "args": {"cover": "garage_door", "action": "open"}}),
    ("device front_door_lock lock", {"name": "control_device", "args": {"device": "front_door_lock", "action": "lock"}}),
    ("device coffee_maker on", {"name": "control_device", "args": {"device": "coffee_maker", "action": "on"}}),
    ("scene movie_night", {"name": "activate_scene", "args": {"scene": "movie_night"}}),
    ("state kids_room temperature", {"name": "get_state", "args": {"target": "kids_room", "attribute": "temperature"}}),
    ("state washing_machine state", {"name": "get_state", "args": {"target": "washing_machine", "attribute": "state"}}),
])
def test_decodes_command_to_call(command, expected):
    r = make_parser().run(command)
    assert r["calls"] == [expected]
    assert r["conf"] > 0.9


def test_none_means_no_call():
    r = make_parser().run("none")
    assert r["calls"] == [] and r["text"]


def test_forced_tokens_skip_the_model():
    p = make_parser()
    p.run("light kids_room off")
    # one forward pass per real decision (tool, room, action); "off" takes no value, so decoding stops there
    assert p.model.calls == 3


class TestConfidenceGate:
    def test_low_confidence_is_rejected(self):
        r = make_parser(strength=1.0, min_conf=0.5).run("light kitchen off")
        assert r["calls"] == []
        assert r["rejected"] == {"name": "control_light", "args": {"room": "kitchen", "action": "off"}}
        assert r["conf"] < 0.5

    def test_door_lock_needs_higher_confidence(self):
        # ~0.7 confidence: enough for a light, not for the front door
        light = make_parser(strength=6.5, min_conf=0.5, min_conf_sensitive=0.9).run("light kitchen off")
        door = make_parser(strength=6.5, min_conf=0.5, min_conf_sensitive=0.9).run("device front_door_lock unlock")
        assert 0.5 < light["conf"] < 0.9 and light["calls"]
        assert door["calls"] == [] and door["rejected"]["args"]["device"] == "front_door_lock"

    def test_confidence_is_the_weakest_decision(self):
        r = make_parser(strengths={1: 6.5}).run("light kitchen off")
        assert 0.5 < r["conf"] < 0.9 and r["calls"]

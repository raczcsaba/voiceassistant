"""Backend-independent parts of va/llm.py: flat JSON -> tool call mapping and the Ollama response handling."""
from unittest import mock

import pytest

from va import llm
from va.common import TOOLS


@pytest.mark.parametrize("flat, expected", [
    ({"tool": "control_light", "target": "garage", "action": "on", "value": None},
     {"name": "control_light", "args": {"room": "garage", "action": "on"}}),
    ({"tool": "control_light", "target": "bathroom", "action": "on", "value": 30},
     {"name": "control_light", "args": {"room": "bathroom", "action": "on", "brightness": 30}}),
    ({"tool": "control_light", "target": "kitchen", "action": "off", "value": 30},
     {"name": "control_light", "args": {"room": "kitchen", "action": "off"}}),
    ({"tool": "control_light", "target": "kitchen", "action": "set", "value": None},
     {"name": "control_light", "args": {"room": "kitchen", "action": "on"}}),
    ({"tool": "set_climate", "target": "bedroom", "action": "set", "value": 21},
     {"name": "set_climate", "args": {"room": "bedroom", "temperature": 21}}),
    ({"tool": "control_cover", "target": "bedroom_blinds", "action": "close", "value": None},
     {"name": "control_cover", "args": {"cover": "bedroom_blinds", "action": "close"}}),
    ({"tool": "control_device", "target": "front_door_lock", "action": "unlock", "value": None},
     {"name": "control_device", "args": {"device": "front_door_lock", "action": "unlock"}}),
    ({"tool": "activate_scene", "target": "good_night", "action": "set", "value": None},
     {"name": "activate_scene", "args": {"scene": "good_night"}}),
    ({"tool": "get_state", "target": "bathroom", "action": "get", "value": None, "attribute": "humidity"},
     {"name": "get_state", "args": {"target": "bathroom", "attribute": "humidity"}}),
])
def test_flat_to_call(flat, expected):
    assert llm.flat_to_call(flat) == expected


@pytest.mark.parametrize("flat", [{"tool": "none"}, {}, {"tool": "play_music", "target": "kitchen"}])
def test_flat_to_call_none(flat):
    assert llm.flat_to_call(flat) is None


def test_flat_to_call_covers_every_tool():
    for t in TOOLS:
        assert llm.flat_to_call({"tool": t["name"], "target": "x", "action": "on", "value": 1})["name"] == t["name"]


@pytest.mark.parametrize("raw, expected", [
    ({"a": 1}, {"a": 1}),
    ('{"room": "kitchen"}', {"room": "kitchen"}),
    ("", {}),
    (None, {}),
    ("not json", {}),
])
def test_as_dict(raw, expected):
    assert llm._as_dict(raw) == expected


def fake_response(status=200, body=None, text=""):
    r = mock.Mock(status_code=status, text=text)
    r.json.return_value = body
    return r


def test_ollama_tool_calls_are_parsed():
    be = llm.Ollama("some-model", "system prompt")
    be._think_ok = True
    body = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "control_light", "arguments": {"room": "kitchen", "action": "on"}}},
        {"function": {"name": "activate_scene", "arguments": '{"scene": "away"}'}},
    ]}}
    with mock.patch.object(be._s, "post", return_value=fake_response(body=body)) as post:
        r = be.run("kitchen light on and away mode")
    assert r["calls"] == [{"name": "control_light", "args": {"room": "kitchen", "action": "on"}},
                          {"name": "activate_scene", "args": {"scene": "away"}}]
    sent = post.call_args.kwargs["json"]
    assert sent["messages"][-1] == {"role": "user", "content": "kitchen light on and away mode"}
    assert sent["think"] is False and sent["options"]["temperature"] == 0


def test_ollama_retries_without_think_for_models_that_lack_it():
    be = llm.Ollama("some-model", "sys")
    be._think_ok = True
    replies = [fake_response(400, text='"think" is not supported'), fake_response(body={"message": {"content": "hi"}})]
    with mock.patch.object(be._s, "post", side_effect=replies) as post:
        r = be.run("hello")
    assert r == {"calls": [], "text": "hi"}
    assert be._think_ok is False
    assert "think" not in post.call_args.kwargs["json"]


def test_ollama_json_mode():
    be = llm.OllamaJSON("some-model", "sys")
    content = '{"tool":"set_climate","target":"kitchen","action":"set","value":23,"attribute":"none"}'
    with mock.patch.object(be._s, "post", return_value=fake_response(body={"message": {"content": content}})) as post:
        r = be.run("warm up the kitchen to 23")
    assert r == {"calls": [{"name": "set_climate", "args": {"room": "kitchen", "temperature": 23}}], "text": ""}
    assert post.call_args.kwargs["json"]["format"] is llm.OllamaJSON.SCHEMA


def test_registry_without_models_or_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no models/ or adapters/ here
    for k in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    names = llm.available("sys")
    assert "granite4-350m" in names and "granite4-350m-json" in names
    assert "lfm2-350m" not in names  # no tool template -> JSON mode only
    assert not any(n.startswith(("groq-", "claude-", "granite-cmd")) for n in names)

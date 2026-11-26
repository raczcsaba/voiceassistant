"""Scoring, text normalisation, mock home and spoken replies (va/common.py)."""
import pytest

from va.common import COVERS, DEVICES, PROFILES, ROOMS, SCENES, TOOLS, MockHome, norm_text, score_call, spoken_reply


def call(name, **args):
    return {"name": name, "args": args}


class TestScoreCall:
    def test_exact_match(self):
        assert score_call([call("control_light", room="kitchen", action="off")], "control_light", {"room": "kitchen", "action": "off"})

    def test_expected_args_are_a_subset(self):
        got = [call("control_light", room="bedroom", action="on", brightness=50)]
        assert score_call(got, "control_light", {"room": "bedroom", "brightness": 50})

    def test_wrong_tool_or_value(self):
        assert not score_call([call("control_cover", cover="garage_door", action="open")], "control_device", {"device": "tv"})
        assert not score_call([call("control_light", room="kitchen", action="on")], "control_light", {"room": "kitchen", "action": "off"})

    def test_numbers_compare_numerically(self):
        assert score_call([call("set_climate", room="bathroom", temperature="24")], "set_climate", {"temperature": 24})
        assert score_call([call("set_climate", room="bathroom", temperature=24.0)], "set_climate", {"temperature": 24})
        assert not score_call([call("set_climate", room="bathroom", temperature="warm")], "set_climate", {"temperature": 24})
        assert not score_call([call("set_climate", room="bathroom")], "set_climate", {"temperature": 24})

    def test_strings_ignore_case_and_accents(self):
        assert score_call([call("activate_scene", scene=" Movie_Night ")], "activate_scene", {"scene": "movie_night"})
        assert score_call([call("x", v="Fürdő")], "x", {"v": "furdo"})

    def test_any_of_several_calls(self):
        calls = [call("control_light", room="kitchen", action="on"), call("activate_scene", scene="away")]
        assert score_call(calls, "activate_scene", {"scene": "away"})

    def test_no_calls_or_missing_args(self):
        assert not score_call([], "control_light", {"room": "kitchen"})
        assert not score_call([{"name": "control_light"}], "control_light", {"room": "kitchen"})


@pytest.mark.parametrize("raw, expected", [
    ("Turn on the Living-Room lights!", "turn on the living room lights"),
    ("  Hello,   world.  ", "hello world"),
    ("Kapcsold FEL a lámpát.", "kapcsold fel a lámpát"),
    ("", ""),
])
def test_norm_text(raw, expected):
    assert norm_text(raw) == expected


class TestTestSets:
    @pytest.mark.parametrize("lang", list(PROFILES))
    def test_expected_args_use_known_ids(self, lang):
        tools = {t["name"]: t for t in TOOLS}
        known = set(ROOMS + DEVICES + COVERS + SCENES)
        for tid, _text, name, args in PROFILES[lang]["testset"]:
            assert name in tools, tid
            props = tools[name]["parameters"]["properties"]
            for k, v in args.items():
                assert k in props, (tid, k)
                if isinstance(v, str):
                    assert v in known or v in props[k].get("enum", []), (tid, v)

    def test_ids_are_unique(self):
        ids = [t[0] for p in PROFILES.values() for t in p["testset"]]
        assert len(ids) == len(set(ids))


class TestMockHome:
    def test_action_echoes_args(self):
        out = MockHome().execute(call("control_light", room="kitchen", action="on"))
        assert out == {"ok": True, "done": "control_light", "room": "kitchen", "action": "on"}

    def test_state_query(self):
        out = MockHome().execute(call("get_state", target="kids_room", attribute="temperature"))
        assert out["ok"] and out["target"] == "kids_room" and out["temperature"] == 21.5


class TestSpokenReply:
    def test_confirmation_per_tool(self):
        assert spoken_reply(call("set_climate", room="bedroom", temperature=21), {"ok": True}) == "Temperature set."
        assert spoken_reply(call("activate_scene", scene="away"), {"ok": True}) == "Scene on."
        assert spoken_reply(call("something_new"), {"ok": True}) == "Okay."

    @pytest.mark.parametrize("attr, value, expected", [
        ("temperature", 21.5, "It's 21.5 degrees."),
        ("humidity", 45, "Humidity is 45 percent."),
        ("state", "on", "It's on."),
    ])
    def test_state_reply_matches_attribute(self, attr, value, expected):
        c = call("get_state", target="x", attribute=attr)
        assert spoken_reply(c, {"ok": True, "target": "x", attr: value}) == expected

    def test_state_reply_with_mock_home(self):
        c = call("get_state", target="tv", attribute="state")
        assert spoken_reply(c, MockHome().execute(c)) == "It's on."

    def test_failures(self):
        assert spoken_reply(call("control_light", room="kitchen", action="on"), {"ok": False, "error": "x"}) == "Sorry, I couldn't do that."
        assert spoken_reply(call("get_state", target="x", attribute="humidity"), {"ok": True}) == "Sorry, I don't know."

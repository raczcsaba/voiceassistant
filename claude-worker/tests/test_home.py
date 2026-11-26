"""Offline tests for home control: the allowlist, the exact Home Assistant calls, dry-run logging, volume.

Run: python -m unittest discover -s tests -v   (from the claude-worker directory)
"""
import copy
import json
import os
import unittest

from voice_claude import config as config_mod
from voice_claude import home
from voice_claude.tools import Tools

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATES = [
    {"entity_id": "switch.halo_led", "state": "on", "attributes": {"friendly_name": "Decor light"}},
    {"entity_id": "light.ambient", "state": "on", "attributes": {"friendly_name": "Ambient", "brightness": 128}},
    {"entity_id": "weather.home", "state": "rainy", "attributes": {"friendly_name": "Home", "temperature": 3.4, "humidity": 96,
                                                                    "attribution": "met.no"}},
    {"entity_id": "input_boolean.intruder_alarm_armed", "state": "on", "attributes": {}},
    {"entity_id": "media_player.pi", "state": "idle",
     "attributes": {"friendly_name": "Pi", "mass_player_type": "player", "active_queue": "q1", "volume_level": 0.34}},
]

HOME = {
    "weather_entity": "weather.home",
    "read_endpoints": {"jellyfin_now": {"path": "/api/jellyfin_panel/now?device=tv", "group": "tv"}},
    "readable": {"lights": ["switch.halo_led", "light.ambient"], "weather": ["weather.home"],
                 "tv": ["media_player.tv"], "alarm": ["input_boolean.intruder_alarm_armed"]},
    "actions": {
        "tv_vibe": {"description": "Vibe mód a tévén.", "service": "script.turn_on", "data": {"entity_id": "script.tv_vibe"}},
        "lights_off": {"description": "Lamps off.", "service": "homeassistant.turn_off",
                       "params": {"entities": {"type": "entities", "enum": ["switch.halo_led", "light.ambient"],
                                               "required": True, "as": "entity_id"}}},
        "light_brightness": {"description": "Dim.", "service": "light.turn_on",
                             "params": {"entities": {"type": "entities", "enum": ["light.ambient"], "required": True, "as": "entity_id"},
                                        "brightness": {"type": "integer", "min": 1, "max": 100, "as": "brightness_pct", "required": True}}},
        "tablet_photos": {"description": "Képeim.", "service": "script.turn_on",
                          "data": {"entity_id": "script.kiosk_tablet_screensaver", "variables": {"style": "Immich Photos"}}},
        "tablet_screensaver": {"description": "Saver.", "service": "script.turn_on", "data": {"entity_id": "script.kiosk_tablet_screensaver"},
                               "params": {"style": {"type": "string", "enum": ["Immich Photos", "Northern Lights"], "into": "variables"},
                                          "mode": {"type": "string", "enum": ["Clock", "Black"], "into": "variables"}}},
        "film": {"description": "Film control.", "post": "/api/jellyfin_panel/control", "data": {"device": "tv"},
                 "params": {"action": {"type": "string", "enum": ["playpause", "stop"], "required": True}}},
        # These must never load, whatever the config says
        "alarm": {"description": "x", "service": "script.turn_on", "data": {"entity_id": "script.intruder_alert"}},
        "alarm_test": {"description": "x", "service": "script.turn_on", "data": {"entity_id": "script.intruder_alert_test"}},
        "disarm": {"description": "x", "service": "input_boolean.turn_off", "data": {"entity_id": "input_boolean.intruder_alarm_armed"}},
        "restart": {"description": "x", "service": "homeassistant.restart"},
        "reload": {"description": "x", "service": "automation.reload"},
        "sneaky": {"description": "x", "service": "script.turn_on",
                   "params": {"which": {"type": "string", "enum": ["script.tv_vibe", "script.intruder_alert"], "as": "entity_id"}}},
    },
}


class FakeHA:
    def __init__(self):
        self.calls = []
        self.gets = []

    async def states(self):
        return copy.deepcopy(STATES)

    async def call_service(self, domain, service, data, timeout=60):
        self.calls.append((f"{domain}.{service}", data))
        return []

    async def post(self, path, body, timeout=90):
        self.calls.append((path, body))
        return {"ok": True}

    async def get(self, path, timeout=20):
        self.gets.append(path)
        return {"playing": False}

    async def service_response(self, domain, service, data, timeout=20):
        self.calls.append((f"{domain}.{service}", data))
        return {"weather.home": {"forecast": [
            {"datetime": "2026-11-27T11:00:00+00:00", "condition": "cloudy", "temperature": 6.1, "templow": 1.0,
             "precipitation": 0.4, "wind_bearing": 80, "humidity": 90}]}}


class FakeMA:
    def __init__(self):
        self.calls = []

    async def call(self, command, **args):
        self.calls.append((command, args))


def make_tools(dry_run, home_cfg=HOME):
    cfg = copy.deepcopy(config_mod.DEFAULTS)
    cfg["home_control"] = copy.deepcopy(home_cfg)
    cfg["music_assistant"]["default_player"] = "media_player.pi"
    ha, ma = FakeHA(), FakeMA()
    return Tools(ma, None, ha, None, cfg, dry_run=dry_run), ha, ma


class AllowlistTests(unittest.TestCase):
    def test_denied_never_load(self):
        tools, _ha, _ma = make_tools(True)
        self.assertEqual(set(tools.actions), {"tv_vibe", "lights_off", "light_brightness", "tablet_photos",
                                              "tablet_screensaver", "film"})
        self.assertNotIn("alarm", tools.readable)
        for name in ("alarm", "alarm_test", "disarm", "restart", "reload", "sneaky"):
            self.assertNotIn(name, home.describe(tools.actions))

    def test_build_call_validation(self):
        _r, actions = home.load({"home_control": HOME})
        with self.assertRaisesRegex(ValueError, "unknown params"):
            home.build_call(actions["tv_vibe"], {"entity_id": "script.intruder_alert"})
        with self.assertRaisesRegex(ValueError, "must be one or more"):
            home.build_call(actions["lights_off"], {"entities": ["switch.halo_led", "lock.front_door"]})
        with self.assertRaisesRegex(ValueError, "required"):
            home.build_call(actions["lights_off"], {})
        with self.assertRaisesRegex(ValueError, "between"):
            home.build_call(actions["light_brightness"], {"entities": "light.ambient", "brightness": 400})
        with self.assertRaisesRegex(ValueError, "one of"):
            home.build_call(actions["tablet_screensaver"], {"style": "Pornhub"})
        # Enum values match case-insensitively and come back in their canonical spelling
        self.assertEqual(home.build_call(actions["tablet_screensaver"], {"style": "northern lights"}),
                         ("service", "script.turn_on",
                          {"entity_id": "script.kiosk_tablet_screensaver", "variables": {"style": "Northern Lights"}}))

    def test_example_config_loads_completely(self):
        cfg = config_mod.load(os.path.join(HERE, "config.example.json"))
        with open(os.path.join(HERE, "config.example.json"), encoding="utf-8") as f:
            raw = json.load(f)
        _readable, actions = home.load(cfg)
        self.assertEqual(set(actions), set(raw["home_control"]["actions"]))


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_logs_the_exact_call(self):
        tools, ha, _ma = make_tools(True)
        with self.assertLogs("voice_claude.tools", "INFO") as logs:
            out, err = await tools.run("ha_action", {"action_id": "tablet_photos"})
        self.assertFalse(err, out)
        self.assertEqual(json.loads(out), {"ok": True, "action": "tablet_photos"})
        self.assertEqual(ha.calls, [])
        self.assertEqual(tools.writes, [("ha", "script.turn_on",
                                         {"entity_id": "script.kiosk_tablet_screensaver", "variables": {"style": "Immich Photos"}})])
        self.assertIn('[dry-run] would call HA script.turn_on {"entity_id": "script.kiosk_tablet_screensaver", '
                      '"variables": {"style": "Immich Photos"}}', "\n".join(logs.output))

    async def test_real_calls(self):
        tools, ha, _ma = make_tools(False)
        await tools.run("ha_action", {"action_id": "lights_off", "params": {"entities": "switch.halo_led"}})
        await tools.run("ha_action", {"action_id": "film", "params": {"action": "playpause"}})
        await tools.run("ha_action", {"action_id": "tv_vibe"})
        self.assertEqual(ha.calls, [("homeassistant.turn_off", {"entity_id": ["switch.halo_led"]}),
                                    ("/api/jellyfin_panel/control", {"device": "tv", "action": "playpause"}),
                                    ("script.turn_on", {"entity_id": "script.tv_vibe"})])

    async def test_unknown_and_denied_actions_are_errors(self):
        tools, ha, _ma = make_tools(False)
        for args in ({"action_id": "alarm"}, {"action_id": "restart"}, {"action_id": "nope"},
                     {"action_id": "lights_off", "params": {"entities": "input_boolean.intruder_alarm_armed"}}):
            out, err = await tools.run("ha_action", args)
            self.assertTrue(err, args)
            self.assertIn("error", json.loads(out))
        self.assertEqual(ha.calls, [])
        self.assertEqual(tools.writes, [])

    async def test_get_states(self):
        tools, ha, _ma = make_tools(True)
        out = json.loads((await tools.run("ha_get_states", {"group": "lights"}))[0])
        self.assertEqual(out, {"states": [{"id": "light.ambient", "state": "on", "name": "Ambient", "brightness_pct": 50},
                                          {"id": "switch.halo_led", "state": "on", "name": "Decor light"}]})
        out, err = await tools.run("ha_get_states", {"entity_ids": ["input_boolean.intruder_alarm_armed"]})
        self.assertTrue(err)
        out = json.loads((await tools.run("ha_get_states", {"group": "weather"}))[0])
        self.assertEqual(out["states"][0]["temperature"], 3.4)
        self.assertNotIn("attribution", out["states"][0])
        out = json.loads((await tools.run("ha_get_states", {"group": "tv"}))[0])
        self.assertEqual(out["jellyfin_now"], {"playing": False})
        self.assertEqual(ha.gets, ["/api/jellyfin_panel/now?device=tv"])

    async def test_weather_forecast(self):
        tools, ha, _ma = make_tools(True)
        out = json.loads((await tools.run("get_weather_forecast", {"kind": "daily"}))[0])
        self.assertEqual(out["forecast"][0]["templow"], 1.0)
        self.assertNotIn("wind_bearing", out["forecast"][0])
        self.assertEqual(ha.calls, [("weather.get_forecasts", {"entity_id": "weather.home", "type": "daily"})])

    async def test_play_music_sets_volume_first(self):
        tools, ha, ma = make_tools(True)
        out, err = await tools.run("play_music", {"uris": ["tidal://playlist/1"], "volume": 40})
        self.assertFalse(err, out)
        self.assertEqual(json.loads(out)["volume_pct"], 40)
        self.assertEqual([w[1] for w in tools.writes], ["media_player.volume_set", "player_queues/play_media"])
        self.assertEqual(tools.writes[0][2], {"entity_id": "media_player.pi", "volume_level": 0.4})
        self.assertEqual(ma.calls, [])  # dry run: nothing sent

    async def test_set_volume_range(self):
        tools, ha, _ma = make_tools(False)
        out, err = await tools.run("set_volume", {"level": 140})
        self.assertTrue(err)
        out, err = await tools.run("set_volume", {"level": 25})
        self.assertFalse(err, out)
        self.assertEqual(ha.calls, [("media_player.volume_set", {"entity_id": "media_player.pi", "volume_level": 0.25})])

    async def test_tool_defs(self):
        tools, _ha, _ma = make_tools(True)
        defs = {d["name"]: d for d in tools.tool_defs()}
        self.assertIn("ha_get_states", defs)
        self.assertIn("get_weather_forecast", defs)
        self.assertEqual(defs["ha_action"]["input_schema"]["properties"]["action_id"]["enum"],
                         ["tv_vibe", "lights_off", "light_brightness", "tablet_photos", "tablet_screensaver", "film"])
        self.assertEqual(tools.tool_defs()[-1]["name"], "report_status")
        bare, _ha, _ma = make_tools(True, home_cfg={})
        self.assertNotIn("ha_action", {d["name"] for d in bare.tool_defs()})


if __name__ == "__main__":
    unittest.main()

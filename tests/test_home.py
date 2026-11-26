"""va/home.py HomeAssistant: our tool calls -> HA REST service calls, with the HTTP session mocked."""
import json
from unittest import mock

import pytest
import requests

from va.home import HomeAssistant

ENTITIES = {
    "lights": {"kitchen": "light.kitchen", "bedroom": "light.bedroom"},
    "climate": {"bedroom": "climate.bedroom"},
    "covers": {"garage_door": "cover.garage_door"},
    "devices": {"tv": "media_player.tv", "front_door_lock": "lock.front_door"},
    "scenes": {"away": "scene.away"},
    "sensors": {"kids_room": {"temperature": "sensor.kids_room_temperature"}},
}


def resp(body=None, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = body or {}
    r.raise_for_status.side_effect = requests.HTTPError(str(status)) if status >= 400 else None
    return r


@pytest.fixture
def ha(tmp_path):
    path = tmp_path / "home_entities.json"
    path.write_text(json.dumps(ENTITIES))
    with mock.patch("requests.Session") as session_cls:
        session = session_cls.return_value
        session.headers = {}
        session.get.return_value = resp({"message": "API running."})
        session.post.return_value = resp([])
        h = HomeAssistant(url="http://ha.test:8123/", token="secret", entities=str(path))
    session.get.reset_mock()
    return h


def posted(ha):
    (url,), kw = ha.s.post.call_args
    return url.removeprefix("http://ha.test:8123"), kw["json"]


def run(ha, name, **args):
    return ha.execute({"name": name, "args": args})


def test_connects_with_token(ha):
    assert ha.url == "http://ha.test:8123"
    assert ha.s.headers["Authorization"] == "Bearer secret"


def test_reads_url_and_token_from_env(tmp_path, monkeypatch):
    path = tmp_path / "e.json"
    path.write_text("{}")
    monkeypatch.setenv("HA_URL", "http://env.test")
    monkeypatch.setenv("HA_TOKEN", "tok")
    with mock.patch("requests.Session") as session_cls:
        session_cls.return_value.headers = {}
        h = HomeAssistant(entities=str(path))
    assert h.url == "http://env.test" and h.s.headers["Authorization"] == "Bearer tok"
    session_cls.return_value.get.assert_called_once_with("http://env.test/api/", timeout=5)


@pytest.mark.parametrize("name, args, path, data", [
    ("control_light", {"room": "kitchen", "action": "on"}, "/api/services/light/turn_on", {"entity_id": "light.kitchen"}),
    ("control_light", {"room": "bedroom", "action": "on", "brightness": 40}, "/api/services/light/turn_on",
     {"entity_id": "light.bedroom", "brightness_pct": 40}),
    ("control_light", {"room": "kitchen", "action": "off", "brightness": 40}, "/api/services/light/turn_off", {"entity_id": "light.kitchen"}),
    ("control_light", {"room": "all", "action": "off"}, "/api/services/light/turn_off", {"entity_id": "all"}),
    ("set_climate", {"room": "bedroom", "temperature": 21}, "/api/services/climate/set_temperature",
     {"entity_id": "climate.bedroom", "temperature": 21}),
    ("control_cover", {"cover": "garage_door", "action": "close"}, "/api/services/cover/close_cover", {"entity_id": "cover.garage_door"}),
    ("control_device", {"device": "front_door_lock", "action": "unlock"}, "/api/services/lock/unlock", {"entity_id": "lock.front_door"}),
    ("control_device", {"device": "tv", "action": "off"}, "/api/services/homeassistant/turn_off", {"entity_id": "media_player.tv"}),
    ("activate_scene", {"scene": "away"}, "/api/services/scene/turn_on", {"entity_id": "scene.away"}),
])
def test_service_calls(ha, name, args, path, data):
    out = run(ha, name, **args)
    assert posted(ha) == (path, data)
    assert out["ok"]


def test_service_error_propagates(ha):
    ha.s.post.return_value = resp(status=500)
    with pytest.raises(requests.HTTPError):
        run(ha, "activate_scene", scene="away")


def test_unknown_tool(ha):
    assert run(ha, "make_coffee")["ok"] is False


def test_sensor_state(ha):
    ha.s.get.return_value = resp({"state": "22.5"})
    out = run(ha, "get_state", target="kids_room", attribute="temperature")
    ha.s.get.assert_called_once_with("http://ha.test:8123/api/states/sensor.kids_room_temperature", timeout=5)
    assert out == {"ok": True, "target": "kids_room", "temperature": "22.5"}


def test_device_state(ha):
    ha.s.get.return_value = resp({"state": "off"})
    out = run(ha, "get_state", target="tv", attribute="state")
    ha.s.get.assert_called_once_with("http://ha.test:8123/api/states/media_player.tv", timeout=5)
    assert out["state"] == "off" and "temperature" not in out


def test_missing_sensor_does_not_query_ha(ha):
    out = run(ha, "get_state", target="bedroom", attribute="humidity")
    assert out["ok"] is False
    ha.s.get.assert_not_called()


def test_temperature_of_a_device_is_not_its_on_off_state(ha):
    # used to fall back to the device entity and report "off" as the temperature
    out = run(ha, "get_state", target="tv", attribute="temperature")
    assert out["ok"] is False
    ha.s.get.assert_not_called()

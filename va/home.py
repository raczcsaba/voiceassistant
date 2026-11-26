"""Home backends: MockHome (default) or a real Home Assistant over its REST API.

Home Assistant: set HA_URL (e.g. http://homeassistant.local:8123) and HA_TOKEN (long-lived access token), and map
our ids to your entity ids in home_entities.json (see home_entities.example.json). One keep-alive HTTP session is
reused, so a call is a single local round trip.
"""
import json
import os
import pathlib

from .common import MockHome  # noqa: F401  (re-exported)


class HomeAssistant:
    def __init__(self, url=None, token=None, entities="home_entities.json"):
        import requests

        self.url = (url or os.environ["HA_URL"]).rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token or os.environ['HA_TOKEN']}"})
        self.e = json.loads(pathlib.Path(entities).read_text())
        self.s.get(f"{self.url}/api/", timeout=5).raise_for_status()  # open + verify the connection

    def _svc(self, domain, service, data):
        r = self.s.post(f"{self.url}/api/services/{domain}/{service}", json=data, timeout=5)
        r.raise_for_status()
        return {"ok": True, "service": f"{domain}.{service}", **data}

    def execute(self, call):
        n, a = call["name"], call.get("args") or {}
        if n == "control_light":
            ent = "all" if a["room"] == "all" else self.e["lights"][a["room"]]
            data = {"entity_id": ent}
            if a["action"] == "on" and a.get("brightness") is not None:
                data["brightness_pct"] = a["brightness"]
            return self._svc("light", "turn_on" if a["action"] == "on" else "turn_off", data)
        if n == "set_climate":
            return self._svc("climate", "set_temperature", {"entity_id": self.e["climate"][a["room"]], "temperature": a["temperature"]})
        if n == "control_cover":
            return self._svc("cover", f"{a['action']}_cover", {"entity_id": self.e["covers"][a["cover"]]})
        if n == "control_device":
            ent = self.e["devices"][a["device"]]
            if a["action"] in ("lock", "unlock"):
                return self._svc("lock", a["action"], {"entity_id": ent})
            return self._svc("homeassistant", f"turn_{a['action']}", {"entity_id": ent})
        if n == "activate_scene":
            return self._svc("scene", "turn_on", {"entity_id": self.e["scenes"][a["scene"]]})
        if n == "get_state":
            ent = self.e.get("sensors", {}).get(a["target"], {}).get(a["attribute"])
            if ent is None and a["attribute"] == "state":
                ent = self.e["devices"].get(a["target"])
            if ent is None:
                return {"ok": False, "error": f"no entity for {a['attribute']} of {a['target']}"}
            r = self.s.get(f"{self.url}/api/states/{ent}", timeout=5)
            r.raise_for_status()
            return {"ok": True, "target": a["target"], a["attribute"]: r.json().get("state")}
        return {"ok": False, "error": f"unknown tool {n}"}

"""Shared bits: smart-home tool schemas, test sets (en/hu), prompts, scoring, mock home."""
import re
import unicodedata

ROOMS = ["living_room", "kitchen", "bedroom", "bathroom", "kids_room", "hallway", "garage", "all"]
DEVICES = ["coffee_maker", "tv", "washing_machine", "fan", "front_door_lock"]
COVERS = ["living_room_blinds", "bedroom_blinds", "garage_door"]
SCENES = ["movie_night", "morning", "good_night", "away"]

TOOLS = [
    {"name": "control_light", "description": "Turn lights on/off or set brightness in a room.",
     "parameters": {"type": "object", "properties": {
         "room": {"type": "string", "enum": ROOMS},
         "action": {"type": "string", "enum": ["on", "off"]},
         "brightness": {"type": "integer", "description": "0-100 percent, optional"}},
         "required": ["room", "action"]}},
    {"name": "set_climate", "description": "Set target temperature (Celsius) for heating/AC in a room.",
     "parameters": {"type": "object", "properties": {
         "room": {"type": "string", "enum": ROOMS},
         "temperature": {"type": "number"}},
         "required": ["room", "temperature"]}},
    {"name": "control_cover", "description": "Open, close or stop blinds or the garage door.",
     "parameters": {"type": "object", "properties": {
         "cover": {"type": "string", "enum": COVERS},
         "action": {"type": "string", "enum": ["open", "close", "stop"]}},
         "required": ["cover", "action"]}},
    {"name": "control_device", "description": "Turn a device on/off (coffee maker, tv, washing machine, fan) or lock/unlock the front door.",
     "parameters": {"type": "object", "properties": {
         "device": {"type": "string", "enum": DEVICES},
         "action": {"type": "string", "enum": ["on", "off", "lock", "unlock"]}},
         "required": ["device", "action"]}},
    {"name": "activate_scene", "description": "Activate a preset scene.",
     "parameters": {"type": "object", "properties": {
         "scene": {"type": "string", "enum": SCENES}},
         "required": ["scene"]}},
    {"name": "get_state", "description": "Read a sensor or state: temperature, humidity, or whether something is on.",
     "parameters": {"type": "object", "properties": {
         "target": {"type": "string", "description": "room or device id, e.g. kids_room, coffee_maker"},
         "attribute": {"type": "string", "enum": ["temperature", "humidity", "state"]}},
         "required": ["target", "attribute"]}},
]

PROFILES = {
    "en": {
        "system": ("You control a smart home. The user's text comes from speech recognition and may contain "
                   "mistakes. Always fulfil a request by calling exactly the right tool; never ask back. "
                   "If no tool fits, answer in one short sentence."),
        "keyterms": ["living room", "kitchen", "bedroom", "bathroom", "kids room", "hallway", "garage",
                     "blinds", "garage door", "coffee maker", "front door", "movie night"],
        "say_voice": "Samantha",
        "testset": [
            ("e01", "Turn on the living room lights.", "control_light", {"room": "living_room", "action": "on"}),
            ("e02", "Switch off the kitchen light.", "control_light", {"room": "kitchen", "action": "off"}),
            ("e03", "Dim the bedroom lamp to fifty percent.", "control_light", {"room": "bedroom", "brightness": 50}),
            ("e04", "Set the living room to twenty two degrees.", "set_climate", {"room": "living_room", "temperature": 22}),
            ("e05", "Close the bedroom blinds.", "control_cover", {"cover": "bedroom_blinds", "action": "close"}),
            ("e06", "Open the garage door.", "control_cover", {"cover": "garage_door", "action": "open"}),
            ("e07", "Start the coffee maker.", "control_device", {"device": "coffee_maker", "action": "on"}),
            ("e08", "What's the temperature in the kids room?", "get_state", {"target": "kids_room", "attribute": "temperature"}),
            ("e09", "Turn off all the lights.", "control_light", {"room": "all", "action": "off"}),
            ("e10", "Start movie night.", "activate_scene", {"scene": "movie_night"}),
            ("e11", "Lock the front door.", "control_device", {"device": "front_door_lock", "action": "lock"}),
            ("e12", "Turn off the TV.", "control_device", {"device": "tv", "action": "off"}),
            ("e13", "Hallway light at twenty percent please.", "control_light", {"room": "hallway", "brightness": 20}),
            ("e14", "I'm cold, heat the bathroom to twenty four degrees.", "set_climate", {"room": "bathroom", "temperature": 24}),
            ("e15", "Kill the lights in the kitchen.", "control_light", {"room": "kitchen", "action": "off"}),
            ("e16", "Open the living room blinds.", "control_cover", {"cover": "living_room_blinds", "action": "open"}),
        ],
    },
    "hu": {
        "system": ("Magyar nyelvű okosotthon hangasszisztens vagy. A szöveg beszédfelismerésből jön, elírásokat "
                   "tartalmazhat. Minden kérést a megfelelő tool hívásával teljesíts, ne kérdezz vissza. "
                   "Helyiségek: nappali=living_room, konyha=kitchen, hálószoba=bedroom, fürdőszoba=bathroom, "
                   "gyerekszoba=kids_room, előszoba=hallway, garázs=garage, minden=all."),
        "keyterms": ["lámpa", "nappali", "konyha", "hálószoba", "fürdőszoba", "gyerekszoba", "előszoba",
                     "redőny", "garázskapu", "kávéfőző", "fűtés"],
        "say_voice": "Tünde",
        "testset": [
            ("t01", "Kapcsold fel a lámpát a nappaliban.", "control_light", {"room": "living_room", "action": "on"}),
            ("t02", "Kapcsold le a konyhai világítást.", "control_light", {"room": "kitchen", "action": "off"}),
            ("t03", "Állítsd a hálószobai lámpát ötven százalékra.", "control_light", {"room": "bedroom", "brightness": 50}),
            ("t04", "Legyen huszonkét fok a nappaliban.", "set_climate", {"room": "living_room", "temperature": 22}),
            ("t05", "Húzd le a redőnyt a hálószobában.", "control_cover", {"cover": "bedroom_blinds", "action": "close"}),
            ("t06", "Nyisd ki a garázskaput.", "control_cover", {"cover": "garage_door", "action": "open"}),
            ("t07", "Kapcsold be a kávéfőzőt.", "control_device", {"device": "coffee_maker", "action": "on"}),
            ("t08", "Hány fok van most a gyerekszobában?", "get_state", {"target": "kids_room", "attribute": "temperature"}),
            ("t09", "Kapcsolj le minden lámpát.", "control_light", {"room": "all", "action": "off"}),
            ("t10", "Indítsd el a filmnézés jelenetet.", "activate_scene", {"scene": "movie_night"}),
            ("t11", "Zárd be a bejárati ajtót.", "control_device", {"device": "front_door_lock", "action": "lock"}),
            ("t12", "Kapcsold ki a tévét.", "control_device", {"device": "tv", "action": "off"}),
            ("t13", "Csak húsz százalékon világítson az előszobában a lámpa.", "control_light", {"room": "hallway", "brightness": 20}),
            ("t14", "Fázom, tekerd fel a fűtést huszonnégy fokra a fürdőszobában.", "set_climate", {"room": "bathroom", "temperature": 24}),
        ],
    },
}


def _ascii(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def score_call(calls, exp_name, exp_args):
    """True if any returned call matches the expected tool and argument subset."""
    for c in calls:
        if c["name"] != exp_name:
            continue
        args = c.get("args") or {}
        ok = True
        for k, v in exp_args.items():
            got = args.get(k)
            if isinstance(v, (int, float)):
                try:
                    ok &= abs(float(got) - v) < 0.01
                except (TypeError, ValueError):
                    ok = False
            else:
                ok &= _ascii(got) == _ascii(v)
        if ok:
            return True
    return False


def norm_text(s):
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class MockHome:
    """Stand-in for Home Assistant: just records/prints the action."""

    def execute(self, call):
        name, a = call["name"], call.get("args") or {}
        if name == "get_state":
            return {"target": a.get("target"), "temperature": 21.5, "humidity": 45, "state": "on"}
        return {"ok": True, "done": name, **a}

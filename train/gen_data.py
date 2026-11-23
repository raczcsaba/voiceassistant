"""Generate synthetic (utterance -> compact command) chat data for LoRA fine-tuning.

  python train/gen_data.py            # -> train/data/{train,valid}.jsonl

Utterances that appear verbatim in eval_nlu.py's held-out set or the bench test set are excluded.
"""
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from va.common import PROFILES  # noqa: E402
from va.fastnlu import FT_SYSTEM  # noqa: E402

random.seed(7)

ROOM = {
    "living_room": ["living room", "lounge", "living-room", "livingroom"],
    "kitchen": ["kitchen"],
    "bedroom": ["bedroom", "bed room", "master bedroom"],
    "bathroom": ["bathroom", "bath room", "restroom"],
    "kids_room": ["kids room", "kid's room", "children's room", "nursery", "kids' room"],
    "hallway": ["hallway", "hall", "corridor", "entrance"],
    "garage": ["garage"],
}
ALL_LIGHTS = ["all the lights", "every light", "all lights", "the lights everywhere", "all the lamps"]
COVER = {
    "living_room_blinds": ["living room blinds", "living room shades", "lounge blinds", "living room shutters"],
    "bedroom_blinds": ["bedroom blinds", "bedroom shades", "bed room blinds", "bedroom shutters"],
    "garage_door": ["garage door", "garage"],
}
DEVICE = {
    "coffee_maker": ["coffee maker", "coffee machine", "espresso machine"],
    "tv": ["tv", "TV", "television", "T V", "telly"],
    "washing_machine": ["washing machine", "washer", "laundry machine"],
    "fan": ["fan", "ventilator", "ceiling fan"],
}
SCENE = {
    "movie_night": ["movie night", "start movie night", "movie mode", "cinema mode", "let's watch a film", "time for a movie"],
    "morning": ["good morning", "morning mode", "wake up mode", "start the morning routine", "rise and shine"],
    "good_night": ["good night", "goodnight", "bedtime", "night mode", "time to sleep", "I'm heading to bed"],
    "away": ["I'm leaving", "away mode", "nobody's home", "I'm off to work", "we're leaving now", "leaving the house"],
}
NONE = ["what's the weather like", "play some music", "tell me a joke", "set a timer for five minutes", "what time is it",
        "call mom", "add milk to the shopping list", "who won the game", "how far is the moon", "order a pizza",
        "what's on my calendar", "remind me to call John", "translate hello to French", "how are you",
        "read me the news", "what's two plus two", "spell necessary", "open youtube", "send a message to Anna"]

# --- "do nothing" material: what a live mic hears besides commands ---
FILLERS = ["hi", "hey", "hey there", "good afternoon", "um", "uh", "erm", "mm", "mhm", "ah", "oh", "oops", "huh", "what",
           "okay", "ok then", "alright", "right", "sure", "yeah", "yep", "nope", "maybe", "thanks", "cheers", "sorry",
           "excuse me", "bye", "see you", "cool", "nice", "wow", "great", "really", "no way", "hold on", "one moment",
           "never mind", "forget it", "I don't know", "let me think", "hang on", "anyway", "so", "well", "hmm okay"]
SUBJ = ["I", "we", "you", "he", "she", "they", "my sister", "the neighbour", "our boss", "the kids", "mum", "dad"]
VERB = ["need to buy", "forgot", "really like", "can't find", "should call", "talked about", "are watching", "lost",
        "want to visit", "saw", "will fix", "ordered", "cooked", "hate", "borrowed", "painted"]
OBJ = ["the car", "some bread", "the tickets", "that movie", "my keys", "the report", "dinner", "the dog", "a new phone",
       "the garden", "my glasses", "the bike", "grandma", "the bill", "the shoes", "the old sofa"]
TAIL = ["", " yesterday", " tomorrow", " again", " later", " this weekend", " last week", " right now", " today"]
VERBS_CMD = ["turn on the", "turn off the", "switch on the", "switch off the", "set the", "open the", "close the",
             "dim the", "start the", "stop the", "lock the", "make the", "put the", "can you turn", "please set"]
UNKNOWN = ["oven", "dishwasher", "microwave", "radio", "vacuum", "kettle", "window", "fridge", "heater in the attic",
           "basement light", "attic light", "garden lights", "pool pump", "printer", "car", "alarm clock", "speaker",
           "dryer", "toaster", "doorbell", "gate", "balcony door", "christmas lights", "water heater", "air purifier"]
MISHEARD = ["main ramps", "light bulbs and", "living", "kitchen and", "the the", "lamps in", "lice", "flights",
            "living rum", "bed", "rooms", "blind", "garage and"]


def gen_none():
    k = random.random()
    if k < 0.3:
        u = r(FILLERS)
        if random.random() < 0.3:
            u = u + " " + r(FILLERS)
    elif k < 0.55:
        u = f"{r(SUBJ)} {r(VERB)} {r(OBJ)}{r(TAIL)}"
    elif k < 0.7:
        u = r(VERBS_CMD) if random.random() < 0.6 else r(VERBS_CMD) + " " + r(MISHEARD)
    elif k < 0.9:
        u = f"{r(['turn on', 'turn off', 'switch on', 'start', 'open', 'close', 'stop', 'switch off'])} the {r(UNKNOWN)}"
    else:
        u = r(NONE)
    return u, "none"


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num_words(n):
    if n < 20:
        return ONES[n]
    if n == 100:
        return "a hundred"
    t, o = divmod(n, 10)
    return TENS[t] + ("" if o == 0 else random.choice([" ", "-"]) + ONES[o])


def num(n):
    return random.choice([str(n), str(n), num_words(n)])


def r(x):
    return random.choice(x)


def gen_one():
    if random.random() < 0.22:
        return gen_none()
    k = random.random()
    if k < 0.30:  # lights on/off
        on = random.random() < 0.5
        if random.random() < 0.12:
            phr = r(ALL_LIGHTS)
            t = r(["turn {a} {p}", "switch {a} {p}", "{p} {a}", "{p} {a} please"] if True else [])
            return t.format(a="on" if on else "off", p=phr), f"light all {'on none' if on else 'off'}"
        room = r(list(ROOM))
        rm = r(ROOM[room])
        if on:
            t = r(["turn on the {r} light", "turn on the {r} lights", "switch on the {r} lights", "{r} lights on",
                   "lights on in the {r}", "put the light on in the {r}", "switch the {r} lamp on", "light up the {r}",
                   "I need some light in the {r}", "it's too dark in the {r}", "{r} light on please", "turn the {r} light on",
                   "can you switch on the light in the {r}", "lamp on in the {r}"])
            return t.format(r=rm), f"light {room} on none"
        t = r(["turn off the {r} light", "turn off the {r} lights", "switch off the {r} lights", "{r} lights off",
               "lights out in the {r}", "kill the {r} lights", "turn of the {r} light", "shut off the lights in the {r}",
               "switch the {r} lamp off", "no more light in the {r}", "{r} light off please", "turn the {r} light off",
               "darken the {r}", "lamp off in the {r}"])
        return t.format(r=rm), f"light {room} off"
    if k < 0.42:  # brightness
        room = r(list(ROOM))
        n = random.choice([5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, random.randint(1, 100)])
        t = r(["set the {r} lights to {n} percent", "{r} lamp at {n} percent", "dim the {r} lights to {n} percent",
               "brighten the {r} to {n} percent", "{r} lights {n} percent", "put the {r} light on {n} percent",
               "{r} brightness {n}", "make the {r} light {n} percent", "change the {r} lights to {n}%"])
        return t.format(r=r(ROOM[room]), n=num(n)), f"light {room} on {n}"
    if k < 0.54:  # climate
        room = r(list(ROOM))
        n = random.randint(16, 28)
        t = r(["set the {r} to {n} degrees", "heat the {r} to {n}", "make it {n} degrees in the {r}", "{r} thermostat to {n}",
               "I want {n} degrees in the {r}", "warm the {r} up to {n}", "cool the {r} to {n}", "change the {r} temperature to {n}",
               "{r} heating to {n} degrees", "set the heating in the {r} to {n}", "it's cold, {r} to {n} degrees please",
               "turn the {r} up to {n} degrees", "bring the {r} down to {n} degrees"])
        return t.format(r=r(ROOM[room]), n=num(n)), f"climate {room} set {n}"
    if k < 0.66:  # covers
        cv = r(list(COVER))
        act = r(["open", "close", "stop"])
        tpl = {"open": ["open the {c}", "raise the {c}", "{c} up", "put the {c} up", "pull up the {c}", "lift the {c}", "open up the {c}"],
               "close": ["close the {c}", "lower the {c}", "shut the {c}", "{c} down", "pull down the {c}", "close up the {c}"],
               "stop": ["stop the {c}", "halt the {c}", "pause the {c}", "stop moving the {c}", "freeze the {c}"]}[act]
        return r(tpl).format(c=r(COVER[cv])), f"cover {cv} {act}"
    if k < 0.80:  # devices
        if random.random() < 0.18:
            lock = random.random() < 0.5
            t = r(["lock the front door", "lock the door", "lock up", "secure the front door", "lock the front door please"]
                  if lock else ["unlock the front door", "unlock the door", "open the lock", "unlock the front door please"])
            return t, f"device front_door_lock {'lock' if lock else 'unlock'}"
        dv = r(list(DEVICE))
        on = random.random() < 0.5
        if dv == "coffee_maker" and on and random.random() < 0.3:
            return r(["make me a coffee", "brew some coffee", "I need a coffee", "coffee please"]), "device coffee_maker on"
        t = r(["turn on the {d}", "start the {d}", "switch on the {d}", "{d} on", "power on the {d}", "fire up the {d}", "put the {d} on"]
              if on else ["turn off the {d}", "stop the {d}", "switch off the {d}", "{d} off", "power down the {d}", "shut down the {d}", "turn the {d} off"])
        return t.format(d=r(DEVICE[dv])), f"device {dv} {'on' if on else 'off'}"
    if k < 0.87:  # scenes
        sc = r(list(SCENE))
        return r(SCENE[sc]), f"scene {sc}"
    if k < 0.96:  # state queries
        if random.random() < 0.6:
            room = r(list(ROOM))
            attr = r(["temperature", "temperature", "humidity"])
            t = r({"temperature": ["what's the temperature in the {r}", "how warm is the {r}", "how cold is it in the {r}",
                                   "{r} temperature?", "how hot is it in the {r}", "what temperature is it in the {r}"],
                   "humidity": ["what's the humidity in the {r}", "how humid is the {r}", "{r} humidity?", "is it humid in the {r}"]}[attr])
            return t.format(r=r(ROOM[room])), f"state {room} {attr}"
        dv = r(list(DEVICE))
        t = r(["is the {d} on", "is the {d} running", "did I leave the {d} on", "is the {d} still on", "check if the {d} is on"])
        return t.format(d=r(DEVICE[dv])), f"state {dv} state"
    return r(NONE), "none"


def decorate(s):
    if random.random() < 0.15:
        s = r(["please ", "hey, ", "can you ", "could you ", "hey assistant, "]) + s
    if random.random() < 0.12:
        s = s + r([" please", " thanks", " now", " right now", ", thank you"])
    if random.random() < 0.5:
        s = s[0].upper() + s[1:] + r([".", "", "!", "?"]) if s else s
    return s


holdout = set()
for mod in ["eval_nlu"]:
    try:
        import importlib
        m = importlib.import_module(mod)
        holdout |= {t.lower() for t, *_ in m.HELDOUT} | {t.lower().rstrip(".?!") for t in m.NEGATIVES}
    except Exception:
        pass
holdout |= {t.lower().rstrip(".?!") for _, t, *_ in PROFILES["en"]["testset"]}

seen, rows = set(), []
while len(rows) < 4000:
    u, a = gen_one()
    u = decorate(u)
    key = u.lower().rstrip(".?!")
    if key in seen or key in holdout:
        continue
    seen.add(key)
    rows.append({"messages": [{"role": "system", "content": FT_SYSTEM}, {"role": "user", "content": u},
                              {"role": "assistant", "content": a}]})

random.shuffle(rows)
out = pathlib.Path(__file__).parent / "data"
out.mkdir(exist_ok=True)
(out / "train.jsonl").write_text("\n".join(json.dumps(x) for x in rows[:3600]) + "\n")
(out / "valid.jsonl").write_text("\n".join(json.dumps(x) for x in rows[3600:]) + "\n")
print(f"{len(rows)} examples -> {out}")
for x in rows[:8]:
    print(" ", x["messages"][1]["content"], "->", x["messages"][2]["content"])

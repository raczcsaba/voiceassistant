"""Text-only accuracy/latency check of command parsers on a larger held-out set (no audio).

  python eval_nlu.py                                    # default MLX candidates
  python eval_nlu.py mlx-qwen3.5-0.8b-8bit granite4-350m-json
"""
import statistics
import sys
import time

from va import llm as llm_mod
from va.common import PROFILES, score_call

L, T, C, D, S, G = "control_light", "set_climate", "control_cover", "control_device", "activate_scene", "get_state"
HELDOUT = [
    ("lights on in the kitchen", L, {"room": "kitchen", "action": "on"}),
    ("can you turn on the bedroom light", L, {"room": "bedroom", "action": "on"}),
    ("bathroom light off please", L, {"room": "bathroom", "action": "off"}),
    ("switch off the lights in the kids room", L, {"room": "kids_room", "action": "off"}),
    ("turn the garage light on", L, {"room": "garage", "action": "on"}),
    ("set the kitchen lights to 75 percent", L, {"room": "kitchen", "brightness": 75}),
    ("living room lamp at ten percent", L, {"room": "living_room", "brightness": 10}),
    ("make the bedroom brighter, 90 percent", L, {"room": "bedroom", "brightness": 90}),
    ("everything off, all lights", L, {"room": "all", "action": "off"}),
    ("turn on all the lights", L, {"room": "all", "action": "on"}),
    ("it's dark in the hallway", L, {"room": "hallway", "action": "on"}),
    ("lights out in the living room", L, {"room": "living_room", "action": "off"}),
    ("set the bedroom to 19 degrees", T, {"room": "bedroom", "temperature": 19}),
    ("heat the kids room to twenty one", T, {"room": "kids_room", "temperature": 21}),
    ("I want 25 degrees in the living room", T, {"room": "living_room", "temperature": 25}),
    ("cool the kitchen down to 20", T, {"room": "kitchen", "temperature": 20}),
    ("thermostat in the bathroom to 22", T, {"room": "bathroom", "temperature": 22}),
    ("open the bedroom blinds", C, {"cover": "bedroom_blinds", "action": "open"}),
    ("shut the living room blinds", C, {"cover": "living_room_blinds", "action": "close"}),
    ("close the garage", C, {"cover": "garage_door", "action": "close"}),
    ("stop the blinds in the living room", C, {"cover": "living_room_blinds", "action": "stop"}),
    ("let some light into the bedroom, blinds up", C, {"cover": "bedroom_blinds", "action": "open"}),
    ("put the garage door up", C, {"cover": "garage_door", "action": "open"}),
    ("make me a coffee", D, {"device": "coffee_maker", "action": "on"}),
    ("turn the coffee machine off", D, {"device": "coffee_maker", "action": "off"}),
    ("switch on the TV", D, {"device": "tv", "action": "on"}),
    ("television off", D, {"device": "tv", "action": "off"}),
    ("start the washing machine", D, {"device": "washing_machine", "action": "on"}),
    ("stop the washer", D, {"device": "washing_machine", "action": "off"}),
    ("turn on the fan", D, {"device": "fan", "action": "on"}),
    ("lock the door", D, {"device": "front_door_lock", "action": "lock"}),
    ("unlock the front door for me", D, {"device": "front_door_lock", "action": "unlock"}),
    ("movie time", S, {"scene": "movie_night"}),
    ("good morning", S, {"scene": "morning"}),
    ("I'm going to bed", S, {"scene": "good_night"}),
    ("we're heading out", S, {"scene": "away"}),
    ("how warm is it in the living room", G, {"target": "living_room", "attribute": "temperature"}),
    ("what's the humidity in the kitchen", G, {"target": "kitchen", "attribute": "humidity"}),
    ("is the coffee maker on", G, {"target": "coffee_maker", "attribute": "state"}),
    ("is the TV still on", G, {"target": "tv", "attribute": "state"}),
    ("temperature in the bedroom?", G, {"target": "bedroom", "attribute": "temperature"}),
    # typical STT slips
    ("turn of the kitchen light", L, {"room": "kitchen", "action": "off"}),
    ("switch on the living room lice", L, {"room": "living_room", "action": "on"}),
    ("set the bed room to twenty degrees", T, {"room": "bedroom", "temperature": 20}),
    ("close the bed room blinds", C, {"cover": "bedroom_blinds", "action": "close"}),
    ("turn off the T V", D, {"device": "tv", "action": "off"}),
    ("start the coffee maker please thanks", D, {"device": "coffee_maker", "action": "on"}),
    ("kids room lights at forty percent", L, {"room": "kids_room", "brightness": 40}),
]
# Things a live mic hears that must NOT trigger anything (incl. real false triggers from the first live test).
NEGATIVES = [
    "Hello", "Hmm.", "Turn on the main ramps", "uh huh", "okay so", "what did you just say", "can you hear me",
    "thank you so much", "I'm hungry", "where did I put my phone", "the weather is nice today", "let's go",
    "turn on the", "set the", "switch off the", "turn on the oven", "open the window", "start the dishwasher",
    "switch on the sprinkler", "turn on the porch light", "she told me she'd call later", "haha that's funny",
    "no", "yes please", "wait a second", "testing testing one two three",
]
DEFAULT = ["granite-cmd-q8"]


def main():
    avail = llm_mod.available(PROFILES["en"]["system"])
    rows = []
    for name in sys.argv[1:] or DEFAULT:
        be = avail[name]()
        be.load()
        lat, ok, bad, pos_conf = [], 0, [], []
        for text, n, a in HELDOUT:
            t = time.perf_counter()
            r = be.run(text)
            lat.append(time.perf_counter() - t)
            if score_call(r["calls"], n, a):
                ok += 1
                pos_conf.append(r.get("conf", 1.0))
            else:
                bad.append((text, r["calls"] or r.get("rejected"), r.get("conf")))
        fired, neg_conf = [], []
        for text in NEGATIVES:
            r = be.run(text)
            neg_conf.append(r.get("conf", 1.0))
            if r["calls"]:
                fired.append((text, r["calls"], r.get("conf")))
        be.unload()
        rows.append((name, ok, len(fired), statistics.median(lat), max(lat)))
        print(f"\n{name}: commands {ok}/{len(HELDOUT)}, false triggers {len(fired)}/{len(NEGATIVES)}, median {statistics.median(lat) * 1000:.0f} ms")
        for text, c, cf in bad:
            print(f"   missed {text!r:46} -> {c} conf={cf}")
        for text, c, cf in fired:
            print(f"   FIRED  {text!r:46} -> {c} conf={cf}")
        if pos_conf:
            q = sorted(pos_conf)
            print(f"   conf on correct commands: min {q[0]:.3f}  p10 {q[len(q) // 10]:.3f}  median {q[len(q) // 2]:.3f}")
            print(f"   conf on negatives:        " + " ".join(f"{c:.2f}" for c in sorted(neg_conf, reverse=True)))

    print("\n| model | commands correct | false triggers | median ms | max ms |\n|---|---|---|---|---|")
    for name, ok, fired, med, mx in sorted(rows, key=lambda r: (-r[1] + r[2])):
        print(f"| {name} | {ok}/{len(HELDOUT)} | {fired}/{len(NEGATIVES)} | {med * 1000:.0f} | {mx * 1000:.0f} |")


if __name__ == "__main__":
    main()

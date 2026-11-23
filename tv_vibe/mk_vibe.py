import json, os, sys
pool = [{"i": p["i"], "d": p["d"], "t": p["t"].strip()} for p in json.load(open("pool.json"))]
# Your Android TV integration entity (the ADB one), e.g. TV_ADB_ENTITY=media_player.android_tv_xxx
ADB = os.environ.get("TV_ADB_ENTITY", "media_player.android_tv")
def adb(cmd): return {"action": "androidtv.adb_command", "target": {"entity_id": ADB}, "data": {"command": cmd}, "continue_on_error": True}
def setv(**kw): return {"variables": kw}
POLL = ("dumpsys media_session | grep -A12 'com.google.android.youtube.tv' | grep -m2 -E 'state=PlaybackState|description='; "
        "echo UP $(cut -d' ' -f1 /proc/uptime); echo FG $(dumpsys activity activities | grep -m1 mResumedActivity)")
R = "(state_attr(adb, 'adb_response') or '')"
watch_loop = {"repeat": {"while": [{"condition": "template", "value_template": "{{ watching }}"}], "sequence": [
    adb(POLL),
    setv(
        r="{{ %s }}" % R,
        st="{{ (%s | regex_findall('state=(\\d+), position') or ['0'])[0] | int }}" % R,
        pos="{{ (%s | regex_findall('position=(\\d+)') or ['0'])[0] | int }}" % R,
        upd="{{ (%s | regex_findall('updated=(\\d+)') or ['0'])[0] | int }}" % R,
        spd="{{ (%s | regex_findall('speed=([\\d.]+)') or ['1'])[0] | float }}" % R,
        up="{{ (%s | regex_findall('UP ([\\d.]+)') or ['0'])[0] | float }}" % R,
        desc="{{ ((%s | regex_findall('description=([^\\n]*)') or [''])[0]).strip() }}" % R,
    ),
    setv(
        fresh="{{ up > 0 and up != last_up and states(adb) not in ['unavailable', 'unknown', 'off'] }}",
        on_yt="{{ 'FG ' in r and 'youtube.tv' in (r.split('FG ')[1]) }}",
        left="{{ (pick.d * 1000 - (pos + ((up * 1000 - upd) * spd if st == 3 else 0))) | int }}",
    ),
    {"choose": [
        # TV switched off (standby can keep ADB alive, so check the TV's own state too)
        {"conditions": [{"condition": "template", "value_template": "{{ states('media_player.philips_uhd_android_tv') == 'off' or states(adb) == 'off' }}"}],
         "sequence": [setv(go=False, watching=False)]},
        {"conditions": [{"condition": "template", "value_template": "{{ not fresh }}"}], "sequence": [
            setv(misses="{{ misses + 1 }}"),
            {"if": [{"condition": "template", "value_template": "{{ misses >= 6 }}"}],
             "then": [setv(go=False, watching=False)], "else": [{"delay": 10}]}]},
        {"conditions": [{"condition": "template", "value_template": "{{ not on_yt }}"}],
         "sequence": [setv(go=False, watching=False)]},
        {"conditions": [{"condition": "template", "value_template": "{{ desc in ['', 'null, null, null'] }}"}],
         "sequence": [setv(misses=0, last_up="{{ up }}"), {"delay": 5}]},
        {"conditions": [{"condition": "template", "value_template": "{{ cur_desc != '' and desc != cur_desc }}"}], "sequence": [
            # Another video took over: YouTube autoplay right at the end means next; anything earlier was the user's own pick
            {"if": [{"condition": "template", "value_template": "{{ prev_left < 30000 }}"}],
             "then": [setv(watching=False)], "else": [setv(go=False, watching=False)]}]},
        {"conditions": [{"condition": "template", "value_template": "{{ st == 3 and left < 15000 }}"}], "sequence": [
            {"delay": {"seconds": "{{ [left / 1000 - 1, 0] | max | round(1) }}"}}, setv(watching=False)]},
    ], "default": [
        setv(misses=0, last_up="{{ up }}", prev_left="{{ left }}", cur_desc="{{ cur_desc if cur_desc != '' else desc }}"),
        {"delay": 10}]},
]}}
cfg = {
    "alias": "TV vibe",
    "description": "Plays a random relaxing video from the pool on the TV's YouTube app and moves to another random one when it ends. Run again to skip.",
    "icon": "mdi:weather-night",
    "mode": "restart",
    "variables": {"adb": ADB, "pool": pool},
    "sequence": [
        {"action": "script.tv_wake"},
        {"repeat": {"sequence": [{"delay": 2}, {"action": "homeassistant.update_entity", "target": {"entity_id": ADB}, "continue_on_error": True}],
                    "until": [{"condition": "template", "value_template": "{{ states(adb) not in ['unavailable','unknown','off'] or repeat.index >= 20 }}"}]}},
        {"condition": "template", "value_template": "{{ states(adb) not in ['unavailable','unknown','off'] }}"},
        setv(go=True, misses=0, last_up=0),
        {"repeat": {"while": [{"condition": "template", "value_template": "{{ go }}"}], "sequence": [
            setv(recent="{{ states('input_text.vibe_recent').split(',') | select('match', '^[A-Za-z0-9_-]{11}$') | list }}"),
            setv(cands="{{ pool | rejectattr('i', 'in', recent) | list }}"),
            setv(pick="{{ (cands if cands | length > 0 else pool) | random }}"),
            # Long walks start somewhere in their first 40% so repeats don't always open the same way
            setv(start="{{ (range(0, (pick.d * 0.4) | int, 60) | list | random) if pick.d > 5400 else 0 }}"),
            {"action": "input_text.set_value", "target": {"entity_id": "input_text.vibe_recent"}, "data": {"value": "{{ (recent + [pick.i])[-20:] | join(',') }}"}},
            {"action": "input_text.set_value", "target": {"entity_id": "input_text.vibe_now"}, "data": {"value": "{{ pick.t[:250] }}"}},
            adb("am start -a android.intent.action.VIEW -d 'https://www.youtube.com/watch?v={{ pick.i }}&t={{ start }}s' -n com.google.android.youtube.tv/com.google.android.apps.youtube.tv.activity.ShellActivity"),
            {"delay": 8},
            setv(watching=True, cur_desc="", prev_left=99999999, misses=0),
            watch_loop,
        ]}},
        {"action": "input_text.set_value", "target": {"entity_id": "input_text.vibe_now"}, "data": {"value": ""}},
    ],
}
json.dump(cfg, open("tv_vibe.json", "w"), ensure_ascii=False)
print(len(json.dumps(cfg)))

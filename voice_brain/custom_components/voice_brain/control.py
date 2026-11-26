"""The local fast path's honesty layer: what a transport command is meant for, and whether a command took effect.

conversation.py reads the Home Assistant states into Player objects, asks resolve() what to act on, awaits the
service call and polls the state until the check from expect() passes or the time budget runs out. reply() then
says only what was verified. Nothing here imports Home Assistant (tests/test_voice_control.py).
"""
from dataclasses import dataclass

TRANSPORT = ("pause", "resume", "stop", "next", "volume_up", "volume_down")
# The state a target must be in for the command to make sense
WANTED = {"pause": ("playing",), "stop": ("playing",), "next": ("playing",), "volume_up": ("playing",),
          "volume_down": ("playing",), "resume": ("paused",)}
# With several things playing and none on the satellite's own speakers, these act on all of them
MULTI = ("pause", "stop")
VOLUME_STEP = 0.1  # "hangosítsd" with no number
VOLUME_TOLERANCE = 0.015
DEAD = ("unavailable", "unknown")


@dataclass
class Player:
    entity: str            # media_player entity, or "jellyfin" / the TV entity for the TV
    kind: str              # music | film | tv
    state: str             # playing | paused | idle | off ...
    volume: float | None = None
    members: tuple = ()     # a Music Assistant group's member players
    title: str | None = None
    content_id: str | None = None
    name: str = ""          # friendly name, for players without a label
    ref: str = ""           # the Jellyfin session id of a film


def player(entity, state, attrs=None, kind="music"):
    """A Player from an HA state (state string and attributes dict)."""
    attrs = attrs or {}
    members = tuple(m for m in (attrs.get("group_members") or ()) if m != entity)
    return Player(entity, kind, state, attrs.get("volume_level"), members, attrs.get("media_title"),
                  attrs.get("media_content_id"), attrs.get("friendly_name") or "")


def collapse_groups(players):
    """A playing group plays on its members too: keep the group, drop the members it covers."""
    covered = {m for p in players for m in p.members}
    return [p for p in players if p.entity not in covered]


def _preferred(p, preferred):
    return p.entity in preferred or any(m in preferred for m in p.members)


def resolve(action, players, named=None, preferred=()):
    """What a transport command acts on: (status, targets).

    status: "ok" (act on targets), "idle" (the named player isn't playing; targets = [it]), "nothing" (nothing
    is playing) or "ambiguous" (several candidates and no rule picks one: let Claude decide).
    named: a speaker's entity the user said, or "TV" for whatever plays on the TV.
    preferred: the speakers the satellite belongs to, in order."""
    wanted = WANTED[action]
    volume = action.startswith("volume")
    if named and named != "TV":
        match = [p for p in players if p.entity == named]
        if not match:
            return "nothing", []
        p = match[0]
        if p.state in wanted or (volume and p.state not in DEAD):
            return "ok", [p]
        return "idle", [p]
    pool = [p for p in players if p.kind in ("film", "tv")] if named == "TV" else players
    active = collapse_groups([p for p in pool if p.state in wanted])
    if not active:
        return "nothing", []
    if len(active) == 1:
        return "ok", active
    mine = [p for p in active if p.kind == "music" and _preferred(p, preferred)]
    if mine:
        mine.sort(key=lambda p: min([preferred.index(e) for e in (p.entity, *p.members) if e in preferred]))
        return "ok", mine if action in MULTI else mine[:1]
    if action in MULTI:
        return "ok", active
    music = [p for p in active if p.kind == "music"]
    if len(music) == 1:
        return "ok", music
    return "ambiguous", active


def alternative(target, players):
    """Who else to try once if the target didn't react: the group's members, or the group a member plays in."""
    if target.kind != "music":
        return None
    by_entity = {p.entity: p for p in players}
    if target.members:
        members = [by_entity[m] for m in target.members if m in by_entity and by_entity[m].state == target.state]
        return members[0] if len(members) == 1 else None
    groups = [p for p in players if target.entity in p.members and p.state not in DEAD]
    return groups[0] if len(groups) == 1 else None


def volume_target(current, action, n=0, absolute=False):
    """The volume (0..1) to set: n percent up/down, or to n percent when absolute; a step when no n was said.
    None when the current volume is unknown and the change is relative."""
    if absolute and n > 0:
        level = n / 100
    elif current is None:
        return None
    else:
        delta = n / 100 if n > 0 else VOLUME_STEP
        level = current + delta if action == "volume_up" else current - delta
    return round(min(1.0, max(0.0, level)), 2)


def expect(action, before, target_volume=None):
    """A check on the player's state after the command: True once it shows the command took effect."""
    if action in ("pause", "stop"):
        return lambda after: after.state not in ("playing", "buffering", *DEAD)
    if action == "resume":
        return lambda after: after.state == "playing"
    if action == "next":
        old = (before.content_id, before.title)
        return lambda after: (after.content_id, after.title) != old and any((after.content_id, after.title))
    if action in ("volume_up", "volume_down"):
        if target_volume is not None:
            return lambda after: after.volume is not None and abs(after.volume - target_volume) <= VOLUME_TOLERANCE
        if before.volume is None:
            return lambda after: False
        if action == "volume_up":
            return lambda after: after.volume is not None and after.volume > before.volume
        return lambda after: after.volume is not None and after.volume < before.volume
    raise ValueError(action)


def switched(action, state, attrs=None, brightness_pct=None):
    """True when a light / switch / TV shows the on / off / brightness that was asked for."""
    if action == "off":
        return state == "off"
    if state in ("off", *DEAD):
        return False
    if brightness_pct is None:
        return True
    current = (attrs or {}).get("brightness")
    return current is not None and abs(current * 100 / 255 - brightness_pct) <= 2


# ---------------------------------------------------------------------------------------------- replies
WHERE = {
    "hu": {"media_player.raspberrypi": "a Pi-n", "media_player.digiamp_player": "a DigiAMP-on",
           "media_player.nappali": "a nappaliban", "media_player.work_pc": "a gépen",
           "media_player.csabas_macbook_pro": "a Macen", "film": "a tévén", "tv": "a tévén"},
    "en": {"media_player.raspberrypi": "on the Pi", "media_player.digiamp_player": "on the DigiAMP",
           "media_player.nappali": "in the living room", "media_player.work_pc": "on the PC",
           "media_player.csabas_macbook_pro": "on the Mac", "film": "on the TV", "tv": "on the TV"},
}
WHAT = {"hu": {"music": "a zenét", "film": "a filmet", "tv": "a lejátszást"},
        "en": {"music": "the music", "film": "the film", "tv": "playback"}}
DONE = {
    "hu": {"stop": "Megállítottam {what} {where}.", "pause": "Szünetre tettem {what} {where}.",
           "resume": "Folytattam {what} {where}.", "next": "Következő szám {where}.",
           "next_title": "Következő szám: {title}.", "volume": "Hangerő {pct} százalék {where}."},
    "en": {"stop": "Stopped {what} {where}.", "pause": "Paused {what} {where}.", "resume": "Resumed {what} {where}.",
           "next": "Next track {where}.", "next_title": "Next track: {title}.", "volume": "Volume {pct} percent {where}."},
}
FAILED = {
    "hu": {"stop": "Nem sikerült megállítani {what} {where}.", "pause": "Nem sikerült szünetre tenni {what} {where}.",
           "resume": "Nem sikerült folytatni {what} {where}.", "next": "Nem sikerült továbblépni {where}.",
           "volume": "Nem sikerült állítani a hangerőt {where}."},
    "en": {"stop": "Couldn't stop {what} {where}.", "pause": "Couldn't pause {what} {where}.",
           "resume": "Couldn't resume {what} {where}.", "next": "Couldn't skip {where}.",
           "volume": "Couldn't change the volume {where}."},
}
UNVERIFIED = {"hu": "Elküldtem a parancsot a tévének, de nem látom, hogy hatott-e.",
              "en": "I sent it to the TV, but I can't see whether it worked."}
NOTHING = {"hu": "Most nem szól semmi.", "en": "Nothing is playing."}
IDLE = {"hu": "{where} most nem szól semmi.", "en": "Nothing is playing {where}."}


def where(p, lang="hu"):
    table = WHERE.get(lang, WHERE["en"])
    if p.kind != "music":
        return table[p.kind]
    if p.entity in table:
        return table[p.entity]
    if not p.name:
        return ""
    return f"itt: {p.name}" if lang == "hu" else f"on {p.name}"


def reply(action, results, lang="hu"):
    """What to say about the targets: results is [(Player before, outcome, Player after or None)], outcome is
    "ok", "failed" or "unverified"."""
    done, failed = DONE.get(lang, DONE["en"]), FAILED.get(lang, FAILED["en"])
    key = "volume" if action.startswith("volume") else action
    parts = []
    for before, outcome, after in results:
        fields = {"what": WHAT.get(lang, WHAT["en"])[before.kind], "where": where(before, lang)}
        if outcome == "unverified":
            text = UNVERIFIED.get(lang, UNVERIFIED["en"])
        elif outcome == "failed":
            text = failed[key].format(**fields)
        elif key == "volume":
            pct = round(((after or before).volume or 0) * 100)
            text = done["volume"].format(pct=pct, **fields)
        elif key == "next" and after is not None and after.title:
            text = done["next_title"].format(title=after.title)
        else:
            text = done[key].format(**fields)
        parts.append(" ".join(text.split()).replace(" .", "."))
    out = []
    for p in parts:
        if p not in out:
            out.append(p)
    return " ".join(out)

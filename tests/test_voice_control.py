"""voice_brain/control.py: which player a transport command is meant for, and when a command counts as done.

The module has no Home Assistant imports, so it is loaded straight from its file; HA states are mocked as
(state, attributes) pairs."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "voice_brain/custom_components/voice_brain/control.py"
_spec = importlib.util.spec_from_file_location("voice_brain_control", _PATH)
control = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(control)

PI, AMP, GROUP, WORK = ("media_player.raspberrypi", "media_player.digiamp_player", "media_player.nappali",
                        "media_player.work_pc")
HOME = (GROUP, PI, AMP)


def house(**states):
    """The Music Assistant players as HA would show them; keyword = short name, value = state or (state, attrs)."""
    names = {"pi": PI, "amp": AMP, "group": GROUP, "work": WORK}
    players = []
    for short, entity in names.items():
        value = states.get(short, "idle")
        state, attrs = value if isinstance(value, tuple) else (value, {})
        if short == "group":
            attrs = {"group_members": [AMP, PI], **attrs}
        players.append(control.player(entity, state, {"volume_level": 0.5, **attrs}))
    return players


FILM = control.Player("jellyfin", "film", "playing", title="Dűne", ref="s1")


# --------------------------------------------------------------------------------------------- resolve
def test_the_bug_state_allj_on_the_tablet_while_the_pi_plays():
    # 2026-11-26 09:44: the Pi played, "Állj!" went to Claude's cancel and nothing stopped. Now the Pi is the target.
    status, targets = control.resolve("stop", house(pi="playing"), None, HOME)
    assert status == "ok" and [t.entity for t in targets] == [PI]


@pytest.mark.parametrize("action", ["stop", "pause", "next", "volume_up", "volume_down"])
def test_nothing_playing(action):
    assert control.resolve(action, house(), None, HOME) == ("nothing", [])


def test_paused_player_is_not_stopped_but_resumed():
    players = house(pi="paused")
    assert control.resolve("stop", players)[0] == "nothing"
    assert [t.entity for t in control.resolve("resume", players)[1]] == [PI]


def test_playing_group_covers_its_members():
    status, targets = control.resolve("stop", house(group="playing", pi="playing", amp="playing"), None, HOME)
    assert status == "ok" and [t.entity for t in targets] == [GROUP]


def test_music_on_the_satellites_speakers_wins_over_elsewhere():
    players = house(pi="playing", work="playing")
    # pause and stop act on the satellite's own speaker only
    assert [t.entity for t in control.resolve("stop", players, None, HOME)[1]] == [PI]
    assert [t.entity for t in control.resolve("next", players, None, HOME)[1]] == [PI]
    # a satellite next to the work PC prefers that one
    assert [t.entity for t in control.resolve("pause", players, None, (WORK,))[1]] == [WORK]


def test_several_without_preference_stop_all_but_next_is_ambiguous():
    players = house(work="playing") + [control.Player("media_player.pici", "music", "playing")]
    status, targets = control.resolve("stop", players, None, HOME)
    assert status == "ok" and {t.entity for t in targets} == {WORK, "media_player.pici"}
    assert control.resolve("next", players, None, HOME)[0] == "ambiguous"


def test_film_alone_is_the_target():
    status, targets = control.resolve("pause", [*house(), FILM], None, HOME)
    assert status == "ok" and targets == [FILM]


def test_music_and_film_stop_prefers_the_living_room_music():
    status, targets = control.resolve("stop", [*house(pi="playing"), FILM], None, HOME)
    assert [t.entity for t in targets] == [PI]


def test_music_elsewhere_and_film_stops_both_volume_goes_to_music():
    players = [*house(work="playing"), FILM]
    assert {t.entity for t in control.resolve("stop", players, None, HOME)[1]} == {WORK, "jellyfin"}
    assert [t.entity for t in control.resolve("volume_up", players, None, HOME)[1]] == [WORK]


def test_named_speaker():
    players = house(pi="playing")
    assert control.resolve("stop", players, AMP, HOME) == ("idle", [players[1]])
    assert control.resolve("stop", players, PI, HOME)[1][0].entity == PI
    # volume on a named idle speaker is fine
    assert control.resolve("volume_up", players, AMP, HOME)[0] == "ok"
    assert control.resolve("volume_up", [control.Player(AMP, "music", "unavailable")], AMP)[0] == "idle"


def test_named_tv_ignores_music():
    players = [*house(pi="playing"), FILM]
    assert control.resolve("pause", players, "TV", HOME)[1] == [FILM]
    assert control.resolve("pause", house(pi="playing"), "TV", HOME) == ("nothing", [])


def test_alternative_target():
    players = house(group="playing", pi="playing")
    group = next(p for p in players if p.entity == GROUP)
    pi = next(p for p in players if p.entity == PI)
    assert control.alternative(group, players).entity == PI   # only the Pi of the group plays
    assert control.alternative(pi, players).entity == GROUP
    assert control.alternative(FILM, players) is None


# --------------------------------------------------------------------------------------------- verification
def after(state="idle", volume=0.5, title=None, content_id=None):
    return control.Player(PI, "music", state, volume, title=title, content_id=content_id)


@pytest.mark.parametrize(("action", "state", "ok"), [
    ("stop", "idle", True), ("stop", "paused", True), ("stop", "playing", False), ("stop", "buffering", False),
    ("stop", "unavailable", False), ("pause", "paused", True), ("pause", "playing", False),
    ("resume", "playing", True), ("resume", "paused", False),
])
def test_expect_state(action, state, ok):
    assert control.expect(action, after("playing"))(after(state)) is ok


def test_expect_next_needs_another_track():
    before = after("playing", title="A", content_id="1")
    check = control.expect("next", before)
    assert not check(before)
    assert check(after("playing", title="B", content_id="2"))
    assert not check(after("playing"))  # no track info at all: not verified


def test_expect_volume():
    before = after("playing", 0.5)
    assert control.expect("volume_up", before, 0.7)(after("playing", 0.7))
    assert not control.expect("volume_up", before, 0.7)(after("playing", 0.5))
    assert control.expect("volume_down", before)(after("playing", 0.45))
    assert not control.expect("volume_down", before)(after("playing", 0.5))
    assert not control.expect("volume_up", after("playing", None))(after("playing", 0.6))


@pytest.mark.parametrize(("current", "action", "n", "absolute", "level"), [
    (0.55, "volume_up", 20, False, 0.75),     # "hangosíts húsz százalékot"
    (0.55, "volume_up", 13, False, 0.68),
    (0.55, "volume_down", 30, True, 0.3),     # "halkítsd le harmincra"
    (0.55, "volume_up", 0, False, 0.65),      # a step
    (0.95, "volume_up", 20, False, 1.0),
    (0.05, "volume_down", 0, False, 0.0),
    (None, "volume_up", 10, False, None),
    (None, "volume_up", 40, True, 0.4),
])
def test_volume_target(current, action, n, absolute, level):
    assert control.volume_target(current, action, n, absolute) == level


@pytest.mark.parametrize(("action", "state", "attrs", "pct", "ok"), [
    ("off", "off", None, None, True), ("off", "on", None, None, False), ("on", "on", None, None, True),
    ("on", "unavailable", None, None, False), ("on", "off", None, None, False),
    ("on", "on", {"brightness": 128}, 50, True), ("on", "on", {"brightness": 255}, 50, False),
    ("on", "on", {}, 50, False), ("off", "unavailable", None, None, False),
])
def test_switched(action, state, attrs, pct, ok):
    assert control.switched(action, state, attrs, pct) is ok


# --------------------------------------------------------------------------------------------- replies
PI_PLAYING = control.player(PI, "playing", {"volume_level": 0.5, "media_title": "A"})


def test_reply_says_what_was_verified():
    assert control.reply("stop", [(PI_PLAYING, "ok", after())]) == "Megállítottam a zenét a Pi-n."
    assert control.reply("pause", [(FILM, "ok", None)]) == "Szünetre tettem a filmet a tévén."
    assert control.reply("stop", [(PI_PLAYING, "failed", None)]) == "Nem sikerült megállítani a zenét a Pi-n."
    assert control.reply("volume_up", [(PI_PLAYING, "ok", after("playing", 0.75))]) == "Hangerő 75 százalék a Pi-n."
    assert control.reply("next", [(PI_PLAYING, "ok", after("playing", title="Creep"))]) == "Következő szám: Creep."
    assert control.reply("stop", [(control.Player("tv", "tv", "playing"), "unverified", None)]).startswith("Elküldtem")


def test_reply_both():
    work = control.player(WORK, "playing", {})
    text = control.reply("stop", [(work, "ok", None), (FILM, "ok", None)])
    assert text == "Megállítottam a zenét a gépen. Megállítottam a filmet a tévén."


def test_reply_unknown_player_and_english():
    pici = control.player("media_player.pici", "playing", {"friendly_name": "Pici"})
    assert control.reply("stop", [(pici, "ok", None)]) == "Megállítottam a zenét itt: Pici."
    assert control.reply("stop", [(PI_PLAYING, "ok", None)], "en") == "Stopped the music on the Pi."

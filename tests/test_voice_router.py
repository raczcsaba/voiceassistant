"""voice_brain/router.py: the deterministic pre-router that keeps like / save / cancel from misfiring.

The module has no Home Assistant imports, so it is loaded straight from its file."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "voice_brain/custom_components/voice_brain/router.py"
_spec = importlib.util.spec_from_file_location("voice_brain_router", _PATH)
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)

# The three requests of 2026-11-26 that the local model sent to save_to_playlist (q="rock"): each one added the
# playing track to the user's "rock" playlist.
MORNING = [
    "Valami rock metal-szerű playlistet indíts el nekem negyvenes hangerőn.",
    "Keresd nekem egy playlistet valami rock metal stílusban és indítsd el.",
    "Szólj Cloudnak, hogy indítson el nekem egy playlistet rock metal stílusban.",
]


@pytest.mark.parametrize("text", MORNING)
def test_morning_misroutes_go_to_claude(text):
    assert router.route(text)[0] == "claude"
    # Even if the model says save_to_playlist (or like / cancel), the transcript doesn't back it
    for action in ("save_to_playlist", "like", "cancel"):
        assert router.check_model(text, action) == "claude"
    assert not router.is_save(text)


@pytest.mark.parametrize("text", [
    "Claude, kapcsold le a dekor lámpát",
    "Cloud kapcsold be a tévét",
    "Klód, mi a helyzet?",
    "Szólj Klaudnak, hogy tegyen be valami zenét",
    "szólj Claude-nak, hogy kapcsolja le a lámpát",
    "Clod indítsd el a képeimet",
    "kérdezd meg a KLÓDOT",
    "Kloud milyen idő lesz holnap",
])
def test_claude_keyword_always_hands_off(text):
    assert router.has_claude(text)
    assert router.route(text) == ("claude", "keyword")


@pytest.mark.parametrize("text", ["Klaudia születésnapja mikor van", "kapcsold le a dekor lámpát", "iCloud", "felhős idő"])
def test_no_false_claude(text):
    assert not router.has_claude(text)


@pytest.mark.parametrize("text", [
    "Indíts el egy playlistet", "játssz egy rock playlistet", "keress egy jó lejátszási listát",
    "indítsd el a nyári lejátszási listát", "csinálj egy lejátszási listát pörgős számokból",
    "Tegyél be egy rock listát",
])
def test_playlist_requests_are_never_save(text):
    assert not router.is_save(text)
    assert router.route(text)[0] == "claude"
    assert router.check_model(text, "save_to_playlist") == "claude"


@pytest.mark.parametrize(("text", "name"), [
    ("mentsd el a rock listába", "rock"),
    ("tedd fel ezt a nyári lejátszási listára", "nyári"),
    ("rakd be ezt a számot az edzős listámba", "edzős"),
    ("add hozzá ezt a Chill Vibes playlisthez", "Chill Vibes"),
    ("tedd a rock listába ami most szól", "rock"),
    ("add this to my workout playlist", "workout"),
    ("ezt mentsd el a listámba", ""),
])
def test_explicit_save(text, name):
    assert router.route(text) == ("save_to_playlist", name)
    assert router.check_model(text, "save_to_playlist") == "save_to_playlist"


@pytest.mark.parametrize("text", [
    "tedd be a rock playlistet",      # play it, accusative: not a destination
    "tedd be ezt a playlistet",
    "mi van a rock listámban",
    "rock",
    "tedd a rock listába",            # no reference to the playing track and no "mentsd el"
])
def test_not_save(text):
    assert not router.is_save(text)
    assert router.check_model(text, "save_to_playlist") == "claude"


@pytest.mark.parametrize("text", [
    "ez tetszik", "nagyon tetszik ez a szám", "tetszik", "lájkold ezt a számot", "lájk",
    "tedd a kedvencekhez ezt a számot", "kedvencekhez", "add hozzá a kedvenceimhez", "i love this song",
])
def test_like(text):
    assert router.route(text) == ("like", "")
    assert router.check_model(text, "like") == "like"


@pytest.mark.parametrize("text", [
    "játszd a kedvenceimet", "tetszik a Beatles", "mi tetszik neked", "imádom a Beatlest",
    "melyik a kedvenc számod", "tegyél be valami kedvenc rock zenét",
])
def test_not_like(text):
    assert not router.is_like(text)
    assert router.check_model(text, "like") == "claude"


@pytest.mark.parametrize("text", ["Claude állj", "hagyd abba Claude", "mégse", "Klód, állj le!", "stop Claude"])
def test_cancel(text):
    assert router.route(text) == ("cancel", "")


@pytest.mark.parametrize(("text", "kept"), [("Állj!", "cancel"), ("elég", "cancel"), ("hagyd abba", "cancel"),
                                            ("kapcsold le a lámpát", "claude"), ("rock", "claude")])
def test_model_cancel_needs_a_stop_word(text, kept):
    assert router.check_model(text, "cancel") == kept


@pytest.mark.parametrize("text", ["kapcsold le a dekor lámpát", "halkítsd le", "következő szám", "szünet",
                                  "tedd be a Mátrix filmet", "játssz valami Beatles számot"])
def test_device_control_and_music_go_to_the_model(text):
    assert router.route(text) is None
    for action in ("off", "volume_down", "next", "pause", "movie", "music"):
        assert router.check_model(text, action) == action


def test_plain_keeps_length():
    text = "Tedd a NYÁRI-listába, ő!"
    assert len(router.plain(text)) == len(text)

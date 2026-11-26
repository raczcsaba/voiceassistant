"""Deterministic pre-router: regex rules on the transcript that run before the local language model.

like, save_to_playlist and cancel change things the user cares about (favourites, own playlists, a running Claude
task), so they never run on the model's word alone: each needs an explicit phrase in the transcript. Anything that
names Claude (or a common mis-transcription of it) always goes to the Claude worker.

No Home Assistant imports, so it can be tested on its own (tests/test_voice_router.py).
"""
import re
import unicodedata


def plain(text):
    """Lowercase, accents stripped, punctuation turned into spaces. Same length as the input, so a span found in
    the plain text can be cut out of the original (playlist names keep their accents)."""
    out = []
    for c in text:
        base = unicodedata.normalize("NFKD", c.lower())[:1] or " "
        out.append(base if base.isalnum() else " ")
    return "".join(out)


def _squash(text):
    return re.sub(r"\s+", " ", plain(text)).strip()


# Claude as speech-to-text spells it: Cloud, Klód, Klaud, Clod... with Hungarian case endings (Claude-nak ->
# "claude nak" after plain(), Cloudnak, Klódot). Whole words only, so "Klaudia" or "felhő" don't match.
_CLAUDE_NAMES = r"(?:claude|claud|clode|cloude|cloud|kloud|klod|klaud|klaude|clod|klot|clot)"
_CASE = r"(?:\s?(?:nak|nek|ot|et|t|tol|hoz|val|vel|ra|re|on|nal|ba|bol|ig|ka|kam|om))?"
CLAUDE = re.compile(rf"\b{_CLAUDE_NAMES}{_CASE}\b")

# "Claude, stop" and friends: certain enough to skip the model.
_STOP = r"(?:allj|alljon le|alljal le|allitsd le|allj le|hagyd abba|hagyja abba|fejezd be|stop|eleg|cancel)"
CANCEL = re.compile(rf"^\s*(?:(?:{_CLAUDE_NAMES}{_CASE}\s+{_STOP})|(?:{_STOP}\s+{_CLAUDE_NAMES}{_CASE})|megse|megsem)\s*$")
# What the model's "cancel" must be backed by: an actual stop word somewhere in the transcript.
STOP_WORD = re.compile(r"\b(?:allj|alljon|allitsd le|hagyd abba|hagyja abba|fejezd be|stop|eleg|megse|megsem|cancel|abort)\b")

# Requests to start, find or build music. These are never like or save, whatever else they contain.
PLAY_VERB = re.compile(
    r"\b(?:indits|inditsd|inditsa|inditson|inditanal|inditsal|elindit\w*|jatssz|jatszd|jatsszal|jatszon|jatszanal|"
    r"lejatsz(?!asi)\w*|keress|keresd|keressen|keresnel|keresel|talalj|csinalj|csinald|keszits|keszitsd|hozz letre|"
    r"rakj ossze|allits ossze|osszeall\w*|tegyel|rakj be|rakjal|szeretnek hallani|play|start|find|search|make|create|"
    r"put on|rakd be valami|kapcsold be)\b")
LIST_WORD = re.compile(r"\b(?:list\w*|playlist\w*|lejatszasi)\b")

# save_to_playlist: a "put" verb + a playlist word + a reference to the playing track (or "mentsd el").
SAVE_VERB = re.compile(r"\b(?:ments\w*|elment\w*|hozzaad\w*|add hozza|adjad hozza|add|tedd|tegyed|rakd|rakjad|"
                       r"pakold|save|put)\b")
SAVE_EXPLICIT = re.compile(r"\bments(?:d|ed|e)? el\b|\belments\w*\b|\bsave (?:this|it|the song|the track)\b")
CURRENT = re.compile(r"\b(?:ez|ezt|ezzel|mostani\w*|ami most szol|ami szol|ami most megy|ami megy|aktualis\w*|"
                     r"jelenlegi\w*|this|it|current)\b")
# The list as the destination, the name in front of it: "a rock listába", "a nyári lejátszási listára", "az edzős
# listámba", "a chill playlisthez", "to my workout playlist". "Indítsd el a rock playlistet" (accusative) is not one.
LIST_NOUN = re.compile(r"\b(?:lejatszasi\s+)?(?:list(?:a|am|ank|ad)(?:ba|ra|hoz)|playlist(?:e?m)?(?:be|re|hez|hoz))\b")
LIST_EN = re.compile(r"\b(?:to|into)\s+(?:the\s+|my\s+)?(?P<name>(?:\w+\s+){0,3}?)(?:play)?list\b")
# Words that end the playlist name when walking backwards from the list noun
NAME_STOP = {"a", "az", "ez", "ezt", "egy", "en", "fel", "be", "bele", "el", "hozza", "ide", "is", "meg", "most",
             "szamot", "szamat", "dalt", "zenet", "mostanit", "the", "my", "to", "this", "it", "into", "nekem",
             "kerlek", "legyszi", "legyszives", "tedd", "tegyed", "rakd", "rakjad", "mentsd", "mentsed", "add",
             "pakold", "hozzaad", "hozzaadod", "hozzaadnad", "es", "pls", "please", "ami", "szol", "kedvenc"}

# like: a clear like / favourite phrase. "játszd a kedvenceimet" is a play request, not a like.
LIKE = re.compile(
    r"\b(?:nagyon jo ez|imadom ezt|szeretem ezt a szamot|lajk\w*|like\w*|"
    r"kedvencekhez|kedvencek koze|kedvenceim koze|kedvenceimhez|kedvencnek|kedvencek kozott|"
    r"i love this|i like this|love this song|add (?:this|it) to (?:my )?favou?rites|favou?rite (?:this|it))\b")
# "tetszik" alone, or about this track: "ez tetszik", "nagyon tetszik ez a szám" (not "tetszik a Beatles")
LIKE_TETSZIK = re.compile(r"^(?:ez\s+|nagyon\s+|ez\s+nagyon\s+|ez\s+a\s+szam\s+)?tetszik(?:\s+ez(?:\s+a\s+(?:szam|dal|zene))?)?$")
QUESTION = re.compile(r"\b(?:mi|mit|milyen|melyik|hogy|hogyan|miert|mikor|kinek|ki|what|which|why|how)\b")


def has_claude(text):
    return bool(CLAUDE.search(_squash(text)))


def is_cancel(text):
    return bool(CANCEL.match(_squash(text)))


def has_stop_word(text):
    return bool(STOP_WORD.search(_squash(text)))


def is_like(text):
    p = _squash(text)
    if PLAY_VERB.search(p) or QUESTION.search(p) or LIST_WORD.search(p):
        return False
    return bool(LIKE.search(p) or LIKE_TETSZIK.match(p))


def is_playlist_request(text):
    """"Indíts el / játssz / keress egy playlistet": a music request that names a playlist."""
    p = _squash(text)
    return bool(LIST_WORD.search(p) and PLAY_VERB.search(p))


def is_save(text):
    p = _squash(text)
    if PLAY_VERB.search(p) or not (LIST_NOUN.search(p) or LIST_EN.search(p)):
        return False
    if SAVE_EXPLICIT.search(p):
        return True
    return bool(SAVE_VERB.search(p) and CURRENT.search(p))


def playlist_name(text):
    """The playlist name in front of the list noun, in its original spelling ("" if none was said)."""
    p = plain(text)
    m = LIST_NOUN.search(p)
    if not m:
        en = LIST_EN.search(p)
        return text[en.start("name"): en.end("name")].strip() if en else ""
    words = [(w.start(), w.end()) for w in re.finditer(r"\w+", p[: m.start()])]
    picked = []
    for start, end in reversed(words):
        if p[start:end] in NAME_STOP or len(picked) == 4:
            break
        picked.append((start, end))
    if not picked:
        return ""
    return text[picked[-1][0]: picked[0][1]].strip()


def route(text):
    """The deterministic decision, or None to ask the local model.

    Returns one of: ("cancel", ""), ("claude", reason), ("like", ""), ("save_to_playlist", name)."""
    if is_cancel(text):
        return "cancel", ""
    if has_claude(text):
        return "claude", "keyword"
    if is_playlist_request(text):
        return "claude", "playlist"
    if is_save(text):
        return "save_to_playlist", playlist_name(text)
    if is_like(text):
        return "like", ""
    return None


def check_model(text, action):
    """The model's like / save / cancel is only kept when the transcript backs it; otherwise Claude decides."""
    if action in ("like", "save_to_playlist"):
        return action if (is_like(text) if action == "like" else is_save(text)) else "claude"
    if action == "cancel":
        return "cancel" if has_stop_word(text) else "claude"
    return action

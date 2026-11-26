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


# Answers to a question the worker asked ("Letöltsem a Dűne második részét?"): the whole utterance is a yes, a no,
# a maybe or a short "do it / something else". Alone these are never device commands.
_YES = (r"igen|igen kerem|igen kerlek|igen legyszi|ja|jah|aha|ok|oke|okes|okay|persze|hogyne|nana|jo|jo lesz|rendben|"
        r"mehet|mehet kerem|csinald|csinald meg|toltsd le|toltsed le|toltsd|toltsd le kerlek|kerem|kerlek|legyszi|"
        r"yes|yeah|yep|sure|go ahead|do it|please")
_NO = r"nem|nem kell|nem kerem|nem koszonom|ne|ne toltsd le|inkabb ne|inkabb nem|hagyjuk|hagyd|nem most|no|nope|no thanks"
_OTHER = (r"mast|valami mast|egy masikat|masikat|a masikat|inkabb mast|talan|lehet|majd|kesobb|majd kesobb|mindegy|"
          r"nem tudom|maybe|later|something else")
ANSWER = re.compile(rf"^(?:(?:{_YES}|{_NO}|{_OTHER})(?:\s+(?:koszi|koszonom|kerem|kerlek|thanks|please))?\s*)+$")
ANSWER_WORDS = 6  # shorter utterances may be answers too: ask the worker whether a question is open


def is_answer(text):
    """The whole utterance is a yes / no / maybe / "mehet" / "töltsd le" / "mást"."""
    p = _squash(text)
    return bool(p) and bool(ANSWER.match(p))


def is_answer_like(text):
    """Worth asking the worker whether it is waiting for an answer: a yes / no or any short utterance."""
    return is_answer(text) or 0 < len(_squash(text).split()) < ANSWER_WORDS


# "halkítsd le harmincra", "hangerő 40 százalékra": a level to set, not an amount to change by
_NUMBER = r"(?:\d+|egy|ket|ketto|harom|negy|ot|hat|het|nyolc|kilenc|tiz|husz|harminc|negyven|otven|hatvan|hetven|nyolcvan|kilencven|szaz)\w*"
VOLUME_TO = re.compile(rf"\bszazalek(?:ra|ig)\b|\b{_NUMBER}(?:ra|re|ig)\b|\b\d+\s(?:ra|re|ig)\b|\bto\s+\d+")


def pending_for(reply, satellite):
    """The worker's /pending reply says it waits for an answer from this satellite (or from any satellite)."""
    if not isinstance(reply, dict) or reply.get("pending") is not True:
        return False
    if isinstance(reply.get("expires_in"), (int, float)) and reply["expires_in"] <= 0:
        return False
    wanted = reply.get("satellite")
    return not wanted or not satellite or wanted == satellite


def volume_absolute(text):
    return bool(VOLUME_TO.search(_squash(text)))


def has_claude(text):
    return bool(CLAUDE.search(_squash(text)))


def is_cancel(text):
    return bool(CANCEL.match(_squash(text)))


def has_stop_word(text):
    return bool(STOP_WORD.search(_squash(text)))


def stops_playback(text):
    """A stop word that is about the playback too, not only "mégse" (never mind)."""
    p = _squash(text)
    return has_stop_word(p) and p not in ("megse", "megsem")


def is_bare_stop(text):
    """Just a stop word ("állj", "elég", "stop", "hagyd abba"), with nothing saying what to stop."""
    p = _squash(text)
    return has_stop_word(p) and len(p.split()) <= 3 and not re.search(r"\b(?:zene\w*|film\w*|tv\w*|teve\w*|szam\w*)\b", p)


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

    Returns one of: ("cancel", ""), ("claude", reason), ("like", ""), ("save_to_playlist", name).
    conversation.py asks the worker about an open question (is_answer_like) before this."""
    if is_cancel(text):
        return "cancel", ""
    if has_claude(text):
        return "claude", "keyword"
    if is_answer(text):
        # A bare "igen" / "nem" with no open question: never a device action, let Claude make sense of it
        return "claude", "answer"
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

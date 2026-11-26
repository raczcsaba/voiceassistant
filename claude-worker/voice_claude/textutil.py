"""Small text helpers: forgiving name matching and TTS-safe output."""
import re
import unicodedata

from rapidfuzz import fuzz, process


def norm(text):
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def best_matches(query, choices, limit=3):
    """choices: dict key -> label. Returns [(key, label, score)] best first."""
    wanted = norm(query)
    labels = {k: norm(v) for k, v in choices.items()}
    exact = [(k, choices[k], 100.0) for k, v in labels.items() if v == wanted]
    if exact:
        return exact[:limit]
    found = process.extract(wanted, labels, scorer=fuzz.WRatio, limit=limit)
    return [(key, choices[key], score) for _label, score, key in found]


_URL = re.compile(r"https?://\S+|www\.\S+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️]")


def for_speech(text, limit=700):
    """Strip what TTS would read badly: markdown, URLs, emoji, list bullets."""
    text = _URL.sub("", text or "")
    text = _EMOJI.sub("", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^\s*(#+|[-*•]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`#>|]+", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\s*\n+\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[: end + 1] if end > limit // 2 else cut.rstrip() + "…"
    return text

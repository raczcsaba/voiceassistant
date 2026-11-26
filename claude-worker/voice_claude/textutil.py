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


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def shorten(text, limit=180, keep_question=False):
    """Keep whole sentences from the start within limit characters (at least the first one, cut at a word if it
    alone is too long). keep_question: if the answer ended with a question that got cut, keep that question too."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    sentences = [s for s in _SENTENCE_END.split(text) if s]
    question = sentences[-1] if keep_question and sentences[-1].endswith("?") else None
    budget = limit - (len(question) + 1 if question else 0)
    out = []
    for s in sentences:
        if s is question:
            break
        if len(" ".join(out + [s])) > budget:
            break
        out.append(s)
    if not out:
        first = sentences[0]
        if question and first is question:
            first, question = question, None
        cut = first[: max(budget, 40)].rsplit(" ", 1)[0].rstrip(",;:–- ")
        out = [cut + ("" if cut.endswith((".", "!", "?")) else ".")]
    if question:
        out.append(question)
    return " ".join(out)

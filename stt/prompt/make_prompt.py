#!/usr/bin/env python3
"""Build the Whisper vocabulary prompt from the household library (JSON from fetch_library.py on stdin).

Whisper uses the prompt as "the text that came before", so names in it are recognised and spelled
the way they are written. whisper.cpp keeps at most 224 prompt tokens (the LAST ones if it is longer),
so this stays under TOKEN_BUDGET with a margin: one short Hungarian command sentence, then the most
likely artists and film/series titles, foreign-sounding names first (Hungarian words are easy anyway).

The output is personal (library names): it lives in /opt/voice/stt_prompt.txt, never in the repo.
Usage: python make_prompt.py [--out FILE] [--budget N] < library.json
"""
import argparse
import json
import os
import re
import sys
import tempfile

TOKEN_BUDGET = 215  # estimate; ~5% above the real count, whisper.cpp's hard cap is 224
LEAD = "Hangvezérlés: kapcsold fel a lámpát, indítsd el a filmet, játssz egy kis zenét."
SKIP_ARTISTS = {"various artists", "unknown artist", "[unknown]"}
HUNGARIAN_LETTERS = set("áéíóöőúüű")
RELEASE_JUNK = re.compile(r"\s(S\d\d(-S\d\d)?|COMPLETE|\d{3,4}p|WEB-DL)\b.*$")


def tokens(text):
    """Rough Whisper (multilingual tiktoken) count; checked against the real tokenizer it overestimates a bit.
    Hungarian and English words cost ~1 token per 3 letters, punctuation and spaces before words ~1 each."""
    count = 0
    for word in re.findall(r"\w+|[^\w\s]", text):
        if word.isalnum():
            accents = sum(c in HUNGARIAN_LETTERS for c in word.lower())
            count += max(1, -(-len(word) // 3)) + accents // 2
        else:
            count += 1
    return count


def latin(text):
    return bool(text) and all(ord(c) < 0x250 or c in "–½" for c in text)


def clean(name):
    name = name.replace("_", " ")
    if "." in name and " " not in name:  # American.Psycho.Uncut
        name = name.replace(".", " ")
    return re.sub(r"\s+", " ", RELEASE_JUNK.sub("", name)).strip(" -–:,")


def artists(library):
    score = {}
    for name in library.get("favorites", []):
        score[name] = score.get(name, 0) + 400
    for name, played in library.get("played", {}).items():
        score[name] = score.get(name, 0) + played
    for name in library.get("library", []):
        score[name] = score.get(name, 0) + 300
    for rank, name in enumerate(library.get("recent", [])):
        score[name] = score.get(name, 0) + 200 - rank
    out, seen = [], set()
    for name in sorted(score, key=lambda n: -score[n]):
        tidy = clean(name)
        if (not latin(tidy) or tidy.lower() in SKIP_ARTISTS or re.search(r"\.(jpe?g|png|mp3)$", tidy, re.I)
                or tidy.lower() in seen):
            continue
        seen.add(tidy.lower())
        out.append(tidy)
    return out


def spoken(name):
    """How a title is said: long titles by their part before the colon ("Frieren", "Castlevania")."""
    name = clean(name)
    head = name.split(":")[0].strip()
    return head if ":" in name and len(name.split()) > 3 and len(head) > 2 else name


def titles(library):
    """Foreign-sounding film/series names first (Hungarian titles come out fine without help)."""
    easy, hard, seen = [], [], set()
    for original, hungarian in library.get("titles", {}).items():
        for name in (hungarian, original):
            if not name or not latin(name):
                continue
            name = spoken(name)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            (easy if set(name.lower()) & HUNGARIAN_LETTERS else hard).append(name)
    return hard + easy


def build(library, budget=TOKEN_BUDGET):
    names_a, names_t = artists(library), titles(library)
    chosen_a, chosen_t = [], []
    used = tokens(LEAD) + 6  # + the two labels
    # alternate so neither list starves
    queue = []
    for i in range(max(len(names_a), len(names_t))):
        queue += [("a", names_a[i])] if i < len(names_a) else []
        queue += [("t", names_t[i])] if i < len(names_t) else []
    for kind, name in queue:
        cost = tokens(name) + 1
        if used + cost > budget:
            continue
        used += cost
        (chosen_a if kind == "a" else chosen_t).append(name)
    def render():
        parts = [LEAD]
        if chosen_t:
            parts.append("Filmek és sorozatok: " + ", ".join(chosen_t) + ".")
        if chosen_a:
            parts.append("Előadók: " + ", ".join(chosen_a) + ".")
        return " ".join(parts)

    while tokens(render()) > budget and (chosen_a or chosen_t):
        (chosen_a if len(chosen_a) >= len(chosen_t) else chosen_t).pop()
    return render()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/opt/voice/stt_prompt.txt")
    parser.add_argument("--budget", type=int, default=TOKEN_BUDGET)
    args = parser.parse_args()
    library = json.load(sys.stdin)
    if not library.get("titles") and not library.get("library"):
        sys.exit("library data is empty; keeping the old prompt")
    text = build(library, args.budget)
    folder = os.path.dirname(os.path.abspath(args.out))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as f:
        f.write(text + "\n")
    os.chmod(f.name, 0o644)
    os.replace(f.name, args.out)
    print(f"wrote {args.out}: {len(text)} chars, ~{tokens(text)} tokens")


if __name__ == "__main__":
    main()

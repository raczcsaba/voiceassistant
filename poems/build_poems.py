#!/usr/bin/env python3
"""Build poems.json for the dashboard's daily poem from Hungarian Wikisource.

Only poets who died more than 70 years ago, so every poem is public domain in the EU.
    python3 build_poems.py            writes poems.json next to this file
    python3 build_poems.py --split    also writes dist/poems/{meta.json,p/<n>.json} for the dashboard card
                                      (copy dist/poems to Home Assistant's www/ folder -> /local/poems/)
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

API = "https://hu.wikisource.org/w/api.php"
UA = "HomeDashboardPoems/1.0 (personal home dashboard)"
POETS = [
    "Petőfi Sándor", "Arany János", "Ady Endre", "József Attila", "Radnóti Miklós", "Kosztolányi Dezső",
    "Babits Mihály", "Juhász Gyula", "Tóth Árpád", "Vörösmarty Mihály", "Csokonai Vitéz Mihály",
    "Berzsenyi Dániel", "Kölcsey Ferenc", "Reviczky Gyula", "Vajda János",
    "Kiss József", "Komjáthy Jenő", "Dsida Jenő", "Karinthy Frigyes",
]
# Long enough to be a poem, short enough for a card and a few minutes of reading
MIN_LINES, MAX_LINES = 4, 40
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poems.json")


def api(**params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("Wikisource did not answer: " + url)


def titles_of(poet):
    data = api(action="query", titles=f"Szerző:{poet}", prop="links", pllimit="max", plnamespace=0)
    page = next(iter(data["query"]["pages"].values()))
    return [l["title"] for l in page.get("links", [])]


def clean(text):
    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>|&nbsp;", " ", text)
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()]
    out = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", out)


def looks_like_verse(text):
    """Leaves out prose, editors' notes in brackets and verse numbers."""
    lines = [l for l in text.splitlines() if l]
    return (not re.search(r"[<>{}\[\]|=]|&\w+;", text)
            and max(len(l) for l in lines) <= 100
            and not any(re.match(r"\d+\.? ", l) for l in lines))


def poem_from(page, poet):
    wikitext = page["revisions"][0]["slots"]["main"]["*"]
    head = re.search(r"szerző\s*=\s*([^\n|]+)", wikitext)
    if not head or poet.split()[0] not in head.group(1):
        return None
    blocks = re.findall(r"<poem[^>]*>(.*?)</poem>", wikitext, flags=re.S)
    # Several poem blocks or section headings mean a cycle or a collection, not one poem
    if len(blocks) != 1 or re.search(r"^==", wikitext, flags=re.M):
        return None
    text = clean(blocks[0])
    lines = [l for l in text.splitlines() if l]
    if not MIN_LINES <= len(lines) <= MAX_LINES or not looks_like_verse(text):
        return None
    year = re.search(r"\b(1[5-9]\d\d)\b", re.search(r"megjegyzés\s*=([^\n]*)", wikitext).group(1) if "megjegyzés" in wikitext else "")
    return {"author": poet, "title": page["title"].split(" (")[0], "year": year.group(1) if year else None,
            "text": text, "source": "https://hu.wikisource.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_"))}


def main():
    poems, seen = [], set()
    for poet in POETS:
        titles = titles_of(poet)
        kept = 0
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            data = api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(batch))
            for page in data["query"]["pages"].values():
                if "revisions" not in page:
                    continue
                poem = poem_from(page, poet)
                if poem and (poem["author"], poem["text"][:80]) not in seen:
                    seen.add((poem["author"], poem["text"][:80]))
                    poems.append(poem)
                    kept += 1
            time.sleep(1)
        print(f"{poet}: {kept} of {len(titles)} pages kept", flush=True)
    poems.sort(key=lambda p: (p["author"], p["title"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(poems, f, ensure_ascii=False, indent=0)
    print(f"{len(poems)} poems written to {OUT}")


def split(start=None):
    """One file per poem in a shuffled (fixed-seed) order, plus meta.json: the card shows poem
    (days since start) mod count, so every poem comes up once before any repeats."""
    import random
    from datetime import date
    poems = json.load(open(OUT, encoding="utf-8"))
    random.Random(42).shuffle(poems)
    d = os.path.join(os.path.dirname(OUT), "dist", "poems")
    os.makedirs(os.path.join(d, "p"), exist_ok=True)
    for i, poem in enumerate(poems):
        with open(os.path.join(d, "p", f"{i}.json"), "w", encoding="utf-8") as f:
            json.dump(poem, f, ensure_ascii=False)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump({"count": len(poems), "start": start or date.today().isoformat()}, f)
    print(f"{len(poems)} poem files written to {d}")


if __name__ == "__main__":
    import sys
    if not (os.path.exists(OUT) and "--split" in sys.argv):
        main()
    if "--split" in sys.argv:
        split()

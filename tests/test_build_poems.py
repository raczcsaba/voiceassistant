"""Wikitext cleaning and poem filtering in poems/build_poems.py (no network)."""
import json

import build_poems as bp
import pytest

VERSE = "Első sor itt van\nMásodik sor jön\n\nHarmadik sor\nNegyedik sor vége"


def page(body, title="Szeptember végén (Petőfi)", header="{{fej\n| szerző = Petőfi Sándor\n| megjegyzés = Koltó, 1847. szeptember\n}}"):
    return {"title": title, "revisions": [{"slots": {"main": {"*": f"{header}\n<poem>\n{body}\n</poem>"}}}]}


def test_clean_strips_markup():
    raw = "Egy [[Link|szép]] sor<ref>forrás</ref><br/>''Dőlt'' {{sablon}} sor&nbsp;itt\n\n\n\nVége"
    assert bp.clean(raw) == "Egy szép sor\nDőlt sor itt\n\nVége"


@pytest.mark.parametrize("text, ok", [
    (VERSE, True),
    ("Egy sor | táblázat\nMásik", False),
    ("1. Első versszak\nmásodik", False),
    ("x" * 101 + "\nrövid", False),
])
def test_looks_like_verse(text, ok):
    assert bp.looks_like_verse(text) is ok


def test_poem_from_page():
    poem = bp.poem_from(page(VERSE), "Petőfi Sándor")
    assert poem["author"] == "Petőfi Sándor"
    assert poem["title"] == "Szeptember végén"
    assert poem["year"] == "1847"
    assert poem["text"] == VERSE
    assert poem["source"].startswith("https://hu.wikisource.org/wiki/Szeptember_v%C3%A9g%C3%A9n")


def test_poem_from_rejects_other_author_short_and_collections():
    assert bp.poem_from(page(VERSE), "Arany János") is None
    assert bp.poem_from(page("Csak\nhárom\nsor"), "Petőfi Sándor") is None
    two = page(VERSE + "\n</poem>\n<poem>\n" + VERSE)
    assert bp.poem_from(two, "Petőfi Sándor") is None


def test_poem_from_note_without_equals_sign():
    # "megjegyzés" in the text but not as a header field used to crash with AttributeError
    header = "{{fej\n| szerző = Petőfi Sándor\n}}\nLásd a megjegyzés részt."
    poem = bp.poem_from(page(VERSE, header=header), "Petőfi Sándor")
    assert poem is not None and poem["year"] is None


def test_split_writes_one_file_per_poem(tmp_path, monkeypatch):
    poems = [{"author": "A", "title": str(i), "year": None, "text": VERSE, "source": ""} for i in range(5)]
    out = tmp_path / "poems.json"
    out.write_text(json.dumps(poems), encoding="utf-8")
    monkeypatch.setattr(bp, "OUT", str(out))
    bp.split(start="2026-01-01")
    meta = json.loads((tmp_path / "dist/poems/meta.json").read_text())
    assert meta == {"count": 5, "start": "2026-01-01"}
    titles = sorted(json.loads((tmp_path / f"dist/poems/p/{i}.json").read_text())["title"] for i in range(5))
    assert titles == ["0", "1", "2", "3", "4"]

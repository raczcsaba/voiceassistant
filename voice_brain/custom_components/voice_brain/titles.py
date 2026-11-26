"""Library film and show names, plus their Hungarian titles, matched forgivingly against what was heard."""
import difflib
import json
import logging
import os
import re
import unicodedata

from custom_components.jellyfin_panel import _jellyfin, _user_id

_LOGGER = logging.getLogger(__name__)
CACHE = "voice_titles.json"
MATCH_CUTOFF = 0.7
SEARCH_PATHS = {"Movie": "/Items/RemoteSearch/Movie", "Series": "/Items/RemoteSearch/Series"}


def key(title):
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"(filmet|film)$", "", re.sub(r"[^a-z0-9]", "", text))


def _known(titles):
    known = {}
    for name, local in titles.items():
        known[key(name)] = name
        if local:
            known[key(local)] = name
    known.pop("", None)
    return known


def resolve(query, titles):
    """The library name closest to the query, or None. titles maps each library name to its Hungarian title."""
    known = _known(titles)
    wanted = key(query)
    if wanted in known:
        return known[wanted]
    close = difflib.get_close_matches(wanted, known, 1, MATCH_CUTOFF)
    return known[close[0]] if close else None


def best(query, titles):
    """(library name, similarity 0..1) of the closest original or Hungarian title; (None, 0) if nothing is close.
    Also tries the query without a Hungarian accusative ending ("Mátrixot" -> "Mátrix")."""
    known = _known(titles)
    wanted = key(query)
    if not wanted or not known:
        return None, 0.0
    variants = {wanted, re.sub(r"(ot|et|at|t)$", "", wanted)} - {""}
    score, found = max((difflib.SequenceMatcher(None, w, k).ratio(), k) for w in variants for k in known)
    return known[found], score


async def _hungarian_title(hass, item):
    ids = item.get("ProviderIds") or {}
    info = {"Name": item["Name"], "Year": item.get("ProductionYear"), "MetadataLanguage": "hu",
            "MetadataCountryCode": "HU", "ProviderIds": ids}
    status, found = await _jellyfin(hass, "POST", SEARCH_PATHS[item["Type"]], json={"SearchInfo": info})
    if status != 200 or not found:
        return None
    for result in found:
        theirs = result.get("ProviderIds") or {}
        if any(ids.get(k) and ids.get(k) == theirs.get(k) for k in ("Tmdb", "Imdb", "Tvdb")):
            return result["Name"]
    return None


async def async_refresh(hass, titles):
    """Add newly arrived library items; titles already looked up stay cached in the config folder."""
    user = await _user_id(hass)
    status, data = await _jellyfin(hass, "GET", f"/Users/{user}/Items", {
        "IncludeItemTypes": "Movie,Series", "Recursive": "true", "Fields": "ProviderIds,ProductionYear"})
    if status != 200:
        return
    items = data.get("Items", [])
    current = {item["Name"] for item in items}
    for name in set(titles) - current:
        del titles[name]
    for item in items:
        if item["Name"] not in titles:
            try:
                titles[item["Name"]] = await _hungarian_title(hass, item)
            except Exception as err:  # Retried next time; the English name still works
                _LOGGER.debug("no Hungarian title for %s: %r", item["Name"], err)
    await hass.async_add_executor_job(_save, hass.config.path(CACHE), titles)


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, titles):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=0)

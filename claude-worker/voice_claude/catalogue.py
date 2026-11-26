"""The library catalogue: a compact, deterministic text of the user's music and films.

It is sent as a cached system block, so the text must be byte-stable between refreshes when
the library has not changed (everything is sorted, nothing time-dependent is included).
"""
import asyncio
import json
import logging
import os
import time

_LOGGER = logging.getLogger(__name__)


async def _all_library(ma, media_type, page=500, cap=5000):
    items, offset = [], 0
    while offset < cap:
        batch = await ma.call(f"music/{media_type}/library_items", limit=page, offset=offset)
        items.extend(batch or [])
        if not batch or len(batch) < page:
            break
        offset += page
    return items


def playlist_info(pl):
    """Who owns a playlist and whether we may add to it."""
    providers = [m.get("provider_domain") for m in pl.get("provider_mappings") or []]
    if pl.get("is_editable"):
        kind = "own"
    elif "builtin" in providers:
        kind = "smart"
    else:
        kind = "provider"
    return {"id": str(pl["item_id"]), "uri": pl["uri"], "name": pl["name"], "owner": pl.get("owner"),
            "editable": bool(pl.get("is_editable")), "kind": kind, "favorite": bool(pl.get("favorite"))}


async def playlist_tracks(ma, playlist_id, provider="library", limit=None):
    tracks = await ma.call("music/playlists/playlist_tracks", item_id=str(playlist_id),
                           provider_instance_id_or_domain=provider)
    tracks = tracks or []
    return tracks[:limit] if limit else tracks


def _artists(item):
    return ", ".join(a["name"] for a in item.get("artists") or [])


async def build(ma, jf, cfg):
    """Fetch everything and return the catalogue dict (text plus lookup tables)."""
    started = time.monotonic()
    artists, albums, tracks, playlists_raw = await asyncio.gather(
        _all_library(ma, "artists"), _all_library(ma, "albums"), _all_library(ma, "tracks"), _all_library(ma, "playlists"))
    playlists = sorted((playlist_info(p) for p in playlists_raw), key=lambda p: (p["kind"] != "own", p["name"].lower(), p["id"]))

    sem = asyncio.Semaphore(4)

    async def count(pl):
        async with sem:
            try:
                pl["tracks"] = len(await playlist_tracks(ma, pl["id"]))
            except Exception as err:
                _LOGGER.warning("track count for playlist %s failed: %r", pl["name"], err)

    t_lib = time.monotonic()
    await asyncio.gather(*(count(p) for p in playlists if p["editable"]))
    t_counts = time.monotonic()

    films, titles = [], {}
    if jf is not None:
        try:
            items = await jf.items()
            titles = await jf.hungarian_titles(items)
            for item in sorted(items, key=lambda i: (i.get("Type") != "Movie", i["Name"].lower())):
                films.append({"id": item["Id"], "name": item["Name"], "type": item.get("Type"),
                              "year": item.get("ProductionYear"), "hu": titles.get(item["Name"]),
                              "original": item.get("OriginalTitle")})
        except Exception as err:
            _LOGGER.warning("Jellyfin catalogue failed: %r", err)
    for n, film in enumerate(films, 1):
        film["ref"] = f"m{n}"
    _LOGGER.info("catalogue fetch: library %.1fs, playlist counts %.1fs, jellyfin %.1fs",
                 t_lib - started, t_counts - t_lib, time.monotonic() - t_counts)

    max_artists = cfg.get("max_artists", 600)
    max_tracks = cfg.get("max_tracks", 600)
    # Library artists plus everyone on a library track (MA counts many more artists in its database)
    names = {a["name"] for a in artists} | {a["name"] for t in tracks for a in t.get("artists") or [] if a.get("name")}
    names |= {a["name"] for al in albums for a in al.get("artists") or [] if a.get("name")}
    artist_names = sorted(names, key=str.lower)[:max_artists]
    track_rows = sorted(tracks, key=lambda t: (_artists(t).lower(), t["name"].lower()))[:max_tracks]

    lines = ["MUSIC LIBRARY (Music Assistant). Library items play by uri: library://track/<n>, library://album/<n>, library://playlist/<n>.",
             f"Artists ({len(artist_names)}): " + "; ".join(artist_names), "",
             f"Albums ({len(albums)}; format: <n> title – artist):"]
    lines += [f"{a['item_id']} {a['name']} – {_artists(a)}" for a in sorted(albums, key=lambda a: a["name"].lower())]
    lines += ["",
             f"Tracks ({len(tracks)}; format: <n> title – artist; * = favourite):"]
    for t in track_rows:
        version = f" ({t['version']})" if t.get("version") else ""
        lines.append(f"{t['item_id']} {t['name']}{version} – {_artists(t)}{' *' if t.get('favorite') else ''}")
    lines += ["", f"Playlists ({len(playlists)}; format: <n> name [kind]; own = the user's editable playlist):"]
    for p in playlists:
        if p["kind"] == "own":
            tag = f"own, {p['tracks']} tracks" if "tracks" in p else "own"
        elif p["kind"] == "smart":
            tag = "Music Assistant smart playlist"
        else:
            tag = f"{p['owner'] or 'provider'}"
        lines.append(f"{p['id']} {p['name']} [{tag}{', *' if p['favorite'] else ''}]")
    lines += ["", f"FILMS AND SERIES (Jellyfin; {len(films)}; format: <ref> type | title (year) | hu: Hungarian title"
              " | orig: original title). Start one with play_movie(<ref>)."]
    for f in films:
        parts = [f"{f['ref']} {'film' if f['type'] == 'Movie' else 'series'}", f"{f['name']} ({f['year'] or '?'})"]
        if f["hu"] and f["hu"] != f["name"]:
            parts.append(f"hu: {f['hu']}")
        if f["original"] and f["original"] not in (f["name"], f["hu"]):
            parts.append(f"orig: {f['original']}")
        lines.append(" | ".join(parts))

    text = "\n".join(lines)
    return {
        "built_at": time.time(),
        "build_seconds": round(time.monotonic() - started, 1),
        "counts": {"artists": len(artist_names), "albums": len(albums), "tracks": len(tracks), "favorite_tracks": sum(1 for t in tracks if t.get("favorite")),
                   "playlists": len(playlists), "own_playlists": sum(1 for p in playlists if p["editable"]),
                   "films": sum(1 for f in films if f["type"] == "Movie"), "series": sum(1 for f in films if f["type"] != "Movie")},
        "playlists": playlists,
        "films": films,
        "text": text,
    }


class Catalogue:
    """Holds the current catalogue, persists it, and refreshes it when stale."""

    def __init__(self, path, builder, refresh_hours=6):
        self.path = path
        self.builder = builder
        self.max_age = refresh_hours * 3600
        self.data = None
        self._lock = asyncio.Lock()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except ValueError:
                self.data = None

    def stale(self):
        return self.data is None or time.time() - self.data.get("built_at", 0) > self.max_age

    async def refresh(self, force=False):
        async with self._lock:
            if not force and not self.stale():
                return self.data
            data = await self.builder()
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.data = data
            _LOGGER.info("catalogue rebuilt in %ss: %s, %d chars", data["build_seconds"], data["counts"], len(data["text"]))
            return data

    async def get(self):
        if self.stale():
            try:
                await self.refresh()
            except Exception as err:
                _LOGGER.warning("catalogue refresh failed: %r", err)
                if self.data is None:
                    raise
        return self.data

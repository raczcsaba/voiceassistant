"""The tools Claude can call, plus the player and playlist lookups /quick shares with them.

Every write goes through _write(), which in dry-run mode only logs the exact command.
Results are compact JSON with trimmed fields.
"""
import asyncio
import json
import logging

from . import catalogue as cat
from .textutil import best_matches, norm

_LOGGER = logging.getLogger(__name__)
MEDIA_TYPES = ["track", "artist", "album", "playlist"]
ENQUEUE = {"replace": "replace", "next": "next", "add": "add", "play": "play"}


class ToolError(Exception):
    """A failure Claude should see and explain to the user."""


def trim(item):
    """Reduce a Music Assistant media item to the fields Claude needs."""
    if not item:
        return None
    out = {"uri": item.get("uri"), "type": item.get("media_type"), "name": item.get("name")}
    if item.get("version"):
        out["version"] = item["version"]
    artists = [a.get("name") for a in item.get("artists") or [] if a.get("name")]
    if artists:
        out["artist"] = ", ".join(artists)
    album = item.get("album")
    if isinstance(album, dict) and album.get("name"):
        out["album"] = album["name"]
    if item.get("year"):
        out["year"] = item["year"]
    if item.get("duration"):
        out["sec"] = int(item["duration"])
    if item.get("favorite"):
        out["favourite"] = True
    if item.get("provider") == "library":
        out["in_library"] = True
    if item.get("media_type") == "playlist":
        out["owner"] = item.get("owner")
        out["editable"] = bool(item.get("is_editable"))
    return out


class Players:
    """Music Assistant players as Home Assistant sees them (entity, name, queue, state)."""

    def __init__(self, ha, default_player=None, aliases=None):
        self.ha = ha
        self.default = default_player
        self.aliases = aliases or {}

    async def all(self):
        states = await self.ha.states()
        out = []
        for st in states:
            attrs = st.get("attributes") or {}
            if not st["entity_id"].startswith("media_player.") or "mass_player_type" not in attrs:
                continue
            if st["state"] == "unavailable":
                continue
            out.append({"entity_id": st["entity_id"], "name": (attrs.get("friendly_name") or "").strip(),
                        "state": st["state"], "queue": attrs.get("active_queue"),
                        "group": attrs.get("mass_player_type") == "group",
                        "members": attrs.get("group_members") or [],
                        "title": attrs.get("media_title"), "artist": attrs.get("media_artist")})
        return out

    async def resolve(self, wanted=None):
        """The named player, else the one playing, else the default. Raises ToolError if unknown."""
        players = await self.all()
        by_entity = {p["entity_id"]: p for p in players}
        if wanted:
            if wanted in by_entity:
                return by_entity[wanted]
            if not wanted.startswith("media_player.") and f"media_player.{wanted}" in by_entity:
                return by_entity[f"media_player.{wanted}"]
            labels = {}
            for p in players:
                labels[p["entity_id"]] = p["name"]
                for n, alias in enumerate(self.aliases.get(p["entity_id"], [])):
                    labels[f"{p['entity_id']}#{n}"] = alias
            found = best_matches(wanted, labels, limit=1)
            if found and found[0][2] >= 80:
                return by_entity[found[0][0].split("#")[0]]
            raise ToolError(f"unknown player {wanted!r}; known: " + ", ".join(p["name"] for p in players))
        playing = [p for p in players if p["state"] == "playing"]
        if playing:
            groups = [p for p in playing if p["group"]]
            return (groups or playing)[0]
        if self.default in by_entity:
            return by_entity[self.default]
        if players:
            return players[0]
        raise ToolError("no Music Assistant player is available")


class Tools:
    def __init__(self, ma, jf, ha, catalogue, cfg, dry_run=False):
        self.ma = ma
        self.jf = jf
        self.ha = ha
        self.catalogue = catalogue
        self.cfg = cfg
        self.dry_run = dry_run
        mcfg = cfg["music_assistant"]
        self.provider = mcfg.get("playlist_provider")
        self.players = Players(ha, mcfg.get("default_player"), mcfg.get("player_aliases"))
        self.writes = []  # (kind, target, args) of every write, real or dry-run
        self.background = set()
        self.on_background_error = None  # async callback(text) for failures after the tool returned

    # ---------------------------------------------------------------- writes
    async def _write(self, command, **args):
        self.writes.append(("ma", command, args))
        if self.dry_run:
            _LOGGER.info("[dry-run] would send MA command %s %s", command, json.dumps(args, ensure_ascii=False))
            return None
        _LOGGER.info("MA command %s %s", command, json.dumps(args, ensure_ascii=False))
        return await self.ma.call(command, **args)

    # ---------------------------------------------------------------- lookups
    async def playlists(self, refresh=False):
        """All library playlists as dicts from catalogue.playlist_info (fresh from MA)."""
        raw = await self.ma.call("music/playlists/library_items", limit=500)
        return [cat.playlist_info(p) for p in raw or []]

    async def match_playlist(self, name, editable_only=False, cutoff=85):
        """(playlist, alternatives). playlist is None when no confident match."""
        pls = await self.playlists()
        if editable_only:
            pls = [p for p in pls if p["editable"]]
        if not name:
            return None, pls[:3]
        text = str(name).strip()
        for p in pls:
            if text in (p["uri"], p["id"]):
                return p, []
        found = best_matches(text, {p["id"]: p["name"] for p in pls}, limit=3)
        by_id = {p["id"]: p for p in pls}
        alts = [by_id[k] for k, _label, _score in found]
        if found and found[0][2] >= cutoff:
            top = found[0]
            second = found[1][2] if len(found) > 1 else 0
            same_name = len(found) > 1 and norm(found[1][1]) == norm(top[1])
            if top[2] == 100 or top[2] - second >= 5 or same_name:
                return by_id[top[0]], alts[1:]
        return None, alts

    async def current_track(self, player=None):
        p = await self.players.resolve(player)
        queue = await self.ma.call("player_queues/get_active_queue", player_id=p["queue"] or p["entity_id"])
        item = ((queue or {}).get("current_item") or {}).get("media_item")
        return p, queue, item

    # ---------------------------------------------------------------- tools
    async def search_music(self, query, media_types=None, limit=5, library_only=False):
        types = [t for t in (media_types or MEDIA_TYPES) if t in MEDIA_TYPES] or MEDIA_TYPES
        limit = max(1, min(int(limit or 5), 15))
        res = await self.ma.call("music/search", search_query=query, media_types=types, limit=limit,
                                 library_only=bool(library_only))
        out = {}
        for key in ("tracks", "artists", "albums", "playlists"):
            items = [trim(i) for i in (res or {}).get(key) or []][:limit]
            if items:
                out[key] = items
        return out or {"result": "nothing found"}

    async def get_playlist_tracks(self, playlist, limit=40):
        pl, alts = await self.match_playlist(playlist)
        provider, item_id = "library", None
        if pl:
            item_id, name = pl["id"], pl["name"]
        elif "://playlist/" in str(playlist):
            provider, item_id = str(playlist).split("://playlist/", 1)
            name = playlist
        else:
            raise ToolError("no playlist matches; closest: " + ", ".join(a["name"] for a in alts))
        tracks = await cat.playlist_tracks(self.ma, item_id, provider)
        limit = max(1, min(int(limit or 40), 100))
        return {"playlist": name, "uri": pl["uri"] if pl else playlist, "total": len(tracks),
                "tracks": [trim(t) for t in tracks[:limit]]}

    async def get_now_playing(self, player=None):
        if player:
            p, queue, item = await self.current_track(player)
            return self._now(p, queue, item)
        out = []
        for p in await self.players.all():
            if p["state"] in ("playing", "paused") or p["entity_id"] == self.players.default:
                queue = await self.ma.call("player_queues/get_active_queue", player_id=p["queue"] or p["entity_id"])
                item = ((queue or {}).get("current_item") or {}).get("media_item")
                out.append(self._now(p, queue, item))
        return {"players": out}

    @staticmethod
    def _now(p, queue, item):
        return {"player": p["entity_id"], "name": p["name"], "state": p["state"],
                "track": trim(item) if item else None,
                "queue_items": (queue or {}).get("items"), "shuffle": (queue or {}).get("shuffle_enabled")}

    async def play_music(self, uris, player=None, enqueue="replace", radio_mode=False, shuffle=False):
        if isinstance(uris, str):
            uris = [uris]
        uris = [u for u in uris or [] if isinstance(u, str) and "://" in u]
        if not uris:
            raise ToolError("no valid uris given")
        option = ENQUEUE.get(enqueue or "replace")
        if not option:
            raise ToolError("enqueue must be replace, next or add")
        p = await self.players.resolve(player)
        queue_id = p["queue"] or p["entity_id"]
        await self._write("player_queues/play_media", queue_id=queue_id, media=uris, option=option,
                          radio_mode=bool(radio_mode))
        if shuffle:
            await self._write("player_queues/shuffle", queue_id=queue_id, shuffle_enabled=True)
        return {"ok": True, "player": p["name"], "items": len(uris), "enqueue": option,
                "radio_mode": bool(radio_mode), "shuffle": bool(shuffle)}

    async def create_playlist(self, name):
        name = (name or "").strip()
        if not name:
            raise ToolError("playlist name is empty")
        existing, _ = await self.match_playlist(name, editable_only=True, cutoff=100)
        if existing and norm(existing["name"]) == norm(name):
            return {"ok": False, "exists": True, "playlist": existing,
                    "note": "an own playlist with this name exists; use add_to_playlist or choose another name"}
        args = {"name": name}
        if self.provider:
            args["provider_instance_or_domain"] = self.provider
        result = await self._write("music/playlists/create_playlist", **args)
        if self.dry_run:
            return {"ok": True, "playlist": {"id": "dry-run", "uri": "library://playlist/dry-run", "name": name}}
        return {"ok": True, "playlist": cat.playlist_info(result)}

    async def add_to_playlist(self, playlist, uris):
        if isinstance(uris, str):
            uris = [uris]
        uris = [u for u in uris or [] if isinstance(u, str) and "://" in u]
        if not uris:
            raise ToolError("no valid uris given")
        if self.dry_run and str(playlist) in ("dry-run", "library://playlist/dry-run"):
            pl = {"id": "dry-run", "name": "(dry-run playlist)", "uri": "library://playlist/dry-run"}
        else:
            pl, alts = await self.match_playlist(playlist, editable_only=True)
            if not pl:
                raise ToolError("no own (editable) playlist matches; closest: " + ", ".join(a["name"] for a in alts))
        await self._write("music/playlists/add_playlist_tracks", db_playlist_id=pl["id"], uris=uris)
        return {"ok": True, "playlist": pl["name"], "added": len(uris)}

    async def like(self, uri=None, player=None):
        if not uri or uri == "current":
            p, _queue, item = await self.current_track(player)
            if not item:
                raise ToolError(f"nothing is playing on {p['name']}")
            uri, label = item["uri"], trim(item)
        else:
            label = {"uri": uri}
        await self._write("music/favorites/add_item", item=uri)
        return {"ok": True, "favourited": label}

    async def search_movies(self, query, limit=5):
        data = await self.catalogue.get()
        films = data.get("films", []) if data else []
        choices = {}
        for f in films:
            choices[f["ref"] + "#n"] = f["name"]
            if f.get("hu"):
                choices[f["ref"] + "#h"] = f["hu"]
            if f.get("original"):
                choices[f["ref"] + "#o"] = f["original"]
        by_ref = {f["ref"]: f for f in films}
        hits, seen = [], set()
        for key, _label, score in best_matches(query, choices, limit=10):
            ref = key.split("#")[0]
            if score >= 60 and ref not in seen:
                seen.add(ref)
                hits.append({**self._film(by_ref[ref]), "score": round(score)})
        if self.jf is not None:
            try:
                for item in await self.jf.items(search=query, limit=5):
                    if not any(h["id"] == item["Id"] for h in hits):
                        hits.append({"id": item["Id"], "name": item["Name"], "type": item.get("Type"),
                                     "year": item.get("ProductionYear"), "source": "jellyfin search"})
            except Exception as err:
                _LOGGER.warning("Jellyfin search failed: %r", err)
        return {"results": hits[: max(1, min(int(limit or 5), 10))]} if hits else {"results": [], "note": "not in the library"}

    @staticmethod
    def _film(f):
        return {"ref": f["ref"], "id": f["id"], "name": f["name"], "hu": f.get("hu"), "type": f.get("type"), "year": f.get("year")}

    async def play_movie(self, item, from_start=False):
        data = await self.catalogue.get()
        films = {f["ref"]: f for f in (data or {}).get("films", [])}
        item_id = films[item]["id"] if item in films else str(item)
        if not item_id.isalnum():
            raise ToolError("unknown film reference")
        info = await self.jf.item(item_id)
        target, label = info, info.get("Name")
        if info.get("Type") == "Series":
            target = await self.jf.next_episode(item_id)
            if not target:
                raise ToolError("the series has no episodes")
            label = f"{info.get('Name')} S{target.get('ParentIndexNumber', 0)}E{target.get('IndexNumber', 0)} {target.get('Name')}"
        position = 0 if from_start else int((target.get("UserData") or {}).get("PlaybackPositionTicks") or 0)
        hcfg = self.cfg["home_assistant"]
        body = {"device": hcfg.get("jellyfin_play_device", "tv"), "item_id": target["Id"], "position": position}
        self.writes.append(("ha", hcfg["jellyfin_play_path"], body))
        if self.dry_run:
            _LOGGER.info("[dry-run] would POST HA %s %s", hcfg["jellyfin_play_path"], body)
        else:
            # Waking the TV and starting playback takes up to a minute; don't hold the loop for it.
            task = asyncio.create_task(self._play_on_tv(hcfg["jellyfin_play_path"], body, label))
            self.background.add(task)
            task.add_done_callback(self.background.discard)
        return {"ok": True, "starting": label, "resume_minutes": round(position / 600_000_000) if position else 0,
                "note": "the TV is waking up; playback starts within about a minute"}

    async def _play_on_tv(self, path, body, label):
        try:
            await self.ha.post(path, body, timeout=90)
            _LOGGER.info("TV playback started: %s", label)
        except Exception as err:
            _LOGGER.warning("TV playback failed for %s: %r", label, err)
            if self.on_background_error:
                await self.on_background_error(f"Nem sikerült elindítani a tévén: {label}.")

    # ---------------------------------------------------------------- dispatch
    async def run(self, name, args):
        """Run a client tool; returns (json_text, is_error)."""
        handler = getattr(self, name, None) if name in TOOL_NAMES else None
        if handler is None:
            return json.dumps({"error": f"unknown tool {name}"}), True
        try:
            result = await handler(**(args or {}))
            return json.dumps(result, ensure_ascii=False, separators=(",", ":")), False
        except ToolError as err:
            return json.dumps({"error": str(err)}, ensure_ascii=False), True
        except TypeError as err:
            return json.dumps({"error": f"bad arguments: {err}"}), True
        except Exception as err:
            _LOGGER.exception("tool %s failed", name)
            return json.dumps({"error": f"{type(err).__name__}: {err}"[:300]}), True


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


PLAYER = {"type": "string", "description": "player entity_id or name; omit for the playing player, else the default"}
URIS = {"type": "array", "items": {"type": "string"}, "description": "Music Assistant uris, e.g. library://track/12 or tidal--x://track/123"}

TOOL_DEFS = [
    {"name": "search_music", "description": "Search the music library and Tidal. Returns uris to play or add.",
     "input_schema": _schema({
         "query": {"type": "string"},
         "media_types": {"type": "array", "items": {"type": "string", "enum": MEDIA_TYPES}},
         "limit": {"type": "integer", "description": "per type, default 5, max 15"},
         "library_only": {"type": "boolean"}}, ["query"])},
    {"name": "get_playlist_tracks", "description": "List the tracks of a playlist (name, library id or uri).",
     "input_schema": _schema({"playlist": {"type": "string"}, "limit": {"type": "integer"}}, ["playlist"])},
    {"name": "get_now_playing", "description": "What is playing now, per player.",
     "input_schema": _schema({"player": PLAYER})},
    {"name": "play_music", "description": "Play uris (tracks, albums, artists, playlists) on a player. enqueue: replace (default, start now), next, add. radio_mode keeps playing similar music after the items.",
     "input_schema": _schema({"uris": URIS, "player": PLAYER,
                              "enqueue": {"type": "string", "enum": ["replace", "next", "add"]},
                              "radio_mode": {"type": "boolean"}, "shuffle": {"type": "boolean"}}, ["uris"])},
    {"name": "create_playlist", "description": "Create a new, empty own playlist on Tidal. Returns its id; then use add_to_playlist.",
     "input_schema": _schema({"name": {"type": "string"}}, ["name"])},
    {"name": "add_to_playlist", "description": "Add tracks to one of the user's own (editable) playlists, by name or id.",
     "input_schema": _schema({"playlist": {"type": "string"}, "uris": URIS}, ["playlist", "uris"])},
    {"name": "like", "description": "Add an item to favourites. uri omitted or 'current' = the track playing now.",
     "input_schema": _schema({"uri": {"type": "string"}, "player": PLAYER})},
    {"name": "search_movies", "description": "Find films and series in the Jellyfin library by any title (English, Hungarian or original).",
     "input_schema": _schema({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"])},
    {"name": "play_movie", "description": "Play a film or series on the living-room TV (catalogue ref like m12, or Jellyfin id). Series resume at the next episode; films resume where left off unless from_start.",
     "input_schema": _schema({"item": {"type": "string"}, "from_start": {"type": "boolean"}}, ["item"])},
    {"name": "report_status", "description": "Say a very short Hungarian progress line aloud while you work (e.g. 'Keresem a számokat.'). Rate limited; may be skipped.",
     "input_schema": _schema({"text": {"type": "string"}}, ["text"])},
]
TOOL_NAMES = {t["name"] for t in TOOL_DEFS} - {"report_status"}

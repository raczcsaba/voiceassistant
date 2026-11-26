"""The tools Claude can call, plus the player and playlist lookups /quick shares with them.

Every write goes through _write() (Music Assistant) or _ha_write() (Home Assistant), which in dry-run mode only
log the exact command. Home Assistant writes are limited to the allowlist in config.json (see home.py).
Results are compact JSON with trimmed fields.
"""
import asyncio
import json
import logging

from rapidfuzz import fuzz

from . import catalogue as cat
from . import home
from . import seerr as seerr_mod
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
        self.readable, self.actions = home.load(cfg)
        self.home_cfg = cfg.get("home_control") or {}
        self.writes = []  # (kind, target, args) of every write, real or dry-run
        self.background = set()
        self.on_background_error = None  # async callback(text) for failures after the tool returned
        self.seerr = None  # seerr.Seerr, when configured
        self.pending = None  # seerr.Pending
        self.tracker = None  # seerr.Tracker
        self.task_ctx = {}  # per task: satellite, ask (a yes/no question was set up)

    # ---------------------------------------------------------------- writes
    async def _write(self, command, **args):
        self.writes.append(("ma", command, args))
        if self.dry_run:
            _LOGGER.info("[dry-run] would send MA command %s %s", command, json.dumps(args, ensure_ascii=False))
            return None
        _LOGGER.info("MA command %s %s", command, json.dumps(args, ensure_ascii=False))
        return await self.ma.call(command, **args)

    async def _write_many(self, command, arg_list):
        """The same MA command many times (e.g. deleting queue items one by one); logged as one write."""
        self.writes.append(("ma", command, {"count": len(arg_list), "first": arg_list[0] if arg_list else None}))
        if self.dry_run:
            _LOGGER.info("[dry-run] would send MA command %s x%d, first %s", command, len(arg_list),
                         json.dumps(arg_list[:1], ensure_ascii=False))
            return
        _LOGGER.info("MA command %s x%d", command, len(arg_list))
        for args in arg_list:
            await self.ma.call(command, **args)

    async def _ha_write(self, kind, target, data):
        """kind "service" (target = domain.service) or "post" (target = HA path)."""
        self.writes.append(("ha", target, data))
        text = json.dumps(data, ensure_ascii=False)
        if self.dry_run:
            _LOGGER.info("[dry-run] would call HA %s %s", target, text)
            return None
        _LOGGER.info("HA write %s %s", target, text)
        try:
            if kind == "service":
                domain, service = target.split(".", 1)
                return await self.ha.call_service(domain, service, data, timeout=20)
            return await self.ha.post(target, data, timeout=20)
        except Exception as err:
            raise ToolError(f"Home Assistant refused {target}: {str(err)[:200]}") from err

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

    async def play_music(self, uris, player=None, enqueue="replace", radio_mode=False, shuffle=False, volume=None):
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
        if volume is not None:
            # Before the music starts, so it doesn't blast at the old level first
            await self._set_volume(p, volume)
        await self._write("player_queues/play_media", queue_id=queue_id, media=uris, option=option,
                          radio_mode=bool(radio_mode))
        if shuffle:
            await self._write("player_queues/shuffle", queue_id=queue_id, shuffle_enabled=True)
        out = {"ok": True, "player": p["name"], "items": len(uris), "enqueue": option,
               "radio_mode": bool(radio_mode), "shuffle": bool(shuffle)}
        if volume is not None:
            out["volume_pct"] = int(volume)
        return out

    async def _set_volume(self, p, level):
        try:
            level = int(round(float(level)))
        except (TypeError, ValueError):
            raise ToolError("volume must be a number from 0 to 100") from None
        if not 0 <= level <= 100:
            raise ToolError("volume must be from 0 to 100 (percent)")
        await self._ha_write("service", "media_player.volume_set", {"entity_id": p["entity_id"], "volume_level": level / 100})
        return level

    async def set_volume(self, level, player=None):
        p = await self.players.resolve(player)
        level = await self._set_volume(p, level)
        return {"ok": True, "player": p["name"], "volume_pct": level}

    # ---------------------------------------------------------------- queue editing
    async def _queue_state(self, player=None, limit=500):
        """(player, queue dict, [items from the current one on, each with its absolute index])."""
        p = await self.players.resolve(player)
        queue = await self.ma.call("player_queues/get_active_queue", player_id=p["queue"] or p["entity_id"]) or {}
        queue_id = queue.get("queue_id") or p["queue"] or p["entity_id"]
        queue["queue_id"] = queue_id
        start = queue.get("current_index") or 0
        raw = await self.ma.call("player_queues/items", queue_id=queue_id, limit=limit, offset=start) or []
        items = []
        for n, it in enumerate(raw):
            media = it.get("media_item") or {}
            artists = ", ".join(a.get("name") for a in media.get("artists") or [] if a.get("name"))
            items.append({"index": start + n, "id": it.get("queue_item_id"),
                          "title": media.get("name") or it.get("name"), "artist": artists})
        return p, queue, items

    @staticmethod
    def _locked_until(queue):
        """Items up to this index can't be moved or removed (playing or already buffered by the player)."""
        cur = queue.get("current_index")
        buf = queue.get("index_in_buffer")
        return max(x for x in (cur, buf, -1) if x is not None)

    async def get_queue(self, player=None, limit=10):
        limit = max(1, min(int(limit or 10), 50))
        p, queue, items = await self._queue_state(player, limit + 1)
        cur = queue.get("current_index")
        locked = self._locked_until(queue)
        current = items[0] if items and cur is not None and items[0]["index"] == cur else None
        upcoming = items[1:] if current else items
        out = {"player": p["name"], "state": p["state"], "shuffle": queue.get("shuffle_enabled"),
               "repeat": queue.get("repeat_mode"),
               "current": {k: current[k] for k in ("title", "artist", "id")} if current else None,
               "upcoming": [{"pos": n + 1, **u, **({"locked": True} if u["index"] <= locked else {})}
                            for n, u in enumerate(upcoming[:limit])],
               "upcoming_total": max(0, int(queue.get("items") or 0) - (cur + 1 if cur is not None else 0))}
        for u in out["upcoming"]:
            u.pop("index", None)
        return out

    @staticmethod
    def _matches(item, text):
        wanted = norm(text)
        if not wanted:
            return False
        hay = norm(f"{item.get('artist') or ''} {item.get('title') or ''}")
        return wanted in hay or fuzz.partial_ratio(wanted, norm(item.get("artist") or "")) >= 90

    async def edit_queue(self, ops, player=None):
        if isinstance(ops, dict):
            ops = [ops]
        if not ops:
            raise ToolError("no ops given")
        done, problems = [], []
        p = None
        for op in ops:
            kind = (op or {}).get("op")
            p, queue, items = await self._queue_state(player)
            qid = queue["queue_id"]
            locked = self._locked_until(queue)
            editable = [i for i in items if i["index"] > locked]
            by_id = {i["id"]: i for i in items}
            if kind == "remove":
                targets = []
                for qi in op.get("ids") or ([op["id"]] if op.get("id") else []):
                    if qi in by_id and by_id[qi]["index"] > locked:
                        targets.append(by_id[qi])
                    else:
                        problems.append(f"remove: {qi} is not an upcoming, editable item")
                if op.get("match"):
                    hits = [i for i in editable if self._matches(i, op["match"])]
                    if not hits:
                        problems.append(f"remove: nothing upcoming matches {op['match']!r}")
                    targets += [h for h in hits if h not in targets]
                if op.get("count"):
                    if items[1:2] and items[1]["index"] <= locked:
                        problems.append("the very next track is already buffered by the player and can't be removed")
                    targets += [i for i in editable[: int(op["count"])] if i not in targets]
                # Highest index first, so the remaining indexes stay valid
                for t in sorted(targets, key=lambda i: -i["index"]):
                    await self._write("player_queues/delete_item", queue_id=qid, item_id_or_index=t["id"])
                if targets:
                    done.append(f"removed {len(targets)}: " + "; ".join(f"{t['artist']} - {t['title']}" for t in targets[:8]))
            elif kind in ("move_next", "move"):
                item = by_id.get(op.get("id")) if op.get("id") else None
                if item is None and op.get("match"):
                    item = next((i for i in editable if self._matches(i, op["match"])), None)
                if item is None or item["index"] <= locked:
                    problems.append(f"{kind}: item not found among the upcoming items")
                    continue
                if kind == "move_next":
                    target = locked + 1
                else:
                    pos = max(1, int(op.get("position") or 1))
                    target = max(locked + 1, (queue.get("current_index") or 0) + pos)
                shift = target - item["index"]
                if shift:
                    await self._write("player_queues/move_item", queue_id=qid, queue_item_id=item["id"], pos_shift=shift)
                done.append(f"moved {item['title']} to upcoming position {target - (queue.get('current_index') or 0)}")
            elif kind == "clear_upcoming":
                total = int(queue.get("items") or 0)
                start = locked + 1
                # MA has no "clear after current"; delete by index from the end
                indexes = list(range(total - 1, start - 1, -1))
                await self._write_many("player_queues/delete_item",
                                       [{"queue_id": qid, "item_id_or_index": i} for i in indexes])
                done.append(f"cleared {len(indexes)} upcoming items")
            elif kind == "shuffle":
                await self._write("player_queues/shuffle", queue_id=qid, shuffle_enabled=bool(op.get("value", True)))
                done.append(f"shuffle {'on' if op.get('value', True) else 'off'}")
            elif kind == "repeat":
                mode = str(op.get("value") or "all").lower()
                if mode not in ("off", "one", "all"):
                    problems.append("repeat: value must be off, one or all")
                    continue
                await self._write("player_queues/repeat", queue_id=qid, repeat_mode=mode)
                done.append(f"repeat {mode}")
            elif kind == "play":
                item = by_id.get(op.get("id")) if op.get("id") else None
                if item is None and op.get("match"):
                    item = next((i for i in items[1:] if self._matches(i, op["match"])), None)
                if item is None:
                    problems.append("play: item not found in the queue")
                    continue
                await self._write("player_queues/play_index", queue_id=qid, index=item["id"])
                done.append(f"playing {item['title']}")
            elif kind in ("next", "previous"):
                await self._write(f"player_queues/{kind}", queue_id=qid)
                done.append(kind)
            else:
                problems.append(f"unknown op {kind!r}")
        if not done and problems:
            raise ToolError("; ".join(problems))
        out = {"ok": True, "player": p["name"] if p else None, "done": done}
        if problems:
            out["problems"] = problems
        return out

    # ---------------------------------------------------------------- home control (allowlist)
    def _readable_ids(self):
        return {e for ids in self.readable.values() for e in ids}

    async def ha_get_states(self, group=None, entity_ids=None):
        if not self.readable:
            raise ToolError("home control is not configured")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        wanted = set()
        if group:
            if group not in self.readable:
                raise ToolError(f"unknown group {group!r}; groups: {', '.join(self.readable)}")
            wanted |= set(self.readable[group])
        if entity_ids:
            allowed = self._readable_ids()
            refused = [e for e in entity_ids if e not in allowed]
            if refused:
                raise ToolError(f"not readable: {', '.join(refused)}; use a group or a listed entity")
            wanted |= set(entity_ids)
        if not wanted:
            wanted = self._readable_ids()
        states = await self.ha.states()
        out = [home.compact_state(st) for st in states if st.get("entity_id") in wanted]
        result = {"states": sorted(out, key=lambda x: x["id"])}
        for name, ep in (self.home_cfg.get("read_endpoints") or {}).items():
            if (group or None) in (None, ep.get("group")) and not entity_ids:
                try:
                    result[name] = await self.ha.get(ep["path"])
                except Exception as err:
                    result[name] = {"error": str(err)[:120]}
        return result

    async def get_weather_forecast(self, kind="daily", limit=None):
        entity = self.home_cfg.get("weather_entity")
        if not entity:
            raise ToolError("no weather entity configured")
        kind = kind if kind in ("daily", "hourly") else "daily"
        resp = await self.ha.service_response("weather", "get_forecasts", {"entity_id": entity, "type": kind})
        items = ((resp or {}).get(entity) or {}).get("forecast") or []
        limit = max(1, min(int(limit or (5 if kind == "daily" else 12)), 10 if kind == "daily" else 48))
        keep = ("datetime", "condition", "temperature", "templow", "precipitation", "precipitation_probability",
                "wind_speed", "humidity")
        return {"entity": entity, "type": kind,
                "forecast": [{k: f[k] for k in keep if f.get(k) is not None} for f in items[:limit]]}

    async def ha_action(self, action_id, params=None):
        spec = self.actions.get(action_id)
        if spec is None:
            raise ToolError(f"unknown action {action_id!r}; allowed: {', '.join(self.actions)}")
        try:
            kind, target, data = home.build_call(spec, params)
        except ValueError as err:
            raise ToolError(str(err)) from None
        await self._ha_write(kind, target, data)
        # The same answer in dry-run mode, so a test run sees what a real one would (the write log tells them apart)
        out = {"ok": True, "action": action_id}
        if spec.get("note"):
            out["note"] = spec["note"]
        return out

    def tool_defs(self):
        """The tool list for this deployment: the static tools plus home control when configured."""
        defs = list(TOOL_DEFS)
        if self.readable:
            defs.append({"name": "ha_get_states",
                         "description": "Read the current state of home devices and sensors (lights, TV, tablet, phone, "
                                        "speakers, weather, sun, presence). Groups: " + ", ".join(
                                            f"{g} ({len(ids)})" for g, ids in self.readable.items())
                                        + ". Omit both arguments for everything.",
                         "input_schema": _schema({"group": {"type": "string", "enum": list(self.readable)},
                                                  "entity_ids": {"type": "array", "items": {"type": "string"}}})})
        if self.home_cfg.get("weather_entity"):
            defs.append({"name": "get_weather_forecast",
                         "description": "Weather forecast for home: daily (default, today first) or hourly.",
                         "input_schema": _schema({"kind": {"type": "string", "enum": ["daily", "hourly"]},
                                                  "limit": {"type": "integer"}})})
        if self.actions:
            defs.append({"name": "ha_action",
                         "description": "Run one allowlisted home action (the only way to control the home). "
                                        "Pass params as an object. Actions:\n" + home.describe(self.actions),
                         "input_schema": _schema({"action_id": {"type": "string", "enum": list(self.actions)},
                                                  "params": {"type": "object"}}, ["action_id"])})
        if self.seerr is not None:
            defs += SEERR_DEFS
        # report_status stays last
        defs.sort(key=lambda d: d["name"] == "report_status")
        return defs

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

    # ---------------------------------------------------------------- Seerr: find and download films and series
    def _need_seerr(self):
        if self.seerr is None:
            raise ToolError("downloading is not configured")

    async def seerr_search(self, query, media_type=None):
        self._need_seerr()
        found = await self.seerr.search(query, limit=8)
        if media_type in ("movie", "tv"):
            found = [f for f in found if f["type"] == media_type]
        return {"results": found[:5]} if found else {"results": [], "note": "nothing found in Seerr/TMDB"}

    async def _checked(self, tmdb_id, media_type):
        self._need_seerr()
        if media_type not in ("movie", "tv"):
            raise ToolError("media_type must be movie or tv")
        try:
            details = await self.seerr.details(media_type, int(tmdb_id))
        except (TypeError, ValueError):
            raise ToolError("tmdb_id must be a number") from None
        info = seerr_mod.compact({**details, "mediaType": media_type})
        return details, info

    async def propose_download(self, tmdb_id, media_type, seasons=None):
        details, info = await self._checked(tmdb_id, media_type)
        if info["status"] in ("available", "partially_available"):
            return {"ok": False, "status": info["status"], "title": info["title"],
                    "note": "already downloaded: check search_movies and offer to play it instead"}
        if info["status"] in ("pending", "processing") or info.get("requested"):
            return {"ok": False, "status": info["status"], "title": info["title"],
                    "note": "already requested and on its way; just say so"}
        if media_type == "tv":
            seasons = [int(s) for s in seasons] if seasons else seerr_mod.default_seasons(details)
        else:
            seasons = None
        satellite = self.task_ctx.get("satellite")
        self.pending.set(kind="seerr", tmdb_id=int(tmdb_id), type=media_type, title=info["title"], year=info["year"],
                         seasons=seasons, satellite=satellite)
        self.task_ctx["ask"] = True
        out = {"ok": True, "title": info["title"], "year": info["year"], "expires_in_s": self.pending.ttl,
               "note": "end your reply with the question (e.g. 'Letöltsem?'); the satellite then listens for the answer"}
        if seasons:
            out["seasons"] = seasons
        return out

    async def request_download(self, tmdb_id, media_type, seasons=None):
        return await self.do_request(tmdb_id, media_type, seasons, self.task_ctx.get("satellite"))

    async def do_request(self, tmdb_id, media_type, seasons, satellite):
        """Request in Seerr (or log it in dry-run) and track it until it is downloaded."""
        details, info = await self._checked(tmdb_id, media_type)
        if self.pending:
            self.pending.clear()
        if info["status"] in ("available", "partially_available", "pending", "processing"):
            return {"ok": False, "status": info["status"], "title": info["title"],
                    "note": "nothing requested: it is already available or on its way"}
        if media_type == "tv":
            seasons = [int(s) for s in seasons] if seasons else seerr_mod.default_seasons(details)
        else:
            seasons = None
        result = await self.seerr.request(media_type, int(tmdb_id), seasons)
        self.writes.append(("seerr", "/request", self.seerr.posts[-1]))
        if self.tracker and not self.seerr.dry_run:
            self.tracker.add(int(tmdb_id), media_type, info["title"], satellite, seasons, (result or {}).get("id"))
        out = {"ok": True, "title": info["title"], "year": info["year"],
               "request_status": seerr_mod.REQUEST_STATUS.get((result or {}).get("status"), "sent")}
        if seasons:
            out["seasons"] = seasons
        return out

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
                              "radio_mode": {"type": "boolean"}, "shuffle": {"type": "boolean"},
                              "volume": {"type": "integer", "description": "optional volume in percent (0-100), set before playing; \"negyvenes hangerő\" = 40"}},
                             ["uris"])},
    {"name": "get_queue", "description": "The playing queue of a player: the current track and the upcoming ones "
                                       "(pos 1 = next) with their queue item id. locked items are already buffered and can't be edited.",
     "input_schema": _schema({"player": PLAYER, "limit": {"type": "integer", "description": "upcoming items, default 10, max 50"}})},
    {"name": "edit_queue", "description": "Edit the queue that is already playing, without replacing it. ops run in order; "
                                        "each is an object with op and its fields:\n"
                                        "- remove: ids (queue item ids) and/or match (artist or title text, removes every upcoming match) "
                                        "and/or count (the next N upcoming items)\n"
                                        "- move_next: id or match -> plays right after the current track\n"
                                        "- move: id or match, position (1 = next)\n"
                                        "- clear_upcoming: removes everything after the current track (which keeps playing)\n"
                                        "- shuffle: value true/false; repeat: value off/one/all\n"
                                        "- play: id or match -> jump to that item now; next; previous",
     "input_schema": _schema({"ops": {"type": "array", "items": {"type": "object", "properties": {
         "op": {"type": "string", "enum": ["remove", "move_next", "move", "clear_upcoming", "shuffle", "repeat", "play",
                                           "next", "previous"]},
         "id": {"type": "string"}, "ids": {"type": "array", "items": {"type": "string"}}, "match": {"type": "string"},
         "count": {"type": "integer"}, "position": {"type": "integer"},
         "value": {"type": ["boolean", "string"]}}, "required": ["op"]}}, "player": PLAYER}, ["ops"])},
    {"name": "set_volume", "description": "Set a music player's volume in percent (0-100).",
     "input_schema": _schema({"level": {"type": "integer"}, "player": PLAYER}, ["level"])},
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
SEERR_DEFS = [
    {"name": "seerr_search", "description": "Search films and series that can be downloaded (Seerr/TMDB, Hungarian titles). "
                                          "status: available (downloaded), processing/pending (on its way), not_requested.",
     "input_schema": _schema({"query": {"type": "string"}, "media_type": {"type": "string", "enum": ["movie", "tv"]}},
                             ["query"])},
    {"name": "propose_download", "description": "Offer ONE title for download and wait for the user's yes/no. Your final "
                                              "reply must then be one short sentence ending with a question like "
                                              "'Letöltsem?'; it is spoken and the satellite listens for the answer.",
     "input_schema": _schema({"tmdb_id": {"type": "integer"}, "media_type": {"type": "string", "enum": ["movie", "tv"]},
                              "seasons": {"type": "array", "items": {"type": "integer"},
                                          "description": "series only; default all seasons, or season 1 if it has more than 3"}},
                             ["tmdb_id", "media_type"])},
    {"name": "request_download", "description": "Request the download now (only when the user explicitly said to download "
                                              "this title, or approved your proposal).",
     "input_schema": _schema({"tmdb_id": {"type": "integer"}, "media_type": {"type": "string", "enum": ["movie", "tv"]},
                              "seasons": {"type": "array", "items": {"type": "integer"}}}, ["tmdb_id", "media_type"])},
]
HOME_TOOLS = {"ha_get_states", "get_weather_forecast", "ha_action"}
TOOL_NAMES = ({t["name"] for t in TOOL_DEFS + SEERR_DEFS} | HOME_TOOLS) - {"report_status"}

"""Seerr (Jellyseerr/Overseerr): search, request downloads, the pending yes/no proposal, and the "it's ready" poller.

Flow: Claude proposes ONE title (propose_download); the question is spoken with assist_satellite.start_conversation so
the satellite listens for the answer. The answer arrives as the next /task; answer_kind() decides yes/no
deterministically where it can. Approved requests are tracked in data/requests.json; the Tracker polls Seerr and
announces on the asking satellite when the title is available (never between quiet_start and quiet_end).
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp
from yarl import URL

from .textutil import norm

_LOGGER = logging.getLogger(__name__)

# Seerr MediaStatus
MEDIA_STATUS = {1: "unknown", 2: "pending", 3: "processing", 4: "partially_available", 5: "available",
                6: "blocklisted", 7: "deleted"}
# Seerr MediaRequestStatus
REQUEST_STATUS = {1: "pending_approval", 2: "approved", 3: "declined", 4: "failed", 5: "completed"}
MAX_SEASONS_ALL = 3  # series with at most this many seasons are requested whole; longer ones start with season 1


class SeerrError(Exception):
    pass


class Seerr:
    def __init__(self, url, key, session, user_id=None, dry_run=False, timeout=15):
        self.url = url.rstrip("/")
        self.key = key
        self.session = session
        self.user_id = user_id
        self.dry_run = dry_run
        self.timeout = timeout
        self.posts = []  # every request body, real or dry-run

    async def _request(self, method, path, params=None, body=None):
        url = f"{self.url}/api/v1{path}"
        if params:
            # Seerr rejects anything but strict percent-encoding (encodeURIComponent), e.g. '+' for spaces
            url += "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        async with self.session.request(method, URL(url, encoded=True), json=body,
                                        headers={"X-Api-Key": self.key},
                                        timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
            data = await resp.json(content_type=None) if resp.content_length != 0 else None
            if resp.status >= 400:
                raise SeerrError(f"Seerr {method} {path} -> {resp.status}: {str(data)[:200]}")
            return data

    async def search(self, query, limit=5):
        data = await self._request("GET", "/search", {"query": query, "page": 1, "language": "hu"})
        out = []
        for r in (data or {}).get("results") or []:
            if r.get("mediaType") not in ("movie", "tv"):
                continue
            out.append(compact(r))
            if len(out) >= limit:
                break
        return out

    async def details(self, media_type, tmdb_id):
        if media_type not in ("movie", "tv"):
            raise SeerrError("media_type must be movie or tv")
        return await self._request("GET", f"/{media_type}/{int(tmdb_id)}", {"language": "hu"})

    async def request(self, media_type, tmdb_id, seasons=None):
        body = {"mediaType": media_type, "mediaId": int(tmdb_id)}
        if media_type == "tv":
            body["seasons"] = seasons or "all"
        if self.user_id:
            body["userId"] = int(self.user_id)
        self.posts.append(body)
        if self.dry_run:
            _LOGGER.info("[dry-run] would POST Seerr /request %s", json.dumps(body))
            return {"id": None, "dry_run": True, "status": 2}
        _LOGGER.info("Seerr POST /request %s", json.dumps(body))
        return await self._request("POST", "/request", body=body)


def compact(r):
    """A Seerr search result or detail object reduced to what Claude needs."""
    info = r.get("mediaInfo") or {}
    date = r.get("releaseDate") or r.get("firstAirDate") or ""
    out = {"tmdb_id": r.get("id"), "type": r.get("mediaType") or ("tv" if r.get("firstAirDate") else "movie"),
           "title": r.get("title") or r.get("name"),
           "original": r.get("originalTitle") or r.get("originalName"),
           "year": int(date[:4]) if date[:4].isdigit() else None,
           "status": MEDIA_STATUS.get(info.get("status"), "not_requested")}
    if out["original"] == out["title"]:
        out.pop("original")
    if info.get("requests"):
        out["requested"] = True
    return out


def default_seasons(details):
    """All seasons for a short series, season 1 for one with more than MAX_SEASONS_ALL seasons."""
    numbers = sorted(s["seasonNumber"] for s in details.get("seasons") or [] if s.get("seasonNumber", 0) > 0)
    if not numbers:
        return [1]
    return numbers if len(numbers) <= MAX_SEASONS_ALL else numbers[:1]


# ---------------------------------------------------------------- the pending yes/no question
YES = {"igen", "ja", "jaja", "aha", "mehet", "jo", "oke", "okes", "ok", "okay", "kerem", "kerlek", "persze", "rendben",
       "nana", "legyen", "toltsd", "toltsed", "csinald", "hajra", "igenis", "szuper", "johet", "yes"}
NO = {"nem", "ne", "nee", "nemkoszi", "megse", "hagyd", "hagyjuk", "no", "nope"}
ANOTHER = {"mast", "masikat", "masik", "inkabb", "valami", "mas"}
UNSURE = {"nem tudom", "talan", "lehet", "majd", "kesobb", "majd kesobb", "mindegy", "nem tudom meg"}


def answer_kind(text):
    """'yes', 'no', 'another' (reject and propose a different one) or None (unclear: let Claude decide)."""
    words = norm(text).split()
    if not words or " ".join(words) in UNSURE or " ".join(words[:2]) == "nem tudom":
        return None
    if any(w in ANOTHER for w in words) and (words[0] in NO or "inkabb" in words or words[0] in ANOTHER
                                             or "mast" in words or "masikat" in words):
        return "another"
    if words[0] in NO or (len(words) <= 3 and any(w in NO for w in words)):
        return "no"
    if len(words) <= 4 and (words[0] in YES or "toltsd le" in " ".join(words) or "mehet" in words):
        return "yes"
    return None


class Pending:
    """At most one open proposal; ignored once expired."""

    def __init__(self, ttl=180, clock=time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self.item = None
        self.proposed = []  # titles already offered in this round, so "mást" gets something new

    def set(self, **item):
        item["expires"] = self.clock() + self.ttl
        self.item = item
        if item.get("title") and item["title"] not in self.proposed:
            self.proposed.append(item["title"])

    def get(self):
        if self.item and self.clock() >= self.item["expires"]:
            self.item = None
        return self.item

    def pop(self):
        item = self.get()
        self.item = None
        return item

    def clear(self, forget=True):
        self.item = None
        if forget:
            self.proposed = []

    def status(self):
        item = self.get()
        if not item:
            return {"pending": False, "kind": None, "title": None, "satellite": None, "expires_in": 0}
        return {"pending": True, "kind": "seerr", "title": item.get("title"), "satellite": item.get("satellite"),
                "expires_in": max(0, round(item["expires"] - self.clock()))}


# ---------------------------------------------------------------- tracking until downloaded
class Tracker:
    """Requested titles in data/requests.json; poll() announces the ones that became available."""

    def __init__(self, path, seerr, notify, tz="Europe/Budapest", quiet=(22, 8), now=None, max_days=30):
        self.path = path
        self.seerr = seerr
        self.notify = notify  # async (item, text) -> None: speak and push the phone notification
        self.tz = ZoneInfo(tz)
        self.quiet = quiet
        self.now = now or (lambda: datetime.now(self.tz))
        self.max_days = max_days
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, tmdb_id, media_type, title, satellite, seasons=None, request_id=None):
        self.items = [i for i in self.items if not (i["tmdb_id"] == tmdb_id and i["type"] == media_type)]
        self.items.append({"tmdb_id": tmdb_id, "type": media_type, "title": title, "satellite": satellite,
                           "seasons": seasons, "request_id": request_id, "requested_at": self.now().isoformat(),
                           "ready_at": None, "notified": False})
        self.save()

    def quiet_now(self, when=None):
        hour = (when or self.now()).hour
        start, end = self.quiet
        return hour >= start or hour < end

    @staticmethod
    def ready(details, seasons):
        info = details.get("mediaInfo") or {}
        if info.get("status") == 5:
            return True
        if seasons and info.get("seasons"):
            done = {s.get("seasonNumber") for s in info["seasons"] if s.get("status") == 5}
            return set(seasons) <= done
        return False

    async def poll(self):
        """One pass. Returns the titles announced."""
        announced, changed = [], False
        now = self.now()
        for item in list(self.items):
            if item["notified"]:
                continue
            try:
                requested = datetime.fromisoformat(item["requested_at"])
            except ValueError:
                requested = now
            if now - requested > timedelta(days=self.max_days):
                _LOGGER.info("giving up on %s after %d days", item["title"], self.max_days)
                self.items.remove(item)
                changed = True
                continue
            if not item.get("ready_at"):
                try:
                    details = await self.seerr.details(item["type"], item["tmdb_id"])
                except Exception as err:
                    _LOGGER.warning("Seerr status for %s failed: %r", item["title"], err)
                    continue
                if not self.ready(details, item.get("seasons")):
                    continue
                item["ready_at"] = now.isoformat()
                changed = True
            if self.quiet_now(now):
                continue  # announced on the first poll after quiet hours (08:00)
            await self.notify(item, f"Letöltődött a(z) {item['title']}, indíthatom a tévén?")
            item["notified"] = True
            changed = True
            announced.append(item["title"])
        # keep finished items for a day so a repeated request is recognised, then drop them
        before = len(self.items)
        self.items = [i for i in self.items if not (i["notified"] and i.get("ready_at") and
                                                     now - datetime.fromisoformat(i["ready_at"]) > timedelta(days=1))]
        if changed or len(self.items) != before:
            self.save()
        return announced

    async def run(self, every_s=300):
        while True:
            try:
                await self.poll()
            except Exception as err:
                _LOGGER.warning("Seerr poll failed: %r", err)
            await asyncio.sleep(every_s)

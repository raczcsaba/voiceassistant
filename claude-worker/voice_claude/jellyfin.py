"""Jellyfin client: the user's films and series, Hungarian titles, next-up episodes."""
import asyncio
import json
import logging
import os

import aiohttp

_LOGGER = logging.getLogger(__name__)
SEARCH_PATHS = {"Movie": "/Items/RemoteSearch/Movie", "Series": "/Items/RemoteSearch/Series"}


class Jellyfin:
    def __init__(self, url, key, user, session, titles_path=None):
        self.url = url.rstrip("/")
        self.key = key
        self.user = user
        self.session = session
        self.titles_path = titles_path
        self._user_id = None

    async def _req(self, method, path, params=None, json_body=None, timeout=20):
        async with self.session.request(method, self.url + path, params=params, json=json_body,
                                        headers={"X-Emby-Token": self.key},
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"Jellyfin {path} -> {resp.status}")
            if resp.content_type == "application/json":
                return await resp.json()
            return await resp.read()

    async def user_id(self):
        if self._user_id is None:
            users = await self._req("GET", "/Users")
            match = [u for u in users if not self.user or u["Name"] == self.user]
            if not match:
                raise RuntimeError(f"Jellyfin user {self.user!r} not found")
            self._user_id = match[0]["Id"]
        return self._user_id

    async def items(self, search=None, limit=None):
        uid = await self.user_id()
        params = {"IncludeItemTypes": "Movie,Series", "Recursive": "true",
                  "Fields": "ProviderIds,ProductionYear,OriginalTitle,UserData", "SortBy": "SortName"}
        if search:
            params["SearchTerm"] = search
        if limit:
            params["Limit"] = str(limit)
        data = await self._req("GET", f"/Users/{uid}/Items", params)
        return data.get("Items", [])

    async def item(self, item_id):
        uid = await self.user_id()
        return await self._req("GET", f"/Users/{uid}/Items/{item_id}")

    async def next_episode(self, series_id):
        """The half-watched or next episode of a series (first episode if never started)."""
        uid = await self.user_id()
        data = await self._req("GET", "/Shows/NextUp", {"SeriesId": series_id, "UserId": uid, "Limit": "1",
                                                        "Fields": "UserData"})
        items = data.get("Items") or []
        if not items:
            data = await self._req("GET", f"/Shows/{series_id}/Episodes", {"UserId": uid, "Limit": "1",
                                                                           "Fields": "UserData"})
            items = data.get("Items") or []
        return items[0] if items else None

    # Hungarian titles, looked up once per item with Jellyfin's remote search and cached on disk
    def load_titles(self):
        if self.titles_path and os.path.exists(self.titles_path):
            with open(self.titles_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_titles(self, titles):
        if self.titles_path:
            tmp = self.titles_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(titles, f, ensure_ascii=False, indent=0, sort_keys=True)
            os.replace(tmp, self.titles_path)

    async def _hungarian_title(self, item):
        ids = item.get("ProviderIds") or {}
        info = {"Name": item["Name"], "Year": item.get("ProductionYear"), "MetadataLanguage": "hu",
                "MetadataCountryCode": "HU", "ProviderIds": ids}
        found = await self._req("POST", SEARCH_PATHS[item["Type"]], json_body={"SearchInfo": info}, timeout=30)
        for result in found or []:
            theirs = result.get("ProviderIds") or {}
            if any(ids.get(k) and ids.get(k) == theirs.get(k) for k in ("Tmdb", "Imdb", "Tvdb")):
                return result["Name"]
        return None

    async def hungarian_titles(self, items):
        titles = self.load_titles()
        missing = [i for i in items if i["Name"] not in titles and i.get("Type") in SEARCH_PATHS]
        sem = asyncio.Semaphore(4)

        async def one(item):
            async with sem:
                try:
                    titles[item["Name"]] = await self._hungarian_title(item)
                except Exception as err:  # retried on the next refresh
                    _LOGGER.debug("no Hungarian title for %s: %r", item["Name"], err)

        if missing:
            await asyncio.gather(*(one(i) for i in missing))
            self._save_titles(titles)
        return titles

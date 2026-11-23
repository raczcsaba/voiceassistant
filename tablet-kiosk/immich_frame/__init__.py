"""Immich photo frame backend for the kiosk screensaver card.

The card never sees the Immich API key: it asks Home Assistant (authenticated) for random
photos, fetches them through this proxy and tags them "Keep" or "Remove". Tagging decides
what a later clean-up may archive or delete; untagged photos are never touched.

Reads immich_frame_url / immich_frame_key from secrets.yaml at request time, so a key
change needs no restart.
"""
import asyncio
import logging
import re
import time

import yaml
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "immich_frame"
TAGS = {"keep": "Keep", "remove": "Remove"}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TAGGED_TTL = 300  # seconds before the tagged-asset sets are re-read from Immich


def _read_secrets(path):
    try:
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data.get("immich_frame_url"), data.get("immich_frame_key")
    except OSError:
        return None, None


class Immich:
    """Small Immich client plus a cache of which assets carry our two tags."""

    def __init__(self, hass):
        self.hass = hass
        self.tag_ids = {}  # "keep"/"remove" -> Immich tag id
        self.tagged = {}  # asset id -> "keep"/"remove"
        self.tagged_at = 0
        self.lock = asyncio.Lock()

    async def call(self, method, path, json=None, raw=False):
        url, key = await self.hass.async_add_executor_job(_read_secrets, self.hass.config.path("secrets.yaml"))
        if not url or not key:
            raise web.HTTPServiceUnavailable(text="immich_frame secrets missing")
        session = async_get_clientsession(self.hass)
        async with session.request(method, url.rstrip("/") + "/api" + path, json=json,
                                   headers={"x-api-key": str(key), "Accept": "application/json"}, timeout=30) as resp:
            if resp.status >= 400:
                text = await resp.text()
                _LOGGER.warning("Immich %s %s -> %s %s", method, path, resp.status, text[:200])
                raise web.HTTPBadGateway(text=f"immich {resp.status}")
            if raw:
                return await resp.read(), resp.content_type
            return await resp.json() if resp.content_type == "application/json" else None

    async def ensure_tags(self):
        if len(self.tag_ids) == len(TAGS):
            return
        existing = {t["value"]: t["id"] for t in await self.call("GET", "/tags")}
        for slug, name in TAGS.items():
            if name not in existing:
                created = await self.call("POST", "/tags", json={"name": name})
                existing[name] = created["id"]
            self.tag_ids[slug] = existing[name]

    async def refresh_tagged(self, force=False):
        async with self.lock:
            if not force and time.monotonic() - self.tagged_at < TAGGED_TTL:
                return
            await self.ensure_tags()
            tagged = {}
            for slug, tag_id in self.tag_ids.items():
                page = 1
                while page:
                    res = await self.call("POST", "/search/metadata",
                                          json={"tagIds": [tag_id], "size": 1000, "page": page, "withDeleted": False})
                    for item in res["assets"]["items"]:
                        tagged[item["id"]] = slug
                    nxt = res["assets"].get("nextPage")
                    page = int(nxt) if nxt else 0
            self.tagged, self.tagged_at = tagged, time.monotonic()


def _photo(item, tag):
    exif = item.get("exifInfo") or {}
    place = ", ".join(p for p in (exif.get("city"), exif.get("country")) if p)
    return {
        "id": item["id"],
        "taken": item.get("localDateTime") or item.get("fileCreatedAt"),
        "place": place,
        "tag": tag,
        # Originals the WebView can decode are served in full resolution; HEIC and RAW fall back to the preview
        "original": item.get("originalMimeType") in ("image/jpeg", "image/png", "image/webp"),
        "w": exif.get("exifImageWidth"),
        "h": exif.get("exifImageHeight"),
    }


class NextView(HomeAssistantView):
    """GET ?count=N -> N random photos (images only) with their current tag."""

    url = "/api/immich_frame/next"
    name = "api:immich_frame:next"

    async def get(self, request):
        immich = request.app["hass"].data[DOMAIN]
        count = max(1, min(50, int(request.query.get("count", 12))))
        await immich.refresh_tagged()
        items = await immich.call("POST", "/search/random", json={"size": count, "type": "IMAGE", "withExif": True})
        return self.json([_photo(i, immich.tagged.get(i["id"])) for i in items if i.get("type") == "IMAGE"])


class ImageView(HomeAssistantView):
    """GET /image/<id>?size=preview|original -> the image, proxied with the server-side key."""

    url = "/api/immich_frame/image/{asset_id}"
    name = "api:immich_frame:image"

    async def get(self, request, asset_id):
        if not UUID.match(asset_id):
            raise web.HTTPBadRequest()
        immich = request.app["hass"].data[DOMAIN]
        path = f"/assets/{asset_id}/thumbnail?size=preview"
        if request.query.get("size") == "original":
            path = f"/assets/{asset_id}/original"
        try:
            body, ctype = await immich.call("GET", path, raw=True)
        except web.HTTPBadGateway:
            if path.endswith("preview"):
                raise
            body, ctype = await immich.call("GET", f"/assets/{asset_id}/thumbnail?size=preview", raw=True)
        return web.Response(body=body, content_type=ctype or "image/jpeg",
                            headers={"Cache-Control": "private, max-age=86400"})


class TagView(HomeAssistantView):
    """POST {id, tag: keep|remove} -> tags the photo, taking the other tag off."""

    url = "/api/immich_frame/tag"
    name = "api:immich_frame:tag"

    async def post(self, request):
        immich = request.app["hass"].data[DOMAIN]
        data = await request.json()
        asset_id, slug = str(data.get("id", "")), data.get("tag")
        if not UUID.match(asset_id) or slug not in TAGS:
            raise web.HTTPBadRequest()
        await immich.ensure_tags()
        await immich.call("PUT", f"/tags/{immich.tag_ids[slug]}/assets", json={"ids": [asset_id]})
        other = next(s for s in TAGS if s != slug)
        if immich.tagged.get(asset_id) == other:
            await immich.call("DELETE", f"/tags/{immich.tag_ids[other]}/assets", json={"ids": [asset_id]})
        immich.tagged[asset_id] = slug
        counts = {s: sum(1 for v in immich.tagged.values() if v == s) for s in TAGS}
        _LOGGER.info("Immich photo %s tagged %s", asset_id, TAGS[slug])
        return self.json({"id": asset_id, "tag": slug, "counts": counts})


class StatsView(HomeAssistantView):
    """GET -> how many photos carry each tag."""

    url = "/api/immich_frame/stats"
    name = "api:immich_frame:stats"

    async def get(self, request):
        immich = request.app["hass"].data[DOMAIN]
        await immich.refresh_tagged(force=request.query.get("force") == "1")
        return self.json({s: sum(1 for v in immich.tagged.values() if v == s) for s in TAGS})


async def async_setup(hass, config):
    hass.data[DOMAIN] = Immich(hass)
    for view in (NextView, ImageView, TagView, StatsView):
        hass.http.register_view(view)
    return True

"""Authenticated HTTP endpoints for the dashboard; they forward to the worker, so the browser never talks to it.

POST /api/voice_brain/like       {"player"?}            -> worker /quick like
GET  /api/voice_brain/playlists                         -> worker /quick list_playlists
POST /api/voice_brain/save       {"playlist", "player"?} -> worker /quick save_to_playlist

Always HTTP 200 with the worker's JSON; {"ok": false, "reason": "unreachable", "say": ...} when it can't be reached.
"""
from homeassistant.components.http import KEY_HASS, HomeAssistantView

from . import worker

UNREACHABLE = {"ok": False, "reason": "unreachable", "say": "Claude most nem elérhető."}


async def _body(request):
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


class LikeView(HomeAssistantView):
    url = "/api/voice_brain/like"
    name = "api:voice_brain:like"

    async def post(self, request):
        data = await _body(request)
        reply = await worker.quick(request.app[KEY_HASS], "like", _text(data.get("player")))
        return self.json(reply or UNREACHABLE)


class PlaylistsView(HomeAssistantView):
    url = "/api/voice_brain/playlists"
    name = "api:voice_brain:playlists"

    async def get(self, request):
        reply = await worker.quick(request.app[KEY_HASS], "list_playlists")
        return self.json(reply or {**UNREACHABLE, "playlists": []})


class SaveView(HomeAssistantView):
    url = "/api/voice_brain/save"
    name = "api:voice_brain:save"

    async def post(self, request):
        data = await _body(request)
        playlist = _text(data.get("playlist"))
        if not playlist:
            return self.json({"ok": False, "say": "Melyik listába?"})
        reply = await worker.quick(request.app[KEY_HASS], "save_to_playlist", _text(data.get("player")), playlist)
        return self.json(reply or UNREACHABLE)


def register(hass):
    for view in (LikeView, PlaylistsView, SaveView):
        hass.http.register_view(view())

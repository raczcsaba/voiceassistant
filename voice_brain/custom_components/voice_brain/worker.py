"""Client for the Claude worker: a separate service that takes over anything that isn't quick device control.

The worker speaks its own status and final answer on the satellite (assist_satellite.announce), so voice_brain
only hands the request over and says the worker's short acknowledgement.
"""
import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "voice_brain"
# The worker on the LAN; override with the config entry option "worker_url"
WORKER_URL = "http://192.168.1.142:8099"
TASK_TIMEOUT = 2  # seconds; the voice reply waits on this
QUICK_TIMEOUT = 8  # like / save / playlist list call Tidal through the worker
PENDING_TIMEOUT = 0.3  # asked before most short commands, so it must never slow them down


def url(hass):
    return hass.data.get(DOMAIN, {}).get("worker_url", WORKER_URL)


async def _post(hass, path, body, timeout):
    """The worker's JSON reply, or None if it is unreachable or answers with an error."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(url(hass) + path, json=body, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                _LOGGER.warning("Worker %s answered %s", path, resp.status)
                return None
            return await resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError, ValueError) as err:
        _LOGGER.warning("Worker %s unreachable: %r", path, err)
        return None


async def pending(hass):
    """{"pending": bool, "kind", "title", "satellite", "expires_in"}: whether the worker asked a question and waits
    for the answer. None if unreachable, slow or not supported (the caller then carries on as usual)."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(url(hass) + "/pending", timeout=aiohttp.ClientTimeout(total=PENDING_TIMEOUT)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            return data if isinstance(data, dict) else None
    except (TimeoutError, aiohttp.ClientError, ValueError) as err:
        _LOGGER.debug("Worker /pending unavailable: %r", err)
        return None


async def task(hass, text, lang, satellite, device_id, source="voice_brain"):
    """{"accepted": true, "ack": ...} or {"accepted": false, "reason": ..., "say": ...}; None if unreachable."""
    return await _post(hass, "/task", {"text": text, "lang": lang, "satellite": satellite,
                                       "device_id": device_id, "source": source}, TASK_TIMEOUT)


async def cancel(hass):
    """{"cancelled": bool}: whether a running Claude task was stopped; None if unreachable."""
    return await _post(hass, "/cancel", {}, TASK_TIMEOUT)


async def quick(hass, action, player=None, playlist=None):
    """action: like | save_to_playlist | list_playlists -> {"ok", "say", "playlists"?}; None if unreachable."""
    return await _post(hass, "/quick", {"action": action, "player": player, "playlist": playlist}, QUICK_TIMEOUT)

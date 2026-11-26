"""Home Assistant REST client: states, services, the jellyfin_panel play endpoint."""
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class HAError(Exception):
    pass


class HomeAssistant:
    def __init__(self, url, token, session):
        self.url = url.rstrip("/")
        self.token = token
        self.session = session

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, method, path, json=None, timeout=20):
        async with self.session.request(method, self.url + path, json=json, headers=self._headers,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.content_type == "application/json":
                data = await resp.json()
            else:
                data = await resp.text()
            if resp.status >= 400:
                raise HAError(f"HA {method} {path} -> {resp.status}: {str(data)[:200]}")
            return data

    async def states(self):
        return await self._request("GET", "/api/states")

    async def state(self, entity_id):
        return await self._request("GET", f"/api/states/{entity_id}")

    async def call_service(self, domain, service, data, timeout=60):
        return await self._request("POST", f"/api/services/{domain}/{service}", json=data, timeout=timeout)

    async def announce(self, satellite, message, timeout=60):
        return await self.call_service("assist_satellite", "announce",
                                       {"entity_id": satellite, "message": message, "preannounce": False},
                                       timeout=timeout)

    async def start_conversation(self, satellite, message, timeout=60):
        """Ask on the satellite and listen for the answer without a wake word."""
        return await self.call_service("assist_satellite", "start_conversation",
                                       {"entity_id": satellite, "start_message": message, "preannounce": False},
                                       timeout=timeout)

    async def get(self, path, timeout=20):
        return await self._request("GET", path, timeout=timeout)

    async def service_response(self, domain, service, data, timeout=20):
        """A read-only service that returns data (e.g. weather.get_forecasts)."""
        result = await self._request("POST", f"/api/services/{domain}/{service}?return_response", json=data,
                                     timeout=timeout)
        return (result or {}).get("service_response") if isinstance(result, dict) else None

    async def post(self, path, body, timeout=90):
        return await self._request("POST", path, json=body, timeout=timeout)

"""Minimal Music Assistant websocket client (aiohttp)."""
import asyncio
import itertools
import json
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class MAError(Exception):
    pass


class MusicAssistant:
    """One persistent, authenticated websocket; reconnects on demand."""

    def __init__(self, url, token, session=None, timeout=20):
        self.url = url
        self.token = token
        self.timeout = timeout
        self._session = session
        self._own_session = session is None
        self._ws = None
        self._reader = None
        self._pending = {}
        self._partial = {}
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    async def _connect(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url, max_msg_size=0, heartbeat=30)
        await self._ws.receive_json(timeout=self.timeout)  # server info
        self._reader = asyncio.create_task(self._read())
        result = await self._call("auth", {"token": self.token})
        if not (result or {}).get("authenticated"):
            raise MAError("Music Assistant authentication failed")

    async def _read(self):
        ws = self._ws
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if "message_id" not in data:
                    continue  # an event
                mid = str(data["message_id"])
                if data.get("partial"):
                    # Large list results arrive in chunks; collect until the final message
                    self._partial.setdefault(mid, []).extend(data.get("result") or [])
                    continue
                fut = self._pending.pop(mid, None)
                chunks = self._partial.pop(mid, None)
                if fut and not fut.done():
                    if "error_code" in data:
                        fut.set_exception(MAError(f"{data.get('error_code')}: {data.get('details')}"))
                    elif chunks is not None:
                        fut.set_result(chunks + list(data.get("result") or []))
                    else:
                        fut.set_result(data.get("result"))
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MAError("Music Assistant connection closed"))
            self._pending.clear()

    async def _call(self, command, args):
        mid = str(next(self._ids))
        fut = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send_str(json.dumps({"command": command, "args": args, "message_id": mid}))
        try:
            return await asyncio.wait_for(fut, self.timeout)
        finally:
            self._pending.pop(mid, None)

    async def call(self, command, **args):
        async with self._lock:
            if self._ws is None or self._ws.closed:
                await self._connect()
        return await self._call(command, args)

    async def close(self):
        if self._ws is not None:
            await self._ws.close()
        if self._reader:
            self._reader.cancel()
        if self._own_session and self._session:
            await self._session.close()

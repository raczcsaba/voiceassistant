"""Read-only: print the household's music artists and film titles as JSON on stdout.

Runs INSIDE the Home Assistant container (it has aiohttp and can reach Music Assistant's internal
API, which is where HA's own MA integration connects). The MA token is read from HA's config entry
and is never printed. Film titles come from voice_brain's /config/voice_titles.json cache.
"""
import asyncio
import json
import os

import aiohttp

ENTRIES = "/config/.storage/core.config_entries"
TITLES = "/config/voice_titles.json"


async def music(entry):
    out = {"library": [], "favorites": [], "played": {}, "recent": []}
    async with aiohttp.ClientSession() as session, session.ws_connect(entry["url"] + "/ws", max_msg_size=0) as ws:
        await ws.receive_json()  # server info
        counter = 0

        async def call(command, **args):
            nonlocal counter
            counter += 1
            await ws.send_json({"message_id": str(counter), "command": command, "args": args})
            while True:
                message = await ws.receive_json()
                if message.get("message_id") == str(counter):
                    if "error_code" in message:
                        raise RuntimeError(f"{command}: {message.get('details')}")
                    return message.get("result") or []

        await call("auth", token=entry["token"])
        out["library"] = [a["name"] for a in await call("music/artists/library_items", limit=1000)]
        out["favorites"] = [a["name"] for a in await call("music/artists/library_items", favorite=True, limit=200)]
        out["favorites"] += [a["name"] for t in await call("music/tracks/library_items", favorite=True, limit=200)
                             for a in t.get("artists", [])]
        for rank, track in enumerate(await call("music/tracks/library_items", limit=300, order_by="play_count_desc")):
            for artist in track.get("artists", []):
                out["played"][artist["name"]] = out["played"].get(artist["name"], 0) + (300 - rank)
        out["recent"] = [a["name"] for a in await call("music/artists/library_items", limit=50,
                                                         order_by="last_played_desc")]
    return out


def main():
    with open(ENTRIES, encoding="utf-8") as f:
        entries = json.load(f)["data"]["entries"]
    entry = next(e["data"] for e in entries if e["domain"] == "music_assistant")
    result = {"titles": {}}
    if os.path.exists(TITLES):
        with open(TITLES, encoding="utf-8") as f:
            result["titles"] = json.load(f)
    result.update(asyncio.run(music(entry)))
    print(json.dumps(result, ensure_ascii=True))  # ASCII-escaped so qm guest exec can't mangle it


main()

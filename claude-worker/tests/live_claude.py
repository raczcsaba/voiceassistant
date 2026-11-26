"""Real Claude calls with dry-run tools and the dry-run speaker: nothing plays, nothing is spoken.

Usage: python -m tests.live_claude --config /path/config.json --model claude-haiku-5-5 "kérés 1" "kérés 2"
       python -m tests.live_claude --config ... --quick      (the /quick endpoint, dry-run)
"""
import argparse
import asyncio
import json
import logging
import time

from aiohttp.test_utils import TestClient, TestServer
from voice_claude import config as config_mod
from voice_claude.loop import Task
from voice_claude.server import build


async def run_requests(cfg, model, requests, satellite="assist_satellite.dry_run"):
    service, cleanup = build(cfg, dry_run=True)
    try:
        await service.catalogue.get()
        total = 0.0
        for text in requests:
            runner = service.runner_factory()
            runner.model = model
            service.tools.writes.clear()
            service.speaker.spoken.clear()
            task = Task(text, satellite=satellite, source="live_claude")
            t = time.monotonic()
            await runner.run(task)
            secs = time.monotonic() - t
            total += task.cost
            print(f"\n=== [{model}] {text}")
            print(f"outcome={task.outcome} turns={task.turns} {secs:.1f}s cost=${task.cost:.4f} web_searches={task.web_searches}")
            for c in task.tools_called:
                print(f"  tool {c['name']}({json.dumps(c['input'], ensure_ascii=False)[:220]})"
                      + (f" {c.get('ms')}ms" if c.get("ms") is not None else "") + (" ERROR" if c.get("error") else ""))
            for w in service.tools.writes:
                print(f"  would send: {json.dumps(w, ensure_ascii=False)[:220]}")
            first = service.speaker.spoken[0][0] if service.speaker.spoken else None
            for ts, _sat, said in service.speaker.spoken:
                print(f"  said +{ts - first:.1f}s: {said}")
        print(f"\nTOTAL ${total:.4f} for {len(requests)} requests on {model}")
    finally:
        await cleanup()


async def run_quick(cfg):
    service, cleanup = build(cfg, dry_run=True)
    client = TestClient(TestServer(service.app()))
    await client.start_server()
    try:
        for body in ({"action": "list_playlists"}, {"action": "like", "player": None},
                     {"action": "save_to_playlist", "playlist": "rok", "player": None},
                     {"action": "save_to_playlist", "playlist": "jazz", "player": None},
                     {"action": "save_to_playlist", "playlist": None, "player": None}):
            t = time.monotonic()
            r = await (await client.post("/quick", json=body)).json()
            if "playlists" in r:
                r["playlists"] = f"{len(r['playlists'])} items, first: {r['playlists'][0]}"
            print(f"{json.dumps(body)} -> {(time.monotonic() - t) * 1000:.0f}ms {json.dumps(r, ensure_ascii=False)}")
        for w in service.tools.writes:
            print(f"  would send: {json.dumps(w, ensure_ascii=False)}")
    finally:
        await client.close()
        await cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--satellite", default="assist_satellite.dry_run", help="the satellite id Claude sees (nothing is spoken)")
    parser.add_argument("requests", nargs="*")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = config_mod.load(args.config)
    asyncio.run(run_quick(cfg) if args.quick else run_requests(cfg, args.model, args.requests, args.satellite))

"""Read-only checks against the real Music Assistant, Jellyfin and Home Assistant.

Writes run with dry_run=True, so they only log the exact command. Nothing is played or spoken.
Usage: python -m tests.live_readonly --config /path/config.json
"""
import argparse
import asyncio
import json
import logging
import time

from voice_claude import config as config_mod
from voice_claude.server import build


def show(label, data, width=700):
    text = json.dumps(data, ensure_ascii=False)
    print(f"--- {label} ({len(text)} chars)\n{text[:width]}{' ...' if len(text) > width else ''}")


async def timed(label, coro, width=700):
    t = time.monotonic()
    result = await coro
    show(f"{label} [{(time.monotonic() - t) * 1000:.0f} ms]", result, width)
    return result


async def main(cfg_path, rebuild):
    cfg = config_mod.load(cfg_path)
    service, cleanup = build(cfg, dry_run=True)
    tools = service.tools
    try:
        t = time.monotonic()
        data = await service.catalogue.refresh(force=rebuild)
        print(f"catalogue: {data['counts']}, {len(data['text'])} chars, built in {data['build_seconds']}s "
              f"(this call {time.monotonic() - t:.1f}s)")
        print("catalogue head:\n" + data["text"][:600] + "\n...\n" + data["text"][-500:])
        key = config_mod.secret(cfg, cfg["anthropic"]["key_file"])
        if key:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            for model in ("claude-haiku-5-5", "claude-sonnet-5-5"):
                n = client.messages.count_tokens(model=model, messages=[{"role": "user", "content": data["text"]}])
                print(f"catalogue tokens ({model}): {n.input_tokens}")

        await timed("players", tools.players.all())
        await timed("get_now_playing()", tools.get_now_playing())
        await timed("search_music(Daft Punk Get Lucky, track)", tools.search_music("Daft Punk Get Lucky", ["track"], 3))
        await timed("search_music(smooth jazz, library_only)", tools.search_music("jazz", None, 5, True))
        await timed("search_music(smooth jazz playlist)", tools.search_music("smooth jazz", ["playlist"], 5))
        await timed("get_playlist_tracks(rock)", tools.get_playlist_tracks("rock", 5))
        await timed("get_playlist_tracks(Dark Jazz)", tools.get_playlist_tracks("Dark Jazz", 5))
        await timed("match_playlist(forza, editable)", tools.match_playlist("forza", True))
        await timed("match_playlist(rok, editable)", tools.match_playlist("rok", True))
        await timed("match_playlist(blabla, editable)", tools.match_playlist("blabla", True))
        await timed("search_movies(vándorló palota)", tools.search_movies("vándorló palota"))
        await timed("search_movies(Frieren)", tools.search_movies("Frieren"))

        print("\n=== dry-run write paths ===")
        await timed("play_music", tools.play_music(["library://track/1"], "Pi", "replace", True, True))
        await timed("create_playlist", tools.create_playlist("Chill teszt"))
        await timed("create_playlist(existing)", tools.create_playlist("rock"))
        await timed("add_to_playlist", tools.add_to_playlist("forza", ["library://track/1"]))
        await timed("like(current)", tools.like(None, None))
        films = data.get("films") or []
        if films:
            await timed("play_movie", tools.play_movie(films[0]["ref"]))
            series = next((f for f in films if f["type"] == "Series"), None)
            if series:
                await timed("play_movie(series)", tools.play_movie(series["ref"]))
        print("\nlogged writes:")
        for w in tools.writes:
            print("  ", json.dumps(w, ensure_ascii=False))
    finally:
        await cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main(args.config, args.rebuild))

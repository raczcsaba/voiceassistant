#!/usr/bin/env python3
"""Mac test device: talk to the real Home Assistant voice pipeline and see where the time goes.

    python ha_voice.py                hands-free, always listening
    python ha_voice.py --ptt          Enter to start, Enter to stop
    python ha_voice.py --file a.wav   send a 16 kHz mono file instead of the microphone
    python ha_voice.py --no-tts       skip the spoken reply

Needs HA's token in ~/.config/voice-test/ha-token.
"""
import argparse
import asyncio
import json
import os
import subprocess
import tempfile
import time
import urllib.request
import wave

import numpy as np
import websockets

# host:port of Home Assistant, and a long-lived access token (Profile > Security in HA)
HA = os.environ.get("HA_HOST", "homeassistant.local:8123")
TOKEN_FILE = os.path.expanduser("~/.config/voice-test/ha-token")
CHUNK = 4096


async def pipeline_ids(ws):
    """Home Assistant's voice pipelines, name to id. Uses message id 1; runs start at 2."""
    await ws.send(json.dumps({"id": 1, "type": "assist_pipeline/pipeline/list"}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == 1:
            return {p["name"]: p["id"] for p in msg["result"]["pipelines"]}


async def run_pipeline(ws, msg_id, pcm, speak, pipeline=None):
    """Send one utterance. Returns a dict of timings in ms, measured from the end of the audio."""
    start = time.perf_counter()
    since = lambda: (time.perf_counter() - start) * 1000
    await ws.send(json.dumps({
        "id": msg_id, "type": "assist_pipeline/run", "start_stage": "stt",
        "end_stage": "tts" if speak else "intent", "input": {"sample_rate": 16000},
        **({"pipeline": pipeline} if pipeline else {}),
    }))
    out = {"text": "", "reply": "", "url": None}
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") != msg_id:
            continue
        if msg["type"] == "result":
            if not msg["success"]:
                raise RuntimeError(msg["error"])
            continue
        event = msg["event"]
        kind, data = event["type"], event.get("data") or {}
        if kind == "run-start":
            handler = bytes([data["runner_data"]["stt_binary_handler_id"]])
            for i in range(0, len(pcm), CHUNK):
                await ws.send(handler + pcm[i:i + CHUNK])
            await ws.send(handler)
            start = time.perf_counter()
        elif kind == "stt-end":
            out["text"] = data["stt_output"]["text"]
            out["stt"] = since()
        elif kind == "intent-end":
            out["reply"] = data["intent_output"]["response"]["speech"]["plain"]["speech"]
            out["action"] = since()
        elif kind == "tts-end":
            out["url"] = data["tts_output"]["url"]
            out["tts"] = since()
        elif kind == "error":
            raise RuntimeError(f"{data.get('code')}: {data.get('message')}")
        elif kind == "run-end":
            return out


def play(url):
    if not url.startswith("http"):
        url = f"http://{HA}{url}"
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(url)[1] or ".mp3") as f:
        f.write(urllib.request.urlopen(url, timeout=10).read())
        f.flush()
        subprocess.run(["afplay", f.name], check=False)


def report(result, wait_ms):
    stt, action = result.get("stt", 0), result.get("action", 0)
    print(f'  heard: "{result["text"]}"')
    print(f'  reply: {result["reply"]}')
    line = f"  speech-to-text {stt:.0f} ms, command {action - stt:.0f} ms = {action:.0f} ms"
    if wait_ms:
        line += f" (+{wait_ms} ms waiting for you to stop = {action + wait_ms:.0f} ms total)"
    print(line)


def load_wav(path):
    with wave.open(path) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("Need a 16 kHz, mono, 16-bit wav")
        return w.readframes(w.getnframes())


async def main(args):
    token = open(TOKEN_FILE).read().strip()
    async with websockets.connect(f"ws://{HA}/api/websocket", max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(await ws.recv())["type"] != "auth_ok":
            raise SystemExit("Home Assistant rejected the token")
        msg_id = 2
        speak = not args.no_tts
        pipeline = (await pipeline_ids(ws))[args.pipeline] if args.pipeline else None
        if args.file:
            for path in args.file:
                result = await run_pipeline(ws, msg_id, load_wav(path), speak, pipeline)
                msg_id += 1
                print(path)
                report(result, 0)
                if speak and result["url"]:
                    await asyncio.to_thread(play, result["url"])
            return
        from va.listen import Listener

        silence = 300
        listener = Listener(silence_ms=silence)
        print("Ready." + (" Enter to start and stop talking." if args.ptt else " Just talk. Ctrl+C to quit."))
        while True:
            get = listener.push_to_talk if args.ptt else listener.next_utterance
            audio, _ = await asyncio.to_thread(get)
            if not len(audio):
                continue
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
            print("…")
            result = await run_pipeline(ws, msg_id, pcm, speak, pipeline)
            msg_id += 1
            report(result, 0 if args.ptt else silence)
            if speak and result["url"]:
                await asyncio.to_thread(play, result["url"])
            await asyncio.to_thread(listener.flush)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ptt", action="store_true")
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--file", nargs="*")
    parser.add_argument("--pipeline", help="Pipeline name, for example 'Fast Local HU'")
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        pass

#!/usr/bin/env python3
"""Menu bar voice assistant: say the wake word, then a command. Home Assistant does the rest."""
import asyncio
import collections
import os
import queue
import subprocess
import threading
import time
import wave

import numpy as np
import rumps
import sounddevice as sd
import websockets

from ha_voice import HA, TOKEN_FILE, pipeline_ids, play, run_pipeline
from va.listen import FRAME, SR, SileroVAD

WAKE_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
WAKE_CHUNK = 1280
COMMAND_TIMEOUT = 6
START_TIMEOUT = 4
SILENCE_FRAMES = 300 // 32
PREROLL_FRAMES = 6
SOUND_WAKE = "/System/Library/Sounds/Tink.aiff"
SOUND_FAIL = "/System/Library/Sounds/Basso.aiff"
ICONS = {"off": "🔇", "wake": "🎙️", "listening": "🔴", "busy": "⏳", "error": "⚠️"}
PIPELINES = {"English": "Fast Local", "Magyar": "Fast Local HU"}
LANGUAGE_FILE = os.path.expanduser("~/.config/voice-test/language")
RECORDINGS = os.path.expanduser("~/Library/Logs/VoiceAssistant-recordings")
LOG = os.path.expanduser("~/Library/Logs/VoiceAssistant.log")


def log(line):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%F %T')} {line}\n")


class Engine(threading.Thread):
    """Owns the microphone and the Home Assistant connection, away from the UI thread."""

    def __init__(self, on_state):
        super().__init__(daemon=True)
        self.on_state = on_state
        self.enabled = threading.Event()
        self.speak = True
        self.language = open(LANGUAGE_FILE).read().strip() if os.path.exists(LANGUAGE_FILE) else "English"

    def run(self):
        from openwakeword.model import Model

        try:
            self.wake = Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")
            self.vad = SileroVAD()
        except Exception as err:  # Without this the thread dies and the menu looks fine
            log(f"startup failed: {err!r}")
            self.on_state("error")
            return
        while True:
            self.enabled.wait()
            try:
                asyncio.run(self._session())
            except Exception as err:  # A dropped connection or mic error must not end the app
                log(f"error: {err!r}")
                self.on_state("error")
                time.sleep(3)

    async def _session(self):
        token = open(TOKEN_FILE).read().strip()
        audio = queue.Queue()
        stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME,
                                callback=lambda d, *_: audio.put(d[:, 0].copy()))
        async with websockets.connect(f"ws://{HA}/api/websocket", max_size=None, ping_interval=20) as ws:
            await ws.recv()
            await ws.send(f'{{"type":"auth","access_token":"{token}"}}')
            await ws.recv()
            msg_id = 2
            ids = await pipeline_ids(ws)
            pipelines = {lang: ids[name] for lang, name in PIPELINES.items()}
            with stream:  # The mic is released as soon as listening is switched off
                while self.enabled.is_set():
                    self.on_state("wake")
                    if not await asyncio.to_thread(self._wait_for_wake, audio):
                        return
                    subprocess.Popen(["afplay", SOUND_WAKE])
                    self.on_state("listening")
                    pcm = await asyncio.to_thread(self._record, audio)
                    if pcm is None:
                        continue
                    self.on_state("busy")
                    self._save(pcm)
                    result = await run_pipeline(ws, msg_id, pcm, self.speak, pipelines[self.language])
                    msg_id += 1
                    log(f'"{result["text"]}" -> {result["reply"]} '
                        f'(stt {result.get("stt", 0):.0f} ms, action {result.get("action", 0):.0f} ms)')
                    if self.speak and result.get("url"):
                        await asyncio.to_thread(play, result["url"])
                    self._drain(audio)
                    self.wake.reset()
        self.on_state("off")

    @staticmethod
    def _save(pcm):
        """Keep each command on this Mac, as test material for recognition tuning."""
        os.makedirs(RECORDINGS, exist_ok=True)
        with wave.open(os.path.join(RECORDINGS, time.strftime("%Y%m%d-%H%M%S.wav")), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)

    @staticmethod
    def _drain(audio):
        while not audio.empty():
            audio.get_nowait()

    def _wait_for_wake(self, audio):
        pending = np.zeros(0, dtype=np.int16)
        while self.enabled.is_set():
            try:
                frame = audio.get(timeout=0.5)
            except queue.Empty:
                continue
            pending = np.concatenate([pending, (frame * 32767).astype(np.int16)])
            while len(pending) >= WAKE_CHUNK:
                chunk, pending = pending[:WAKE_CHUNK], pending[WAKE_CHUNK:]
                if self.wake.predict(chunk)[WAKE_MODEL] >= WAKE_THRESHOLD:
                    self._drain(audio)
                    self.wake.reset()
                    return True
        return False

    def _record(self, audio):
        """One command after the wake word; None if nothing was said."""
        self.vad.reset()
        preroll = collections.deque(maxlen=PREROLL_FRAMES)
        speech, voiced, silent, started = [], 0, 0, False
        begin = time.monotonic()
        while time.monotonic() - begin < (COMMAND_TIMEOUT if started else START_TIMEOUT):
            try:
                frame = audio.get(timeout=0.5)
            except queue.Empty:
                continue
            p = self.vad(frame)
            if not started:
                preroll.append(frame)
                voiced = voiced + 1 if p > 0.5 else 0
                if voiced >= 2:
                    started, speech = True, list(preroll)
                continue
            speech.append(frame)
            silent = silent + 1 if p < 0.35 else 0
            if silent >= SILENCE_FRAMES:
                break
        if not started:
            return None
        return (np.clip(np.concatenate(speech), -1, 1) * 32767).astype(np.int16).tobytes()


class VoiceApp(rumps.App):
    def __init__(self):
        super().__init__("Voice", title=ICONS["off"], quit_button="Quit")
        self.toggle = rumps.MenuItem("Start listening", callback=self.on_toggle)
        self.spoken = rumps.MenuItem("Spoken replies", callback=self.on_spoken)
        self.spoken.state = True
        self.languages = [rumps.MenuItem(lang, callback=self.on_language) for lang in PIPELINES]
        self.menu = [self.toggle, self.spoken, ("Language", self.languages), rumps.MenuItem("Say: Hey Jarvis, then your command"), None,
                     rumps.MenuItem("Open log", callback=lambda _: subprocess.run(["open", LOG]))]
        self.engine = Engine(self.set_state)
        for item in self.languages:
            item.state = item.title == self.engine.language
        self.engine.start()
        self.on_toggle(self.toggle)

    def set_state(self, state):
        self.title = ICONS[state]

    def on_toggle(self, item):
        if self.engine.enabled.is_set():
            self.engine.enabled.clear()
            item.title = "Start listening"
            self.title = ICONS["off"]
        else:
            self.engine.enabled.set()
            item.title = "Stop listening"
            self.title = ICONS["wake"]

    def on_language(self, item):
        self.engine.language = item.title
        for other in self.languages:
            other.state = other is item
        with open(LANGUAGE_FILE, "w") as f:
            f.write(item.title)

    def on_spoken(self, item):
        item.state = not item.state
        self.engine.speak = bool(item.state)


if __name__ == "__main__":
    VoiceApp().run()

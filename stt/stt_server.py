#!/usr/bin/env python3
"""Wyoming speech-to-text server for Home Assistant.

English: Parakeet TDT 0.6B v3 (int8 ONNX, CPU).
Hungarian: a Hungarian fine-tuned Whisper large-v3-turbo on whisper.cpp (GPU), with
  - a vocabulary prompt (the household's artists and film titles, see make_prompt.py),
  - a timeout that grows with the clip length,
  - Parakeet running alongside as the fallback, so a whisper failure costs no extra time,
  - a guard that returns empty text instead of whisper's typical hallucinations.
Settings come from environment variables (see the systemd unit); nothing secret lives here.
"""
import asyncio
import io
import json
import logging
import os
import re
import time
import unicodedata
import urllib.request
import uuid
import wave
from functools import partial

import numpy as np
import onnx_asr
import onnxruntime
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer

ENV = os.environ.get
MODEL = "nemo-parakeet-tdt-0.6b-v3"
URI = ENV("STT_URI", "tcp://0.0.0.0:10300")
LANGUAGES = ["en", "hu"]
WHISPER_URL = ENV("WHISPER_URL", "http://127.0.0.1:8090/inference")
# Vocabulary prompt (prompt/make_prompt.py). Off by default: with the Hungarian fine-tune it made things worse
# (benchmark in README). Set STT_PROMPT_FILE=/opt/voice/stt_prompt.txt to use it.
PROMPT_FILE = ENV("STT_PROMPT_FILE", "")
VAD_MODEL = ENV("STT_VAD_MODEL", "/opt/voice/models/silero_vad.onnx")  # empty string = no VAD guard
DEBUG_DIR = ENV("STT_DEBUG_DIR", "/opt/voice/stt-debug")  # requests are saved only while this folder exists
DEBUG_MAX = int(ENV("STT_DEBUG_MAX", "20"))
AUDIO_CTX = ENV("WHISPER_AUDIO_CTX", "auto")  # "auto": fit the clip; 0 = always the whole 30 s window
CTX_MIN = int(ENV("WHISPER_CTX_MIN", "1000"))  # encoder frames (20 ms each); fewer than ~1000 costs accuracy
CTX_PAD = int(ENV("WHISPER_CTX_PAD", "250"))  # frames added after the clip in "auto"
BEAM = ENV("WHISPER_BEAM", "5")
GUARD = ENV("STT_GUARD", "1") == "1"
FALLBACK_HEAD_START = float(ENV("STT_FALLBACK_AFTER_S", "1.0"))  # whisper usually answers in 0.4-0.6 s
SOFT_DEADLINE_S = float(ENV("STT_SOFT_DEADLINE_S", "2.0"))  # + 0.1 s per audio second; then Parakeet may win
MIN_SPEECH_S = float(ENV("STT_MIN_SPEECH_S", "0.2"))  # less voiced audio than this counts as "nothing said"
SR = 16000

_LOGGER = logging.getLogger("stt")
ATTRIBUTION = Attribution(name="NVIDIA", url="https://huggingface.co/nvidia/parakeet-tdt-0.6-v3")
INFO = Info(asr=[AsrProgram(
    name="parakeet-onnx", description="Parakeet TDT 0.6 v3 (ONNX) + Hungarian Whisper", attribution=ATTRIBUTION,
    installed=True, version="2.0",
    models=[AsrModel(name=MODEL, description=MODEL, attribution=ATTRIBUTION, installed=True,
                     languages=LANGUAGES, version="3")])])


def whisper_timeout(seconds):
    """Turbo on the RX 6700 needs ~0.1-0.3 s per clip; leave room for a busy GPU, but never hang on."""
    return min(15.0, 2.0 + 0.6 * seconds)


_prompt_cache = {"mtime": None, "text": ""}


def prompt():
    """The vocabulary prompt, re-read whenever the daily refresh rewrites the file."""
    if not PROMPT_FILE:
        return ""
    try:
        mtime = os.stat(PROMPT_FILE).st_mtime
    except OSError:
        return ""
    if mtime != _prompt_cache["mtime"]:
        with open(PROMPT_FILE, encoding="utf-8") as f:
            _prompt_cache.update(mtime=mtime, text=" ".join(f.read().split()))
    return _prompt_cache["text"]


def wav_bytes(samples):
    audio = io.BytesIO()
    with wave.open(audio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return audio.getvalue()


def audio_context(seconds, setting=None):
    """Encoder window for this clip. The full 30 s window (1500) costs ~1 s on the RX 6700, 1000 (20 s) ~0.45 s,
    400 (8 s) ~0.3 s but loses accuracy and drops the end of longer commands (the 10.5 s timeout)."""
    setting = AUDIO_CTX if setting is None else str(setting)
    if setting != "auto":
        return int(setting)
    return min(1500, max(CTX_MIN, int(seconds * 50) + CTX_PAD))


def whisper(samples, use_prompt=True, audio_ctx=None, url=None, response_format="verbose_json"):
    """One request to the whisper.cpp server; returns (text, segments)."""
    fields = {"language": "hu", "response_format": response_format, "temperature": "0", "beam_size": BEAM,
              "audio_ctx": str(audio_context(len(samples) / SR, audio_ctx)), "no_timestamps": "true",
              # verbose_json would otherwise run language detection too (+150 ms); the language is fixed
              "no_language_probabilities": "true"}
    text_prompt = prompt() if use_prompt else ""
    if text_prompt:
        fields["prompt"] = text_prompt
    boundary = uuid.uuid4().hex
    body = b""
    for key, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
             "Content-Type: audio/wav\r\n\r\n").encode() + wav_bytes(samples) + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(url or WHISPER_URL, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    reply = json.load(urllib.request.urlopen(request, timeout=whisper_timeout(len(samples) / SR)))
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply.get("text", "").strip(), reply.get("segments", [])


class SpeechDetector:
    """Silero VAD (ONNX, CPU, ~1 ms per second of audio): how many seconds of the clip are voiced."""

    def __init__(self, path):
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"])

    def speech_seconds(self, samples, threshold=0.5):
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(64, dtype=np.float32)
        voiced = 0
        sr = np.array(SR, dtype=np.int64)
        for start in range(0, len(samples) - 511, 512):
            chunk = samples[start:start + 512].astype(np.float32)
            frame = np.concatenate([context, chunk])[None, :]
            out, state = self.session.run(None, {"input": frame, "state": state, "sr": sr})
            context = chunk[-64:]
            voiced += float(out[0][0]) >= threshold
        return voiced * 512 / SR


# Phrases that the Hungarian Whisper produces from silence or noise: subtitle credits and video outros.
HALLUCINATIONS = re.compile(
    r"feliratoz|feliratkoz|felirat(ot|ok|ta)|amara\.org|szinkroniz|k[öo]sz[öo]n[öo]m a figyelm|k[öo]sz[öo]n[öo]m,? hogy|"
    r"iratkozz|kövess(etek)? |like-?ol|www\.|\.com|\.hu\b|youtube|zene\]|\[zene|♪|\(zene|nevet\)|taps\)",
    re.IGNORECASE)


def _plain(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text).split()


def collapse(text):
    """Remove back-to-back copies of a phrase (1-8 words): whisper's decoder loops.
    "Állít meg a zenét, állít meg a zenét." -> "Állít meg a zenét," """
    tokens = text.split()
    key = [" ".join(_plain(t)) for t in tokens]
    changed = True
    while changed:
        changed = False
        for size in range(8, 0, -1):
            for start in range(0, len(tokens) - 2 * size + 1):
                if key[start:start + size] == key[start + size:start + 2 * size] and any(key[start:start + size]):
                    if size == 1 and len(key[start]) < 3:  # "a a", "le le": leave short words alone
                        continue
                    del tokens[start + size:start + 2 * size], key[start + size:start + 2 * size]
                    changed = True
                    break
            if changed:
                break
    return " ".join(tokens).rstrip(",;") if len(tokens) else ""


def hallucination(text, segments, speech_s, prompt_text):
    """Why this whisper output should be dropped, or None to keep it."""
    words = _plain(text)
    if not words:
        return "empty"
    if HALLUCINATIONS.search(text):
        return "known phrase"
    plain_prompt = " ".join(_plain(prompt_text))
    if prompt_text and len(words) >= 4 and " ".join(words) in plain_prompt:
        return "prompt echo"
    if segments:
        no_speech = max(s.get("no_speech_prob", 0) for s in segments)
        logprob = min(s.get("avg_logprob", 0) for s in segments)
        if no_speech > 0.6 and logprob < -0.7:
            return f"no speech {no_speech:.2f}, logprob {logprob:.2f}"
        if logprob < -1.2 and speech_s < 1.0:
            return f"low confidence {logprob:.2f}"
    return None


def save_debug(samples, language, text):
    """While DEBUG_DIR exists, keep the first DEBUG_MAX requests as WAVs to tell source clipping from model errors."""
    if not DEBUG_DIR or not os.path.isdir(DEBUG_DIR):
        return
    if sum(name.endswith(".wav") for name in os.listdir(DEBUG_DIR)) >= DEBUG_MAX:
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(DEBUG_DIR, f"{stamp}-{language}.wav"), "wb") as f:
        f.write(wav_bytes(samples))
    with open(os.path.join(DEBUG_DIR, f"{stamp}-{language}.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")


def onset_ms(samples):
    """Leading quiet before the first loud 10 ms frame; ~0 means the speech onset was already cut at the source."""
    frames = samples[:len(samples) // 160 * 160].reshape(-1, 160)
    if not len(frames):
        return 0
    level = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    loud = np.nonzero(level > max(0.02, level.max() * 0.15))[0]
    return int(loud[0] * 10) if len(loud) else -1


class Handler(AsyncEventHandler):
    def __init__(self, model, lock, vad, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.lock = lock
        self.vad = vad
        self.converter = AudioChunkConverter(rate=SR, width=2, channels=1)
        self.audio = bytearray()
        self.language = None

    async def parakeet(self, samples):
        async with self.lock:
            return await asyncio.to_thread(self.model.recognize, samples, sample_rate=SR)

    async def hungarian(self, samples):
        """Whisper first. Parakeet starts only if whisper is slower than usual, so normal requests don't share
        the CPU with it, and a whisper failure falls back to an answer that is already (nearly) done."""
        seconds = len(samples) / SR
        # VAD first (~15 ms for 3 s): whisper-server works one request at a time, and on silence it can loop
        # for seconds, which would delay the next real command.
        speech_s = await asyncio.to_thread(self.vad.speech_seconds, samples) if self.vad else seconds
        if GUARD and self.vad and speech_s < MIN_SPEECH_S:
            return "", f"dropped: {speech_s:.2f} s speech"
        request = asyncio.create_task(asyncio.to_thread(whisper, samples))
        fallback = None
        done, _ = await asyncio.wait({request}, timeout=FALLBACK_HEAD_START + 0.05 * seconds)
        if not done:
            fallback = asyncio.create_task(self.parakeet(samples))
            # A stuck GPU should not cost the whole timeout: past the soft deadline, the first answer wins.
            done, _ = await asyncio.wait({request}, timeout=SOFT_DEADLINE_S + 0.1 * seconds - FALLBACK_HEAD_START)
            if not done:
                await asyncio.wait({request, fallback}, return_when=asyncio.FIRST_COMPLETED)
                if not request.done() and fallback.exception() is None:
                    request.add_done_callback(lambda task: task.exception())
                    return fallback.result(), "parakeet (whisper too slow)"
        try:
            text, segments = await request
        except Exception as err:  # timeout, server down or decode failure: Parakeet beats no answer
            _LOGGER.warning("whisper failed: %r", err)
            return await (fallback or self.parakeet(samples)), "parakeet fallback"
        if fallback:
            fallback.cancel()  # its thread finishes in the background; the result is just not used
        note = f"speech {speech_s:.1f} s"
        if GUARD:
            looped = collapse(text)
            if len(_plain(looped)) < len(_plain(text)):
                # a loop over real speech keeps one copy; a loop over (almost) nothing is noise
                kept, removed = len(_plain(looped)), len(_plain(text)) - len(_plain(looped))
                if speech_s < 0.8 or kept < 2 or (kept <= 3 and removed >= 2 * kept):  # "Az a szörnyet" x3
                    return "", f"dropped (repetition): {text}"
                note += f", loop removed from: {text}"
                text = looped
            why = hallucination(text, segments, speech_s, prompt())
            if why:
                return "", f"dropped ({why}): {text}"
        return text, note

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(INFO.event())
        elif Transcribe.is_type(event.type):
            self.audio.clear()
            self.language = Transcribe.from_event(event).language
        elif AudioChunk.is_type(event.type):
            self.audio += self.converter.convert(AudioChunk.from_event(event)).audio
        elif AudioStop.is_type(event.type):
            samples = np.frombuffer(bytes(self.audio), dtype=np.int16).astype(np.float32) / 32768.0
            start = time.perf_counter()
            text, note = "", ""
            if len(samples) and (self.language or "").lower().startswith("hu"):
                text, note = await self.hungarian(samples)
            elif len(samples):
                text = await self.parakeet(samples)
            _LOGGER.info("%.0f ms for %.2f s audio (%s, onset %d ms%s): %s", (time.perf_counter() - start) * 1000,
                         len(samples) / SR, self.language, onset_ms(samples), f", {note}" if note else "", text)
            try:
                save_debug(samples, self.language or "xx", f"{text}\t{note}")
            except OSError as err:
                _LOGGER.warning("debug save failed: %r", err)
            await self.write_event(Transcript(text=text).event())
            return False
        return True


async def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    model = onnx_asr.load_model(MODEL, quantization="int8")
    model.recognize(np.zeros(SR, dtype=np.float32), sample_rate=SR)
    vad = SpeechDetector(VAD_MODEL) if VAD_MODEL and os.path.exists(VAD_MODEL) else None
    _LOGGER.info("ready on %s (whisper %s, prompt %s, vad %s, guard %s)", URI, WHISPER_URL,
                 f"{len(prompt())} chars" if prompt() else "off", "on" if vad else "off", GUARD)
    await AsyncServer.from_uri(URI).run(partial(Handler, model, asyncio.Lock(), vad))


if __name__ == "__main__":
    asyncio.run(main())

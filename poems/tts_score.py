#!/usr/bin/env python3
"""Score each sample: Hungarian Whisper transcribes it, then letter error rate against the poem, plus median pitch.

    python tts_score.py $AI_ROOT/samples/*.wav     (on the GPU box, uses the voice assistant's Whisper model)
"""
import re
import subprocess
import sys

import numpy as np
import soundfile as sf
import os
ROOT = os.environ.get("AI_ROOT", "/opt/ai")  # model + sample folder on the GPU box

# A second copy of the voice assistant's Whisper server, started without its 8 s limit for this test
SERVER = "http://127.0.0.1:8091/inference"
REF = open(f"{ROOT}/test_poem.txt", encoding="utf-8").read()


SPELLINGS = {"ady": "adi", "páris": "párizs"}


def letters(text):
    """Letters only, so Whisper's own spacing and hyphens (rőzsedalok, fa levelek) don't count as errors."""
    text = text.lower()
    for old, new in SPELLINGS.items():
        text = text.replace(old, new)
    return [c for c in text if c.isalpha()]


def wer(ref, hyp):
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / len(ref)


def pitch(path):
    """Median voice pitch in Hz from autocorrelation of voiced 40 ms frames; lower is deeper."""
    audio, rate = sf.read(path, dtype="float32")
    audio = audio if audio.ndim == 1 else audio.mean(1)
    size, found = int(rate * 0.04), []
    for start in range(0, len(audio) - size, size):
        frame = audio[start:start + size]
        if np.sqrt((frame ** 2).mean()) < 0.02:
            continue
        ac = np.correlate(frame, frame, "full")[size - 1:]
        lo, hi = int(rate / 400), int(rate / 60)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.3 * ac[0]:
            found.append(rate / lag)
    return float(np.median(found)) if found else 0.0


for path in sys.argv[1:]:
    wav16 = "/tmp/score16.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ar", "16000", "-ac", "1", wav16], check=True)
    out = subprocess.run(["curl", "-s", SERVER, "-F", f"file=@{wav16}", "-F", "response_format=text"], capture_output=True, text=True).stdout
    print(f"{path.rsplit('/', 1)[-1]:32} letter errors {wer(letters(REF), letters(out)) * 100:5.1f}%  pitch {pitch(path):5.0f} Hz", flush=True)

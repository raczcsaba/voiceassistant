"""Microphone helpers (16 kHz mono float32)."""
import queue

import numpy as np

SR = 16000


def record_until_enter(prompt="  ● recording... Enter = stop"):
    import sounddevice as sd

    q = queue.Queue()
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=lambda d, *_: q.put(d.copy())):
        input(prompt)
    chunks = []
    while not q.empty():
        chunks.append(q.get())
    return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, dtype=np.float32)


def save_wav(path, audio):
    import soundfile as sf

    sf.write(str(path), audio, SR, subtype="PCM_16")

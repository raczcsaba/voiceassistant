"""Optional TTS: time-to-first-audio for Hungarian voices.

  python tts_bench.py           # benchmark only
  python tts_bench.py --play    # also play each result
"""
import pathlib
import statistics
import subprocess
import sys
import time

REPLIES = [
    "Okay, the living room lights are on.",
    "It's twenty one and a half degrees in the kids room.",
    "Done, the garage door is opening.",
]
PIPER_VOICES = ["en_US-lessac-low", "en_US-lessac-medium"]
VOICE_DIR = pathlib.Path("voices")
play = "--play" in sys.argv


def bench_say():
    out = pathlib.Path("results/say.aiff")
    out.parent.mkdir(exist_ok=True)
    ts = []
    for r in REPLIES:
        t = time.perf_counter()
        subprocess.run(["say", "-v", "Samantha", "-o", str(out), r], check=True)
        ts.append(time.perf_counter() - t)
        if play:
            subprocess.run(["afplay", str(out)])
    print(f"| macOS say (Samantha) | {statistics.median(ts) * 1000:.0f} | full file (say streams directly when speaking live) |")


def bench_piper(voice):
    import sounddevice as sd
    from piper import PiperVoice

    model = VOICE_DIR / f"{voice}.onnx"
    if not model.exists():
        subprocess.run([sys.executable, "-m", "piper.download_voices", "--download-dir", str(VOICE_DIR), voice], check=True)
    v = PiperVoice.load(model)
    list(v.synthesize("Bemelegítés."))  # warm up onnx session
    first, total = [], []
    for r in REPLIES:
        t = time.perf_counter()
        chunks = []
        for i, c in enumerate(v.synthesize(r)):
            if i == 0:
                first.append(time.perf_counter() - t)
            chunks.append(c)
        total.append(time.perf_counter() - t)
        if play:
            for c in chunks:
                sd.play(c.audio_float_array, c.sample_rate, blocking=True)
    print(f"| piper {voice} | {statistics.median(first) * 1000:.0f} | total {statistics.median(total) * 1000:.0f} ms |")


print("| TTS | time to first audio (ms) | note |\n|---|---|---|")
bench_say()
for v in PIPER_VOICES:
    try:
        bench_piper(v)
    except Exception as e:
        print(f"| piper {v} | - | failed: {e} |")

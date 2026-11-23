#!/usr/bin/env python3
"""Read the test poem with Higgs TTS 3, plain and "directed" (emotion, pace and pause tags per sentence).

    HSA_OVERRIDE_GFX_VERSION=10.3.0 python higgs_poem.py
Runs on a Linux GPU box ($AI_ROOT, default /opt/ai) next to native.py from github.com/Saganaki22/Higgs_v3-TTS-ComfyUI (used without ComfyUI).
Needs about 9.5 GB of GPU memory, so the voice assistant's LLM and Whisper are stopped while it runs.
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = os.environ.get("AI_ROOT", "/opt/ai")  # model + sample folder on the GPU box
VOICE_ROOT = os.environ.get("VOICE_ROOT", "/opt/voice")  # whisper.cpp build
sys.path.insert(0, f"{ROOT}/higgs")
import native  # noqa: E402

MODEL_DIR = Path(f"{ROOT}/higgs/higgs-audio-v3-tts-4b")
OUT = Path(f"{ROOT}/samples")
RATE = native.SAMPLE_RATE
DTYPE = torch.float16
REFERENCE = OUT / "higgs_reference.wav"
REFERENCE_TEXT = open(f"{ROOT}/higgs_reference.txt", encoding="utf-8").read().strip()
SCRIPTS = json.load(open(f"{ROOT}/poem_scripts.json", encoding="utf-8"))


class Bundle:
    def __init__(self, device):
        config = native.read_config(MODEL_DIR)
        # bf16 matrix multiplies crash on the RX 6700 (RDNA2), fp16 works and is the same size
        self.model = native.build_native_model(config, DTYPE, "sdpa")
        # Straight onto the GPU: the container has less RAM to spare than the weights need
        native.load_native_weights(self.model, MODEL_DIR, device, DTYPE)
        # The codec's convolutions crash MIOpen on this RX 6700, and it is small, so it runs on the CPU
        self.codec = native.HiggsAudioCodec.from_pretrained(MODEL_DIR, device=torch.device("cpu"), dtype=torch.float32)
        self.tokenizer = native.load_tokenizer(MODEL_DIR)
        self.attention = "sdpa"


def speak(bundle, text, seed):
    audio = native.generate_higgs_audio(
        bundle, text=text, reference_audio=None, reference_audio_path=str(REFERENCE), reference_text=REFERENCE_TEXT,
        max_new_tokens=2048, temperature=0.7, top_p=0.95, top_k=50, seed=seed,
        trim_reference_audio=True, silence_threshold_db=-42.0, max_reference_seconds=15.0)
    return audio["waveform"].reshape(-1).float().numpy()


# Takes per phrase: Whisper on the CPU checks each against the text and the closest is kept,
# which throws out the loops and dropped words Higgs sometimes produces
TAKES = 3
ASR = "http://127.0.0.1:8092/inference"
SPELLINGS = {"ady": "adi", "páris": "párizs"}


def letters(text):
    text = re.sub(r"<\|[^|]*\|>", "", text).lower()
    for old, new in SPELLINGS.items():
        text = text.replace(old, new)
    return "".join(c for c in unicodedata.normalize("NFC", text) if c.isalpha())


def cer(ref, hyp):
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / max(1, len(ref))


def heard(audio):
    sf.write("/tmp/take.wav", audio, RATE)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "/tmp/take.wav", "-ar", "16000", "-ac", "1", "/tmp/take16.wav"], check=True)
    return subprocess.run(["curl", "-s", ASR, "-F", "file=@/tmp/take16.wav", "-F", "response_format=text"],
                          capture_output=True, text=True).stdout


def best_take(bundle, text, seed):
    takes = []
    for k in range(TAKES):
        audio = speak(bundle, text, seed + 100 * k)
        error = cer(letters(text), letters(heard(audio)))
        takes.append((error, k, audio))
        if error < 0.03:
            break
    error, k, audio = min(takes, key=lambda t: t[0])
    print(f"   take {k + 1}/{len(takes)} error {error * 100:4.1f}%  {re.sub(r'<[^>]*>', '', text)[:50]}", flush=True)
    return audio


def main():
    native.CODEC_CONFIG_PATH = Path(f"{ROOT}/higgs/assets/higgs_audio_v2_tokenizer_config.json")
    device = torch.device("cuda")
    started = time.time()
    bundle = Bundle(device)
    print(f"loaded in {time.time() - started:.0f} s, GPU memory {torch.cuda.memory_allocated() / 1e9:.1f} GB", flush=True)
    asr = subprocess.Popen([f"{VOICE_ROOT}/whisper.cpp/build/bin/whisper-server", "-m", f"{VOICE_ROOT}/whisper.cpp/models/hu-turbo-q5.bin",
                            "--host", "127.0.0.1", "--port", "8092", "-t", "6", "-l", "hu", "-ng"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    for name, script in SCRIPTS.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        started = time.time()
        parts = []
        for i, seg in enumerate(script):
            parts.append(best_take(bundle, seg["text"], seed=1234 + i))
            parts.append(np.zeros(int(RATE * seg.get("after", 0.6)), dtype=np.float32))
        audio = np.concatenate(parts)
        audio = 0.9 * audio / max(1e-6, float(np.abs(audio).max()))
        sf.write(OUT / f"{name}.wav", audio, RATE)
        print(f"{name}: {len(audio) / RATE:.1f} s of audio in {time.time() - started:.0f} s", flush=True)
    asr.terminate()


if __name__ == "__main__":
    main()

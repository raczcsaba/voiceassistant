#!/usr/bin/env python3
"""Read the test poem with each local TTS model and voice, one wav per combination.

    HSA_OVERRIDE_GFX_VERSION=10.3.0 python tts_test.py omnivoice|f5|xtts
Runs on a Linux GPU box ($AI_ROOT, default /opt/ai); text in $AI_ROOT/test_poem.txt, results in $AI_ROOT/samples.
"""
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch
ROOT = os.environ.get("AI_ROOT", "/opt/ai")  # model + sample folder on the GPU box

OUT = f"{ROOT}/samples"
TEXT = open(f"{ROOT}/test_poem.txt", encoding="utf-8").read().strip()
# Title line, then one chunk per stanza: these models are steadier on 10-20 second pieces
CHUNKS = [c.replace("\n", " ") for c in TEXT.split("\n\n")]
PAUSE = 0.8

OMNI_VOICES = {
    "omni_deep_old": "male, elderly, very low pitch",
    "omni_deep_mid": "male, middle-aged, very low pitch",
    "omni_low_mid": "male, middle-aged, low pitch",
    "omni_young": "male, young adult, low pitch",
    "omni_female": "female, middle-aged, low pitch",
}
XTTS_VOICES = ["Damien Black", "Viktor Eka", "Craig Gutsy", "Baldur Sanjin", "Torcull Diarmuid",
               "Viktor Menelaos", "Aaron Dreschner", "Ludvig Milivoj", "Ana Florence", "Tammie Ema"]


def save(name, pieces, rate, started):
    gap = np.zeros(int(rate * PAUSE), dtype=np.float32)
    audio = np.concatenate([np.concatenate([np.asarray(p, dtype=np.float32).reshape(-1), gap]) for p in pieces])
    sf.write(f"{OUT}/{name}.wav", audio, rate)
    took = time.time() - started
    print(f"{name}: {len(audio) / rate:.1f} s of audio in {took:.1f} s", flush=True)


def omnivoice():
    from omnivoice import OmniVoice
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)
    for name, instruct in OMNI_VOICES.items():
        started = time.time()
        pieces = [model.generate(text=c, instruct=instruct, language="hu", num_step=32, speed=0.9)[0] for c in CHUNKS]
        save(name, pieces, 24000, started)
        if name == REF_VOICE:
            sf.write(f"{OUT}/reference.wav", np.asarray(pieces[1], dtype=np.float32).reshape(-1), 24000)


def omni_directed():
    """The Higgs direction script read by OmniVoice: its tags become pace and pause lengths,
    and the elderly deep voice reads a reference sentence for Higgs to clone."""
    import json
    import re
    from omnivoice import OmniVoice
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)
    voice = OMNI_VOICES["omni_deep_old"]
    ref_text = open(f"{ROOT}/higgs_reference.txt", encoding="utf-8").read().strip()
    ref = model.generate(text=ref_text, instruct=voice, language="hu", num_step=32, speed=0.95)[0]
    sf.write(f"{OUT}/higgs_reference.wav", np.asarray(ref, dtype=np.float32).reshape(-1), 24000)
    speeds = {"speed_very_slow": 0.75, "speed_slow": 0.85}
    started, pieces = time.time(), []
    for seg in json.load(open(f"{ROOT}/poem_scripts.json", encoding="utf-8"))["higgs_directed"]:
        speed = next((v for k, v in speeds.items() if k in seg["text"]), 0.9)
        for part in re.split(r"(<\|prosody:(?:long_)?pause\|>)", seg["text"]):
            if "long_pause" in part:
                pieces.append(np.zeros(int(24000 * 0.9), dtype=np.float32))
            elif "pause" in part:
                pieces.append(np.zeros(int(24000 * 0.35), dtype=np.float32))
            elif re.sub(r"<\|[^|]*\|>", "", part).strip():
                text = re.sub(r"<\|[^|]*\|>", "", part).strip()
                pieces.append(np.asarray(model.generate(text=text, instruct=voice, language="hu", num_step=32, speed=speed)[0], dtype=np.float32).reshape(-1))
        pieces.append(np.zeros(int(24000 * seg.get("after", 0.6)), dtype=np.float32))
    audio = np.concatenate(pieces)
    sf.write(f"{OUT}/omni_directed.wav", audio, 24000)
    print(f"omni_directed: {len(audio) / 24000:.1f} s of audio in {time.time() - started:.1f} s", flush=True)


def f5():
    # Clones the deep OmniVoice design, so no real person's voice is copied
    import torchaudio

    # As in the model card: torchaudio's loader is unreliable, so read references with soundfile
    def load(fp, **kw):
        d, sr = sf.read(str(fp), dtype="float32")
        return torch.from_numpy(d[np.newaxis, :] if d.ndim == 1 else d.T), sr
    torchaudio.load = load
    from f5_tts.api import F5TTS
    from huggingface_hub import hf_hub_download
    ckpt = hf_hub_download("Maxdorger29/f5-tts-hungarian", "model_last_final.safetensors")
    vocab = hf_hub_download("Maxdorger29/f5-tts-hungarian", "vocab.txt")
    tts = F5TTS(model="F5TTS_v1_Base", ckpt_file=ckpt, vocab_file=vocab, device="cuda", use_ema=True)
    started = time.time()
    pieces = []
    for c in CHUNKS:
        wav, out_rate, _ = tts.infer(ref_file=f"{OUT}/reference.wav", ref_text=CHUNKS[1], gen_text=c, speed=0.9)
        pieces.append(wav)
    save("f5_hungarian_deep", pieces, out_rate, started)


def xtts():
    from TTS.api import TTS
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    for voice in XTTS_VOICES:
        started = time.time()
        pieces = [model.tts(text=c, speaker=voice, language="hu", speed=0.95) for c in CHUNKS]
        save("xtts_" + voice.lower().replace(" ", "_"), pieces, 24000, started)


# The first stanza in this designed voice becomes the reference clip for the cloning models
REF_VOICE = "omni_deep_mid"

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    {"omnivoice": omnivoice, "omni_directed": omni_directed, "f5": f5, "xtts": xtts}[sys.argv[1]]()

#!/usr/bin/env python3
"""Hungarian STT benchmark: Piper-synthesised commands, clean / onset-cut / noisy, plus silence and noise clips.

Runs in the voice LXC with /opt/voice/venv (numpy, wyoming). Piper lives in a throwaway venv:
  python3 -m venv /opt/voice/stt-bench/venv && /opt/voice/stt-bench/venv/bin/pip install piper-tts
  voices hu_HU-anna-medium and hu_HU-imre-medium (rhasspy/piper-voices) in /opt/voice/stt-bench/voices

  bench_stt.py gen                                 # synthesise the clips (audio stays out of the repo)
  bench_stt.py wyoming 127.0.0.1:10300 --tag prod  # end to end, like Home Assistant does it
  bench_stt.py whisper --audio-ctx 400 --no-prompt --tag ac400   # whisper.cpp directly (ablations)
  bench_stt.py report                              # table of everything in results/

Synthetic TTS is cleaner and more regular than real speech through a kiosk microphone, so absolute
WERs are optimistic; the comparison between configurations is what counts.
"""
import argparse
import asyncio
import glob
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import wave

import numpy as np

HERE = os.environ.get("STT_BENCH_DIR", "/opt/voice/stt-bench")
AUDIO = os.path.join(HERE, "audio")
RESULTS = os.path.join(HERE, "results")
PIPER = os.path.join(HERE, "venv/bin/piper")
VOICES = ["hu_HU-anna-medium", "hu_HU-imre-medium"]
SR = 16000

# (what Piper is told to say, reference text, names that must come out right)
# English names are spelled the way a Hungarian says them, so the TTS pronounces them realistically.
COMMANDS = [
    ("kapcsold fel a dekor lámpát", "kapcsold fel a dekor lámpát", []),
    ("kapcsold le az összes lámpát", "kapcsold le az összes lámpát", []),
    ("kapcsold be a tévét", "kapcsold be a tévét", []),
    ("kapcsold ki a led lámpát", "kapcsold ki a led lámpát", []),
    ("kapcsold fel a konyhai lámpát", "kapcsold fel a konyhai lámpát", []),
    ("kapcsold be a porszívót", "kapcsold be a porszívót", []),
    ("hangosítsd fel a zenét", "hangosítsd fel a zenét", []),
    ("halkítsd le egy kicsit", "halkítsd le egy kicsit", []),
    ("állítsd meg a zenét", "állítsd meg a zenét", []),
    ("következő szám", "következő szám", []),
    ("milyen idő lesz holnap", "milyen idő lesz holnap", []),
    ("állíts be egy időzítőt tíz percre", "állíts be egy időzítőt tíz percre", []),
    ("játszd le a Daft Pank Get Laki című számát", "játszd le a Daft Punk Get Lucky című számát",
     ["Daft Punk", "Get Lucky"]),
    ("indítsd el a Csillagok között című filmet", "indítsd el a Csillagok között című filmet", ["Csillagok között"]),
    ("tegyél be valami szmúsz dzsesszt munkához", "tegyél be valami smooth jazzt munkához", ["smooth jazz"]),
    ("játssz egy kis Kóldplét", "játssz egy kis Coldplayt", ["Coldplay"]),
    ("indítsd el a Ponyvaregényt", "indítsd el a Ponyvaregényt", ["Ponyvaregény"]),
    ("játssz valamit Dzso Hiszaisitól", "játssz valamit Joe Hisaishitól", ["Joe Hisaishi"]),
    ("tedd be Poszt Malóntól a Szörkölsz című számot", "tedd be Post Malonetól a Circles című számot",
     ["Post Malone", "Circles"]),
    ("indítsd el a Fríren című sorozatot", "indítsd el a Frieren című sorozatot", ["Frieren"]),
    ("játszd le a Bárányok hallgatnak című filmet", "játszd le a Bárányok hallgatnak című filmet",
     ["Bárányok hallgatnak"]),
    ("játssz Bob Dilentől valamit", "játssz Bob Dylantől valamit", ["Bob Dylan"]),
    ("tegyél be egy kis lófáj zenét", "tegyél be egy kis lo-fi zenét", ["lo-fi"]),
    ("indítsd el a tévén a vájb módot", "indítsd el a tévén a vibe módot", ["vibe"]),
    ("játssz egy kis Kóldkatot", "játssz egy kis Coldcutot", ["Coldcut"]),
    ("játszd le a Fontéjnz Dí Szí legújabb albumát", "játszd le a Fontaines D.C. legújabb albumát",
     ["Fontaines D.C."]),
    ("indítsd el a Bodzsek Horszmen következő részét", "indítsd el a BoJack Horseman következő részét",
     ["BoJack Horseman"]),
    ("játssz Ludoviko Einauditól valamit", "játssz Ludovico Einauditól valamit", ["Ludovico Einaudi"]),
    ("tegyél be egy kis Metallikát", "tegyél be egy kis Metallicát", ["Metallica"]),
    ("indítsd el a Kászlvénia sorozatot", "indítsd el a Castlevania sorozatot", ["Castlevania"]),
]
LONG = [
    ("figyelj, azt szeretném, hogy kapcsold le az összes lámpát a nappaliban, aztán indítsd el a tévén a "
     "Ponyvaregény című filmet, és halkítsd le egy kicsit a zenét",
     "figyelj, azt szeretném, hogy kapcsold le az összes lámpát a nappaliban, aztán indítsd el a tévén a "
     "Ponyvaregény című filmet, és halkítsd le egy kicsit a zenét", ["Ponyvaregény"]),
    ("játssz nekem valami nyugodt zenét, például Ludoviko Einauditól vagy Dzso Hiszaisitól, mert most "
     "dolgozni szeretnék egy kicsit csendben, és utána kapcsold le a lámpát",
     "játssz nekem valami nyugodt zenét, például Ludovico Einauditól vagy Joe Hisaishitól, mert most "
     "dolgozni szeretnék egy kicsit csendben, és utána kapcsold le a lámpát", ["Ludovico Einaudi", "Joe Hisaishi"]),
    ("mondd meg, milyen idő lesz holnap reggel, és ha esni fog, akkor emlékeztess, hogy vigyek magammal "
     "esernyőt, mert múltkor is elfelejtettem",
     "mondd meg, milyen idő lesz holnap reggel, és ha esni fog, akkor emlékeztess, hogy vigyek magammal "
     "esernyőt, mert múltkor is elfelejtettem", []),
]
NUMBERS = {"10": "tíz", "50": "ötven", "5": "öt"}


# ---------------------------------------------------------------- audio
def read_wav(path):
    with wave.open(path) as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if rate != SR:
        data = np.interp(np.arange(0, len(data), rate / SR), np.arange(len(data)), data).astype(np.float32)
    return data


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


def pink(n, rng):
    spectrum = np.fft.rfft(rng.standard_normal(n))
    spectrum /= np.sqrt(np.maximum(np.arange(len(spectrum)), 1))
    noise = np.fft.irfft(spectrum, n)
    return (noise / (np.sqrt((noise ** 2).mean()) + 1e-12)).astype(np.float32)


def rms(x):
    return float(np.sqrt((x ** 2).mean() + 1e-12))


def onset(samples):
    frames = samples[:len(samples) // 160 * 160].reshape(-1, 160)
    level = np.sqrt((frames ** 2).mean(axis=1))
    loud = np.nonzero(level > level.max() * 0.1)[0]
    return int(loud[0]) * 160 if len(loud) else 0


def variant(samples, kind, seed):
    rng = np.random.default_rng(seed)
    if kind == "clean":
        return samples
    if kind == "cut150":  # the stream starts 150 ms into the first word, like a late satellite
        return samples[onset(samples) + int(0.15 * SR):]
    if kind == "noise":  # pink noise 10 dB below the speech level, over the whole clip
        start = onset(samples)
        speech = rms(samples[start:start + SR * 2])
        return samples + pink(len(samples), rng) * speech / (10 ** (10 / 20))
    raise ValueError(kind)


def negatives():
    """Audio that holds no command: the right answer is empty text."""
    rng = np.random.default_rng(7)
    out = {
        "silence": rng.standard_normal(SR * 2).astype(np.float32) * 10 ** (-70 / 20),
        "pink-45dB": pink(SR * 2, rng) * 10 ** (-45 / 20),
        "pink-30dB": pink(int(SR * 2.5), rng) * 10 ** (-30 / 20),
        "hum+fan": (np.sin(2 * np.pi * 50 * np.arange(SR * 3) / SR) * 0.01
                    + np.cumsum(rng.standard_normal(SR * 3)).astype(np.float32) * 1e-4),
        "clicks": np.zeros(SR * 2, dtype=np.float32),
        "breath": pink(int(SR * 1.5), rng) * 10 ** (-28 / 20) * np.hanning(int(SR * 1.5)).astype(np.float32),
    }
    out["hum+fan"] -= out["hum+fan"].mean()
    out["hum+fan"] = out["hum+fan"] / (np.abs(out["hum+fan"]).max() + 1e-9) * 0.03
    for k in range(4):
        out["clicks"][int((0.3 + 0.4 * k) * SR):int((0.3 + 0.4 * k) * SR) + 80] = 0.4 * rng.standard_normal(80)
    return {k: v.astype(np.float32) for k, v in out.items()}


def generate():
    os.makedirs(AUDIO, exist_ok=True)
    rng = np.random.default_rng(1)
    items = [("cmd", i, c) for i, c in enumerate(COMMANDS)] + [("long", i, c) for i, c in enumerate(LONG)]
    for voice in VOICES:
        model = os.path.join(HERE, "voices", voice + ".onnx")
        for kind, i, (say, _, _) in items:
            path = os.path.join(AUDIO, f"{kind}{i:02d}-{voice.split('-')[1]}.wav")
            if os.path.exists(path):
                continue
            raw = path + ".raw.wav"
            subprocess.run([PIPER, "-m", model, "-f", raw], input=say.encode(), check=True, capture_output=True)
            speech = read_wav(raw)
            os.remove(raw)
            speech = speech / (np.abs(speech).max() + 1e-9) * 0.5
            # what a satellite sends: a little room noise, ~0.3 s before and ~0.7 s after the speech
            clip = np.concatenate([np.zeros(int(0.3 * SR)), speech, np.zeros(int(0.7 * SR))]).astype(np.float32)
            clip += pink(len(clip), rng) * 10 ** (-60 / 20)
            write_wav(path, clip)
    for name, samples in negatives().items():
        write_wav(os.path.join(AUDIO, f"neg-{name}.wav"), samples)
    print(f"{len(glob.glob(os.path.join(AUDIO, '*.wav')))} clips in {AUDIO}")


def real_cases(folder):
    """Recordings of real speech: phrases.tsv lines "<file>\t<what was said>". Names = capitalised words
    after the first one. Personal audio: keep it out of the repo and delete the copy after the run."""
    out = []
    with open(os.path.join(folder, "phrases.tsv"), encoding="utf-8") as f:
        for index, line in enumerate(f):
            if "\t" not in line:
                continue
            name, ref = line.rstrip("\n").split("\t", 1)
            samples = read_wav(os.path.join(folder, name))
            names = [w.strip(".,!?") for w in ref.split()[1:] if w[:1].isupper()]
            for k, condition in enumerate(("clean", "cut150", "noise")):
                out.append((f"real-{name[:-4]}", condition, variant(samples, condition, index * 10 + k), ref, names))
    return out


def cases(real=None):
    """(id, condition, samples, reference, names)"""
    if real:
        return real_cases(real)
    out = []
    for path in sorted(glob.glob(os.path.join(AUDIO, "*.wav"))):
        name = os.path.basename(path)[:-4]
        samples = read_wav(path)
        if name.startswith("neg-"):
            out.append((name, "negative", samples, "", []))
            continue
        kind, index = name[:-5].rstrip("0123456789"), int(re.search(r"\d+", name).group())
        _, ref, names = (COMMANDS if kind == "cmd" else LONG)[index]
        if kind == "long":
            out.append((name, "long", samples, ref, names))
            continue
        for k, condition in enumerate(("clean", "cut150", "noise")):
            out.append((name, condition, variant(samples, condition, index * 10 + k), ref, names))
    return out


# ---------------------------------------------------------------- scoring
def words(text):
    text = text.lower().replace("-", "").replace("’", "'")
    text = re.sub(r"[^\w' ]+", " ", text)
    return [NUMBERS.get(w, w) for w in text.split()]


def fold(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if not unicodedata.combining(c)))


def edits(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


# ---------------------------------------------------------------- systems
async def wyoming_once(host, port, samples):
    from wyoming.asr import Transcribe, Transcript
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.client import AsyncTcpClient
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
    async with AsyncTcpClient(host, port) as client:
        start = time.perf_counter()
        await client.write_event(Transcribe(language="hu").event())
        await client.write_event(AudioStart(rate=SR, width=2, channels=1).event())
        for k in range(0, len(pcm), 2048):
            await client.write_event(AudioChunk(rate=SR, width=2, channels=1, audio=pcm[k:k + 2048]).event())
        await client.write_event(AudioStop().event())
        while True:
            event = await client.read_event()
            if event is None:
                raise ConnectionError("closed")
            if Transcript.is_type(event.type):
                return Transcript.from_event(event).text, time.perf_counter() - start


def run(args):
    if args.system == "wyoming":
        host, port = args.target.split(":")
        transcribe = lambda s: asyncio.run(wyoming_once(host, int(port), s))  # noqa: E731
    else:
        sys.path.insert(0, args.server_dir)
        import stt_server
        if args.ctx_pad is not None:
            stt_server.CTX_PAD = args.ctx_pad

        def transcribe(samples):
            start = time.perf_counter()
            try:
                text, _ = stt_server.whisper(samples, use_prompt=not args.no_prompt, audio_ctx=args.audio_ctx,
                                             url=args.target)
            except Exception as err:
                text = f"<error {err!r}>"
            return text, time.perf_counter() - start
    transcribe(np.zeros(SR, dtype=np.float32))  # warm-up
    rows = []
    for case_id, condition, samples, ref, names in cases(args.real):
        if args.only and condition not in args.only.split(","):
            continue
        text, seconds = transcribe(samples)
        rows.append({"id": case_id, "condition": condition, "ref": ref, "hyp": text, "names": names,
                     "seconds": round(seconds, 3), "audio_s": round(len(samples) / SR, 2)})
        print(f"{seconds * 1000:6.0f} ms {condition:8s} {case_id:14s} {text}", flush=True)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, f"{args.tag}.json"), "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "system": args.system, "target": args.target, "rows": rows}, f,
                  ensure_ascii=False, indent=1)
    summary(args.tag, rows)


def summary(tag, rows):
    print(f"\n{tag}")
    lines = []
    for condition in ("clean", "cut150", "noise", "long", "negative"):
        sel = [r for r in rows if r["condition"] == condition]
        if not sel:
            continue
        lat = np.array([r["seconds"] for r in sel]) * 1000
        if condition == "negative":
            bad = [r["hyp"] for r in sel if r["hyp"].strip()]
            lines.append(f"| {tag} | {condition} | {len(sel)} | {len(bad)} non-empty | | {np.median(lat):.0f} | "
                         f"{lat.max():.0f} |")
            continue
        errors = sum(edits(words(r["ref"]), words(r["hyp"])) for r in sel)
        total = sum(len(words(r["ref"])) for r in sel)
        exact = sum(words(r["ref"]) == words(r["hyp"]) for r in sel)
        hits = [fold(n) in fold(r["hyp"]) for r in sel for n in r["names"]]
        lines.append(f"| {tag} | {condition} | {len(sel)} | WER {100 * errors / total:.1f}% (exact {exact}/{len(sel)}) "
                     f"| names {sum(hits)}/{len(hits)} | {np.median(lat):.0f} | {lat.max():.0f} |")
    print("| system | set | n | WER | names | p50 ms | max ms |\n|---|---|---|---|---|---|---|")
    print("\n".join(lines))
    return lines


def report(_args):
    print("| system | set | n | WER | names | p50 ms | max ms |\n|---|---|---|---|---|---|---|")
    for path in sorted(glob.glob(os.path.join(RESULTS, "*.json")), key=os.path.getmtime):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            lines = summary(data["tag"], data["rows"])
        print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen")
    sub.add_parser("report")
    for name in ("wyoming", "whisper"):
        p = sub.add_parser(name)
        p.add_argument("target", nargs="?", default="127.0.0.1:10300" if name == "wyoming"
                       else "http://127.0.0.1:8090/inference")
        p.add_argument("--tag", required=True)
        p.add_argument("--only", help="comma list of sets: clean,cut150,noise,long,negative")
        p.add_argument("--audio-ctx", default="auto", help="auto, 0 (full) or a number")
        p.add_argument("--no-prompt", action="store_true")
        p.add_argument("--ctx-pad", type=int, help="encoder frames after the clip with --audio-ctx auto")
        p.add_argument("--server-dir", default="/opt/voice")
        p.add_argument("--real", help="folder with real recordings and phrases.tsv instead of the TTS set")
    args = parser.parse_args()
    if args.cmd == "gen":
        generate()
    elif args.cmd == "report":
        report(args)
    else:
        args.system = args.cmd
        run(args)


if __name__ == "__main__":
    main()

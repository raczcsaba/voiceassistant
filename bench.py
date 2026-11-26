"""Benchmark STT and LLM tool-calling latency/accuracy on the smart-home test set.

  python bench.py                         # English, everything available (local + cloud with keys set)
  python bench.py --stt moonshine-base --llm functiongemma-270m,granite4-350m
  python bench.py --lang hu               # Hungarian profile
  python bench.py --audio tts             # use synthetic audio instead of your recordings
  python bench.py --list                  # show backend names

Phase 1: each STT transcribes every clip (`--repeats` times, median latency) -> WER.
Phase 2: each LLM gets (a) the reference text -> pure LLM accuracy/latency and
         (b) every STT's transcripts -> end-to-end accuracy, latency = STT + LLM per clip.
"""
import argparse
import datetime
import json
import pathlib
import statistics
import time

import jiwer
import requests
import soundfile as sf

from va import llm as llm_mod
from va import stt as stt_mod
from va.common import PROFILES, norm_text, score_call


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def ms(x):
    return f"{x * 1000:.0f}"


def timed(fn, *a):
    t = time.perf_counter()
    r = fn(*a)
    return r, time.perf_counter() - t


def ollama_mem(model):
    try:
        for m in requests.get("http://localhost:11434/api/ps", timeout=5).json().get("models", []):
            if m["name"] == model or m["model"] == model:
                return m["size"] / 1e9
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=list(PROFILES))
    ap.add_argument("--stt", help="comma list, 'none' to skip")
    ap.add_argument("--llm", help="comma list, 'none' to skip")
    ap.add_argument("--audio", choices=["rec", "tts"], help="default: rec if recorded, else tts")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    prof = PROFILES[a.lang]
    testset = prof["testset"]
    stts, llms = stt_mod.available(a.lang, prof["keyterms"]), llm_mod.available(prof["system"])
    if a.list:
        print("STT:", ", ".join(stts))
        print("LLM:", ", ".join(llms))
        return

    def pick(arg, avail):
        if arg == "none":
            return []
        names = arg.split(",") if arg else list(avail)
        bad = [n for n in names if n not in avail]
        if bad:
            raise SystemExit(f"unknown/unavailable backend(s): {bad}; available: {list(avail)}")
        return names

    stt_names, llm_names = pick(a.stt, stts), pick(a.llm, llms)
    base = pathlib.Path("audio") / a.lang
    audio_dir = base / (a.audio or ("rec" if any((base / "rec").glob("*.wav")) else "tts"))
    clips = []
    for tid, text, n, args in testset:
        p = audio_dir / f"{tid}.wav"
        if p.exists():
            audio, sr = sf.read(str(p), dtype="float32")
            assert sr == 16000, f"{p}: expected 16 kHz"
            clips.append((tid, text, n, args, audio))
    if stt_names and not clips:
        raise SystemExit(f"no clips in {audio_dir}; run make_audio.py --lang {a.lang} or record.py first")
    if clips:
        print(f"audio: {audio_dir} ({len(clips)} clips, avg {statistics.mean(len(c[-1]) / 16000 for c in clips):.1f}s)")

    res = {"lang": a.lang, "audio": str(audio_dir), "stt": {}, "llm": {}}

    # ---------- Phase 1: STT ----------
    for name in stt_names:
        be = stts[name]()
        print(f"\n[STT] {be.name}: loading...", flush=True)
        _, t_load = timed(be.load)
        lat, hyps = {}, {}
        for tid, _text, *_, audio in clips:
            times = []
            for _ in range(a.repeats):
                hyp, t = timed(be.transcribe, audio)
                times.append(t)
            lat[tid], hyps[tid] = statistics.median(times), hyp
            print(f"  {tid} {ms(lat[tid]):>5}ms  {hyp}", flush=True)
        refs = [norm_text(t) for tid, t, *_ in clips]
        wer = jiwer.wer(refs, [norm_text(hyps[tid]) or "-" for tid, *_ in clips])
        res["stt"][name] = {"backend": be.name, "load_s": t_load, "lat": lat, "hyp": hyps, "wer": wer}
        be.unload()

    # ---------- Phase 2: LLM ----------
    for name in llm_names:
        be = llms[name]()
        print(f"\n[LLM] {be.name}: loading/warming...", flush=True)
        try:
            _, t_load = timed(be.load)
        except Exception as e:
            print(f"  FAILED to load: {e}")
            be.unload()
            continue
        out = {"backend": be.name, "load_s": t_load, "mem_gb": ollama_mem(getattr(be, "model", "")), "ref": {}, "e2e": {}}
        for tid, text, exp_n, exp_a in testset:
            times = []
            for _ in range(a.repeats):
                r, t = timed(be.run, text)
                times.append(t)
            ok = score_call(r["calls"], exp_n, exp_a)
            out["ref"][tid] = {"lat": statistics.median(times), "ok": ok, "calls": r["calls"], "text": r["text"]}
            print(f"  {tid} {ms(out['ref'][tid]['lat']):>5}ms {'OK ' if ok else 'BAD'} {r['calls'] or r['text'][:80]}", flush=True)
        for sname, s in res["stt"].items():
            e = {}
            for tid, _text, exp_n, exp_a, _ in clips:
                r, t = timed(be.run, s["hyp"][tid])
                e[tid] = {"llm": t, "stt": s["lat"][tid], "ok": score_call(r["calls"], exp_n, exp_a)}
            out["e2e"][sname] = e
            print(f"  e2e with {sname}: {sum(v['ok'] for v in e.values())}/{len(e)} correct", flush=True)
        res["llm"][name] = out
        be.unload()

    report(res)
    pathlib.Path("results").mkdir(exist_ok=True)
    f = pathlib.Path("results") / f"bench-{a.lang}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    print(f"\nraw results: {f}")


def report(res):
    if res["stt"]:
        print("\n## STT  (latency per clip, ms)\n")
        print("| backend | median | p90 | max | WER | load s |")
        print("|---|---|---|---|---|---|")
        for n, s in sorted(res["stt"].items(), key=lambda kv: statistics.median(kv[1]["lat"].values())):
            l = list(s["lat"].values())
            print(f"| {n} | {ms(statistics.median(l))} | {ms(pct(l, 90))} | {ms(max(l))} | {s['wer']:.1%} | {s['load_s']:.1f} |")
    if res["llm"]:
        print("\n## LLM tool calling on reference text  (ms)\n")
        print("| backend | median | p90 | max | correct | RAM GB |")
        print("|---|---|---|---|---|---|")
        for n, o in sorted(res["llm"].items(), key=lambda kv: statistics.median(v["lat"] for v in kv[1]["ref"].values())):
            l = [v["lat"] for v in o["ref"].values()]
            c = sum(v["ok"] for v in o["ref"].values())
            mem = f"{o['mem_gb']:.2f}" if o.get("mem_gb") else "-"
            print(f"| {n} | {ms(statistics.median(l))} | {ms(pct(l, 90))} | {ms(max(l))} | {c}/{len(l)} | {mem} |")
    pairs = [(sn, ln, e) for ln, o in res["llm"].items() for sn, e in o["e2e"].items()]
    if pairs:
        print("\n## End-to-end STT + LLM  (ms, from end of speech to tool call; no VAD/TTS)\n")
        print("| STT | LLM | median | p90 | max | correct | under 1 s |")
        print("|---|---|---|---|---|---|---|")
        rows = []
        for sn, ln, e in pairs:
            tot = [v["stt"] + v["llm"] for v in e.values()]
            rows.append((statistics.median(tot), sn, ln, tot, sum(v["ok"] for v in e.values())))
        for med, sn, ln, tot, c in sorted(rows):
            under = sum(t < 1.0 for t in tot)
            print(f"| {sn} | {ln} | {ms(med)} | {ms(pct(tot, 90))} | {ms(max(tot))} | {c}/{len(tot)} | {under}/{len(tot)} |")


if __name__ == "__main__":
    main()

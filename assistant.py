"""Live voice assistant PoC: mic -> VAD -> STT -> command parser -> home -> (optional) TTS.

  python assistant.py                          # hands-free (Silero VAD), fastest tested stack
  python assistant.py --ptt                    # push-to-talk instead of VAD
  python assistant.py --tts                    # spoken confirmations (pre-rendered Piper voice)
  python assistant.py --ha                     # real Home Assistant (HA_URL, HA_TOKEN, home_entities.json)
  python assistant.py --stt moonshine-base --llm mlx-qwen3.5-0.8b-8bit --silence-ms 250
"""
import argparse
import time

from va import llm as llm_mod
from va import stt as stt_mod
from va.common import PROFILES, REPLY, spoken_reply
from va.home import HomeAssistant, MockHome

ap = argparse.ArgumentParser()
ap.add_argument("--stt", default="parakeet-110m")
ap.add_argument("--llm", default=llm_mod.DEFAULT)
ap.add_argument("--ptt", action="store_true", help="push-to-talk instead of voice activity detection")
ap.add_argument("--silence-ms", type=int, default=300, help="VAD: silence that ends an utterance")
ap.add_argument("--tts", action="store_true")
ap.add_argument("--ha", action="store_true", help="use Home Assistant instead of the mock")
a = ap.parse_args()
prof = PROFILES["en"]

t = time.perf_counter()
stt = stt_mod.available("en", prof["keyterms"])[a.stt]()
nlu = llm_mod.available(prof["system"])[a.llm]()
stt.load()
nlu.load()
try:  # keep model weights resident: macOS must not page them out while we wait for speech
    import mlx.core as mx
    mx.set_wired_limit(int(1.5e9))
except Exception:
    pass
home = HomeAssistant() if a.ha else MockHome()
tts = None
if a.tts:
    from va.tts import PiperTTS
    tts = PiperTTS(phrases=list(REPLY.values()))

from va.listen import Listener  # noqa: E402

mic = Listener(silence_ms=a.silence_ms)
print(f"ready in {time.perf_counter() - t:.1f}s: {stt.name} + {nlu.name}"
      + ("" if a.ptt else f" | listening (VAD, {a.silence_ms} ms end-of-speech)") + " | Ctrl+C to quit")

try:
    while True:
        mic.flush()
        audio, t0 = mic.push_to_talk() if a.ptt else mic.next_utterance()
        text = stt.transcribe(audio)
        t1 = time.perf_counter()
        r = nlu.run(text) if text else {"calls": [], "text": ""}
        t2 = time.perf_counter()
        say = ""  # not a command (chatter, "hmm", unknown device, low confidence): stay silent
        outs = []
        for c in r["calls"]:
            try:
                out = home.execute(c)
            except Exception as e:  # HA down / unknown entity: report it, keep listening
                out = {"ok": False, "error": str(e)}
            outs.append(out)
            say = spoken_reply(c, out)
        t3 = time.perf_counter()
        if tts and say:
            mic.mute(tts.say(say) + 0.3)  # don't hear ourselves
        t4 = time.perf_counter()
        print(f"\n  heard: {text!r}")
        if r["calls"]:
            print(f"  calls: {r['calls']}  {outs}")
        elif r.get("rejected"):
            print(f"  ignored (confidence {r['conf']:.2f} too low for {r['rejected']})")
        else:
            print("  ignored (not a command)")
        print(f"  STT {(t1 - t0) * 1000:.0f} ms | NLU {(t2 - t1) * 1000:.0f} ms | home {(t3 - t2) * 1000:.0f} ms"
              + (f" | TTS start {(t4 - t3) * 1000:.0f} ms" if tts else "")
              + f" | total {(t4 - t0) * 1000:.0f} ms after end-of-speech"
              + ("" if a.ptt else f" (+{a.silence_ms} ms VAD wait)"))
except KeyboardInterrupt:
    print("\nbye")

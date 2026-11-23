"""Record your own voice for every test sentence -> audio/<lang>/rec/*.wav (16 kHz mono).

  python record.py                # English
  python record.py --lang hu t03  # Hungarian, only t03

Press Enter to start, Enter again to stop. Type 's' + Enter to skip a sentence, 'r' to redo the last one.
"""
import argparse
import pathlib

from va.audio import record_until_enter, save_wav
from va.common import PROFILES

ap = argparse.ArgumentParser()
ap.add_argument("--lang", default="en", choices=list(PROFILES))
ap.add_argument("only", nargs="*", help="test ids to record (default: all)")
a = ap.parse_args()
testset = PROFILES[a.lang]["testset"]

out = pathlib.Path("audio") / a.lang / "rec"
out.mkdir(parents=True, exist_ok=True)
i = 0
while i < len(testset):
    tid, text, *_ = testset[i]
    if a.only and tid not in a.only:
        i += 1
        continue
    cmd = input(f"\n[{tid}] Say: \"{text}\"\n  Enter = start, s = skip > ").strip().lower()
    if cmd == "s":
        i += 1
        continue
    audio = record_until_enter()
    save_wav(out / f"{tid}.wav", audio)
    print(f"  saved {len(audio) / 16000:.1f}s")
    if input("  ok? (Enter = next, r = redo) > ").strip().lower() != "r":
        i += 1

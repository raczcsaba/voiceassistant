"""Generate synthetic test utterances with a macOS voice -> audio/<lang>/tts/*.wav (16 kHz mono).

  python make_audio.py            # English (Samantha)
  python make_audio.py --lang hu  # Hungarian (Tünde)

Synthetic speech is clean, so WER will look better than with a real voice. Use record.py for real numbers.
"""
import argparse
import pathlib
import subprocess

from va.common import PROFILES

ap = argparse.ArgumentParser()
ap.add_argument("--lang", default="en", choices=list(PROFILES))
a = ap.parse_args()
prof = PROFILES[a.lang]

out = pathlib.Path("audio") / a.lang / "tts"
out.mkdir(parents=True, exist_ok=True)
for tid, text, *_ in prof["testset"]:
    p = out / f"{tid}.wav"
    subprocess.run(["say", "-v", prof["say_voice"], "--data-format=LEI16@16000", "-o", str(p), text], check=True)
    print(p, text)

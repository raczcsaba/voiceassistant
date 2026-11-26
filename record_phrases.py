#!/usr/bin/env python3
"""Read Hungarian commands aloud to build a test set in your own voice. Nothing is executed."""
import os
import wave

import numpy as np

from va.listen import SR, Listener

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
PHRASES = """Kapcsold fel a LED lámpát.
Kapcsold le a dekor lámpát.
Kapcsolj le mindent.
Állítsd a hangulatvilágítást negyven százalékra.
Kapcsold be az erősítőt.
Kapcsold ki a tévét.
Indítsd el a Ponyvaregényt.
Indítsd el a Pulp Fiction filmet.
Tedd be a Shreket.
Indítsd el a Verdákat.
Nézzük meg a Forrest Gumpot.
Indítsd el a Bárányok hallgatnak filmet.
Indíts egy kis Mozartot.
Játssz klasszikus zenét.
Játssz valami Beatles számot.
Játszd le a Hey Jude-ot.
Tegyél be valami Massive Attacket a Pin.
Csak a Teardrop című számot játszd a Massive Attacktől.
Következő szám.
Állítsd meg a zenét.
Folytasd a lejátszást.
Hangosítsd fel.
Halkítsd le.
Tedd hangosabbra a zenét.""".split("\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    listener = Listener(silence_ms=300)
    print("Enter starts, Enter stops, for each sentence. Speak naturally, as you would to the assistant.\n")
    with open(os.path.join(OUT, "phrases.tsv"), "a", encoding="utf-8") as index:
        for number, phrase in enumerate(PHRASES, 1):
            print(f"[{number}/{len(PHRASES)}]  {phrase}")
            audio, _ = listener.push_to_talk()
            name = f"{number:02d}.wav"
            with wave.open(os.path.join(OUT, name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
            index.write(f"{name}\t{phrase}\n")
            index.flush()
    print("\nDone, thank you. You can close this window.")


if __name__ == "__main__":
    main()

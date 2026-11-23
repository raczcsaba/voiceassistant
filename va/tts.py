"""Optional spoken replies. Fixed confirmations are synthesized once at startup and played from RAM."""
import pathlib
import subprocess
import sys

VOICE_DIR = pathlib.Path("voices")


class PiperTTS:
    def __init__(self, voice="en_US-lessac-low", phrases=()):
        import sounddevice as sd
        from piper import PiperVoice

        self.sd = sd
        model = VOICE_DIR / f"{voice}.onnx"
        if not model.exists():
            subprocess.run([sys.executable, "-m", "piper.download_voices", "--download-dir", str(VOICE_DIR), voice], check=True)
        self.v = PiperVoice.load(model)
        self.cache = {}
        for p in phrases:
            self._render(p)

    def _render(self, text):
        import numpy as np
        if text not in self.cache:
            chunks = list(self.v.synthesize(text))
            self.cache[text] = (np.concatenate([c.audio_float_array for c in chunks]), chunks[0].sample_rate)
        return self.cache[text]

    def say(self, text):
        """Start playback (non-blocking). Returns the clip length in seconds."""
        audio, sr = self._render(text)
        self.sd.play(audio, sr)
        return len(audio) / sr

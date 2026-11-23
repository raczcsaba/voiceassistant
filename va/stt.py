"""STT backends. Each exposes .name, .load(), .transcribe(audio) -> str, .unload().

`audio` is a float32 numpy array, 16 kHz mono, already in memory (no temp files, no ffmpeg).
"""
import gc
import io
import os

import numpy as np

SR = 16000


class Moonshine:
    """Moonshine (moonshine-voice, ONNX on CPU). Built for low-latency English voice commands."""

    def __init__(self, arch="base", lang="en", keyterms=None):
        self.arch, self.lang, self.keyterms = arch, lang, keyterms
        self.name = f"moonshine:{arch}"

    def load(self):
        from moonshine_voice import Transcriber, get_model_for_language, string_to_model_arch
        path, arch = get_model_for_language(self.lang, string_to_model_arch(self.arch))
        self._t = Transcriber(path, arch)
        if self.keyterms and "streaming" in self.arch:  # biasing only exists for streaming archs
            self._t.set_keyterms(self.keyterms)
        self.transcribe(np.zeros(SR, dtype=np.float32))  # warm up

    def transcribe(self, audio):
        tr = self._t.transcribe_without_streaming(audio.astype(np.float32).tolist(), SR)
        return " ".join(l.text.strip() for l in tr.lines).strip()

    def unload(self):
        self._t.close()
        self._t = None
        gc.collect()


class Parakeet:
    """NVIDIA Parakeet on MLX. v2 / 110m = English, v3 = 25 EU languages incl. Hungarian."""

    def __init__(self, repo):
        self.repo, self.name = repo, f"parakeet:{repo.split('/')[-1]}"

    def load(self):
        from parakeet_mlx import from_pretrained
        self._m = from_pretrained(self.repo)
        self.transcribe(np.zeros(SR, dtype=np.float32))  # compile Metal kernels

    def transcribe(self, audio):
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel
        mel = get_logmel(mx.array(audio.astype(np.float32)), self._m.preprocessor_config)
        return self._m.generate(mel)[0].text.strip()

    def unload(self):
        self._m = None
        _free()


class MlxWhisper:
    def __init__(self, repo, lang="en", prompt=None):
        self.repo, self.lang, self.prompt = repo, lang, prompt
        self.name = f"mlx-whisper:{repo.split('/')[-1]}"

    def load(self):
        import mlx_whisper
        self._m = mlx_whisper
        self.transcribe(np.zeros(SR, dtype=np.float32))  # download + warm up

    def transcribe(self, audio):
        r = self._m.transcribe(audio.astype(np.float32), path_or_hf_repo=self.repo, language=self.lang,
                               temperature=0.0, condition_on_previous_text=False, initial_prompt=self.prompt)
        return r["text"].strip()

    def unload(self):
        from mlx_whisper.transcribe import ModelHolder
        ModelHolder.model = None
        _free()


class GroqWhisper:
    def __init__(self, lang="en", prompt=None, model="whisper-large-v3-turbo"):
        self.lang, self.prompt, self.model, self.name = lang, prompt, model, f"groq:{model}"

    def load(self):
        from openai import OpenAI
        self._c = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])

    def transcribe(self, audio):
        r = self._c.audio.transcriptions.create(model=self.model, file=("a.wav", _wav_bytes(audio)),
                                                language=self.lang, prompt=self.prompt, temperature=0.0)
        return r.text.strip()

    def unload(self):
        pass


class Deepgram:
    """Pre-recorded endpoint (upper bound). Real-time streaming would hide most of this latency."""

    def __init__(self, lang="en", model="nova-3"):
        self.lang, self.model, self.name = lang, model, f"deepgram:{model}"

    def load(self):
        import requests
        self._s = requests.Session()
        self._key = os.environ["DEEPGRAM_API_KEY"]

    def transcribe(self, audio):
        r = self._s.post("https://api.deepgram.com/v1/listen",
                         params={"model": self.model, "language": self.lang, "smart_format": "true"},
                         headers={"Authorization": f"Token {self._key}", "Content-Type": "audio/wav"},
                         data=_wav_bytes(audio), timeout=30)
        r.raise_for_status()
        return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()

    def unload(self):
        pass


def _wav_bytes(audio):
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _free():
    gc.collect()
    try:
        import mlx.core as mx
        mx.clear_cache()
    except Exception:
        pass


def available(lang="en", keyterms=None):
    """Backend factories keyed by short name. Cloud ones are only offered when their key is set."""
    prompt = ", ".join(keyterms or [])
    if lang == "en":
        b = {
            "moonshine-tiny": lambda: Moonshine("tiny", keyterms=keyterms),
            "moonshine-base": lambda: Moonshine("base", keyterms=keyterms),
            "moonshine-tiny-streaming": lambda: Moonshine("tiny-streaming", keyterms=keyterms),
            "moonshine-medium-streaming": lambda: Moonshine("medium-streaming", keyterms=keyterms),
            "moonshine-small-streaming": lambda: Moonshine("small-streaming", keyterms=keyterms),
            "parakeet-110m": lambda: Parakeet("mlx-community/parakeet-tdt_ctc-110m"),
            "parakeet-v2": lambda: Parakeet("mlx-community/parakeet-tdt-0.6b-v2"),
            "whisper-tiny.en": lambda: MlxWhisper("mlx-community/whisper-tiny.en-mlx", prompt=prompt),
            "whisper-base.en": lambda: MlxWhisper("mlx-community/whisper-base.en-mlx", prompt=prompt),
        }
    else:
        b = {
            "parakeet-v3": lambda: Parakeet("mlx-community/parakeet-tdt-0.6b-v3"),
            "whisper-turbo": lambda: MlxWhisper("mlx-community/whisper-large-v3-turbo", lang=lang, prompt=prompt),
        }
    if os.environ.get("GROQ_API_KEY"):
        b["groq-whisper"] = lambda: GroqWhisper(lang=lang, prompt=prompt)
    if os.environ.get("DEEPGRAM_API_KEY"):
        b["deepgram-nova3"] = lambda: Deepgram(lang=lang)
    return b

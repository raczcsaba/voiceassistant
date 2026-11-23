"""Always-open microphone + Silero VAD endpointing (hands-free), or push-to-talk.

The mic stream is opened once and never closed, so there is no device-open delay per command. A short pre-roll
buffer keeps the first syllable that arrives before the VAD fires. The utterance ends after `silence_ms` of
non-speech; that wait is the only latency VAD adds.
"""
import collections
import queue
import time

import numpy as np

SR = 16000
FRAME = 512  # 32 ms at 16 kHz (Silero v5 frame size)


class SileroVAD:
    def __init__(self, path="models/silero_vad.onnx"):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = opts.intra_op_num_threads = 1
        self.sess = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.ctx = np.zeros(64, dtype=np.float32)  # v5 expects 64 samples of left context

    def __call__(self, frame):
        x = np.concatenate([self.ctx, frame])[None, :].astype(np.float32)
        out, self.state = self.sess.run(None, {"input": x, "state": self.state, "sr": np.array(SR, dtype=np.int64)})
        self.ctx = frame[-64:]
        return float(out[0, 0])


class Listener:
    def __init__(self, silence_ms=300, preroll_ms=320, start_thresh=0.5, end_thresh=0.35, min_speech_ms=200):
        import sounddevice as sd

        self.vad = SileroVAD()
        self.silence_frames = max(1, silence_ms // 32)
        self.preroll = collections.deque(maxlen=max(1, preroll_ms // 32))
        self.start_thresh, self.end_thresh = start_thresh, end_thresh
        self.min_speech_frames = max(1, min_speech_ms // 32)
        self.mute_until = 0.0
        self.q = queue.Queue()
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME,
                                     callback=lambda d, *_: self.q.put(d[:, 0].copy()))
        self.stream.start()

    def mute(self, seconds):
        """Ignore the mic for a while (e.g. while our own TTS is playing)."""
        self.mute_until = max(self.mute_until, time.perf_counter() + seconds)

    def _frames(self):
        while True:
            f = self.q.get()
            if time.perf_counter() < self.mute_until:
                continue
            yield f

    def flush(self):
        """Drop audio captured while we were busy (processing / speaking)."""
        while not self.q.empty():
            self.q.get_nowait()

    def next_utterance(self):
        """Block until one utterance is spoken. Returns (audio, t_endpoint)."""
        self.vad.reset()
        self.preroll.clear()
        speech, voiced, silent, started = [], 0, 0, False
        for f in self._frames():
            p = self.vad(f)
            if not started:
                self.preroll.append(f)
                voiced = voiced + 1 if p > self.start_thresh else 0
                if voiced >= 2:
                    started, speech = True, list(self.preroll)
                    self.preroll.clear()
                continue
            speech.append(f)
            if p < self.end_thresh:
                silent += 1
                if silent >= self.silence_frames:
                    if len(speech) - silent >= self.min_speech_frames:
                        keep = len(speech) - silent + 3  # keep ~100 ms of tail
                        return np.concatenate(speech[:keep]), time.perf_counter()
                    speech, voiced, silent, started = [], 0, 0, False  # too short: a click/cough
            else:
                silent = 0

    def push_to_talk(self):
        """Enter = start, Enter = stop. Returns (audio, t_endpoint)."""
        input("\nEnter = speak > ")
        while not self.q.empty():
            self.q.get_nowait()
        input("  ● recording... Enter = stop")
        t = time.perf_counter()
        chunks = []
        while not self.q.empty():
            chunks.append(self.q.get_nowait())
        return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)), t

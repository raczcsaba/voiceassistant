"""Endpointing logic of va/listen.py Listener, with a scripted VAD instead of a microphone + Silero."""
import collections
import queue

import numpy as np
import pytest

from va.listen import FRAME, Listener


class FiniteQueue(queue.Queue):
    """Raises instead of blocking once the scripted audio is used up."""

    def get(self, block=True, timeout=None):
        if self.empty():
            raise EOFError("no more audio")
        return super().get(block=False)


class ScriptedVAD:
    def __init__(self, probs):
        self.probs = iter(probs)

    def reset(self):
        pass

    def __call__(self, frame):
        return next(self.probs)


def listener(probs, silence_ms=96, preroll_ms=96, min_speech_ms=96):
    """Listener without the sound device: frame i is filled with the value i, so we can see which were kept."""
    li = Listener.__new__(Listener)
    li.vad = ScriptedVAD(probs)
    li.silence_frames = silence_ms // 32
    li.preroll = collections.deque(maxlen=preroll_ms // 32)
    li.start_thresh, li.end_thresh = 0.5, 0.35
    li.min_speech_frames = min_speech_ms // 32
    li.mute_until = 0.0
    li.q = FiniteQueue()
    for i in range(len(probs)):
        li.q.put(np.full(FRAME, i, dtype=np.float32))
    return li


def frames_of(audio):
    return [int(v) for v in audio[::FRAME]]


def test_utterance_with_preroll_and_tail():
    probs = [0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]
    audio, _ = listener(probs).next_utterance()
    # 3-frame pre-roll (frames 2-4, incl. the two that triggered), speech 5-7, then silence 8-10 ends it;
    # 3 frames of tail are kept
    assert frames_of(audio) == [2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_needs_two_voiced_frames_to_start():
    probs = [0.9, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1]
    with pytest.raises(EOFError):  # audio runs out: nothing was detected
        listener(probs).next_utterance()


def test_short_click_is_dropped():
    # 2 voiced frames + 1 frame of tail is below min_speech (3 frames): dropped, then a real utterance follows
    probs = [0.9, 0.9, 0.1, 0.1, 0.1] + [0.1, 0.9, 0.9, 0.9, 0.9, 0.2, 0.2, 0.2]
    audio, _ = listener(probs).next_utterance()
    assert frames_of(audio)[0] >= 5


def test_pause_shorter_than_silence_does_not_end():
    probs = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.9, 0.9, 0.1, 0.1, 0.1]
    audio, _ = listener(probs).next_utterance()
    assert frames_of(audio) == list(range(11))


def test_muted_frames_are_ignored():
    li = listener([0.9] * 3)
    li.mute(60)
    with pytest.raises(EOFError):
        next(li._frames())


def test_flush_drops_buffered_audio():
    li = listener([0.9] * 3)
    li.flush()
    assert li.q.empty()

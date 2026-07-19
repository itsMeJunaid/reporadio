import numpy as np

from reporadio.voice.vad import CHUNK, Mic


class ScriptedVAD:
    """Deterministic VAD: returns the scripted probability sequence."""

    def __init__(self, probs):
        self._probs = list(probs)

    def prob(self, chunk):
        return self._probs.pop(0) if self._probs else 0.0

    def reset(self):
        pass


def chunk(value=0.0):
    return np.full(CHUNK, value, dtype=np.float32)


def make_mic(probs, fired):
    return Mic(
        on_speech=lambda: fired.append(1),
        start_ms=300, end_ms=800,  # ≈10 chunks start · ≈25 chunks end
        vad=ScriptedVAD(probs),
    )


def test_short_blip_does_not_fire():
    fired = []
    mic = make_mic([0.9] * 4 + [0.0] * 20, fired)
    for _ in range(24):
        mic.process_chunk(chunk())
    assert fired == []
    assert mic.utterance(timeout=0.01) is None


def test_speech_fires_once_and_utterance_is_captured():
    fired = []
    speech, tail = 14, 30
    mic = make_mic([0.9] * speech + [0.0] * tail, fired)
    for _ in range(speech + tail):
        mic.process_chunk(chunk(0.5))
    assert fired == [1]  # fired exactly once, ≥300ms of speech
    utt = mic.utterance(timeout=0.5)
    assert utt is not None
    assert len(utt) >= speech * CHUNK  # preroll + speech + closing silence


def test_second_utterance_after_reset():
    fired = []
    round_ = [0.9] * 12 + [0.0] * 26
    mic = make_mic(round_ + round_, fired)
    for _ in range(len(round_) * 2):
        mic.process_chunk(chunk())
    assert fired == [1, 1]
    assert mic.utterance(timeout=0.5) is not None
    assert mic.utterance(timeout=0.5) is not None

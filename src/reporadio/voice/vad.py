"""Silero VAD via onnxruntime (no torch) + always-open mic with barge-in detection."""

from __future__ import annotations

import queue
import threading
from collections import deque
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

from reporadio.config import get_settings

SAMPLE_RATE = 16000
CHUNK = 512  # 32ms per chunk at 16kHz
_CONTEXT = 64  # silero v5 wants the previous 64 samples prepended
_CHUNK_MS = CHUNK * 1000 / SAMPLE_RATE
_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/"
    "src/silero_vad/data/silero_vad.onnx"
)


class VADError(RuntimeError):
    pass


def model_path() -> Path:
    return get_settings().data_dir / "models" / "silero_vad.onnx"


def ensure_model() -> Path:
    path = model_path()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            urlretrieve(_MODEL_URL, path)  # ~2.3MB, one-time
        except OSError as err:
            raise VADError(
                f"Couldn't download the Silero VAD model to {path} — "
                "check your internet, or place silero_vad.onnx there manually."
            ) from err
    return path


class SileroVAD:
    """Minimal ONNX wrapper: feed 512-sample float32 chunks @16k, get speech prob."""

    def __init__(self, path: Path | None = None):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(
            str(path or ensure_model()),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, _CONTEXT), dtype=np.float32)

    def prob(self, chunk: np.ndarray) -> float:
        x = np.concatenate(
            [self._context, chunk.astype(np.float32).reshape(1, -1)], axis=1
        )
        out, self._state = self._sess.run(
            None,
            {"input": x, "state": self._state, "sr": np.array(SAMPLE_RATE, np.int64)},
        )
        self._context = x[:, -_CONTEXT:]
        return float(out[0, 0])


class Mic:
    """Always-listening mic. Fires on_speech once ≥start_ms of speech is heard,
    then keeps capturing until ~end_ms of silence and emits the full utterance."""

    def __init__(
        self,
        on_speech=None,
        *,
        start_ms: int = 300,
        end_ms: int = 800,
        threshold: float = 0.5,
        vad: SileroVAD | None = None,
    ):
        self._vad = vad if vad is not None else SileroVAD()
        self._on_speech = on_speech
        self._start_chunks = max(1, round(start_ms / _CHUNK_MS))
        self._end_chunks = max(1, round(end_ms / _CHUNK_MS))
        self._threshold = threshold

        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._utterances: queue.Queue[np.ndarray] = queue.Queue()
        self._preroll: deque[np.ndarray] = deque(maxlen=self._start_chunks + 8)
        self._captured: list[np.ndarray] = []
        self._recording = False
        self._speech = 0
        self._silence = 0

        self._paused = threading.Event()
        self._running = threading.Event()
        self._stream = None
        self._thread: threading.Thread | None = None

    # -- state machine (public so tests can drive it without audio hardware) --

    def process_chunk(self, chunk: np.ndarray) -> None:
        p = self._vad.prob(chunk)
        if self._recording:
            self._captured.append(chunk)
            self._silence = self._silence + 1 if p < self._threshold else 0
            if self._silence >= self._end_chunks:
                utt = np.concatenate(self._captured)
                self._reset_capture()
                self._utterances.put(utt)
        else:
            self._preroll.append(chunk)
            self._speech = self._speech + 1 if p >= self._threshold else 0
            if self._speech >= self._start_chunks:
                self._recording = True
                self._captured = list(self._preroll)
                self._silence = 0
                if self._on_speech:
                    self._on_speech()

    def _reset_capture(self) -> None:
        self._recording = False
        self._captured = []
        self._preroll.clear()
        self._speech = 0
        self._silence = 0

    # -- live audio plumbing --

    def start(self) -> None:
        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=CHUNK, callback=self._cb,
            )
            self._stream.start()
        except Exception as err:
            raise VADError(f"Couldn't open the microphone: {err}") from err
        self._running.set()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _cb(self, indata, frames, time_info, status) -> None:
        self._chunks.put(indata[:, 0].copy())

    def _worker(self) -> None:
        while self._running.is_set():
            try:
                chunk = self._chunks.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._paused.is_set():
                continue  # drop audio while the host is answering
            if len(chunk) == CHUNK:
                self.process_chunk(chunk)

    def utterance(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            return self._utterances.get(timeout=timeout)
        except queue.Empty:
            return None

    def pause(self) -> None:
        self._paused.set()
        self._reset_capture()
        self._vad.reset()

    def resume(self) -> None:
        while not self._chunks.empty():  # drop backlog collected while paused
            try:
                self._chunks.get_nowait()
            except queue.Empty:
                break
        self._paused.clear()

    def stop(self) -> None:
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2)
        if self._stream:
            self._stream.stop()
            self._stream.close()

"""Playback queue: plays segment N while N+1 is being written; instant cancel."""

from __future__ import annotations

import queue
import threading

import numpy as np

from reporadio.voice.tts import Audio

_CHUNK_FRAMES = 1024  # cancel latency ≈ chunk/samplerate → well under 100ms


class PlayerError(RuntimeError):
    pass


class Player:
    def __init__(self):
        try:
            import sounddevice  # noqa: F401 — probe PortAudio early
        except OSError as err:
            raise PlayerError(
                "No audio device layer (PortAudio) found — "
                "install it (e.g. `sudo apt install libportaudio2`) or run with --mute."
            ) from err
        self._q: queue.Queue[Audio | None] = queue.Queue()
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, audio: Audio) -> None:
        self._q.put(audio)

    def stop(self) -> None:
        """Instant cancel: kill current playback and drain the queue."""
        self._cancel.set()
        while True:
            try:
                self._q.get_nowait()
                self._q.task_done()
            except queue.Empty:
                break

    def wait(self) -> None:
        self._q.join()

    def close(self) -> None:
        self._q.put(None)
        self._thread.join(timeout=5)

    def _worker(self) -> None:
        import sounddevice as sd

        while True:
            item = self._q.get()
            if item is None:
                self._q.task_done()
                return
            try:
                if not self._cancel.is_set():
                    self._play(sd, item)
            finally:
                self._q.task_done()

    def _play(self, sd, audio: Audio) -> None:
        samples = audio.samples.reshape(-1, 1)
        with sd.OutputStream(
            samplerate=audio.samplerate, channels=1, dtype="float32"
        ) as stream:
            for start in range(0, len(samples), _CHUNK_FRAMES):
                if self._cancel.is_set():
                    break
                stream.write(np.ascontiguousarray(samples[start:start + _CHUNK_FRAMES]))


class NullPlayer:
    """--mute: exercises the whole pipeline without touching an audio device."""

    def enqueue(self, audio: Audio) -> None:
        pass

    def stop(self) -> None:
        pass

    def wait(self) -> None:
        pass

    def close(self) -> None:
        pass

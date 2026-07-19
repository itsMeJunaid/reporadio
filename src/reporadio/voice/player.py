"""Playback queue: plays segment N while N+1 is being written.
Supports instant cancel AND barge-in interrupt that returns the unplayed
remainder so the show can resume exactly where it stopped."""

from __future__ import annotations

import queue
import threading

import numpy as np

from reporadio.voice.tts import Audio

_CHUNK_FRAMES = 1024  # cancel latency ≈ chunk/samplerate → well under 100ms
_MIN_LEFTOVER_S = 0.5  # don't bother replaying less than half a second


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
        self._lock = threading.Lock()
        self._leftovers: list[Audio] = []
        self._playing = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, audio: Audio) -> None:
        self._q.put(audio)

    def interrupt(self) -> list[Audio]:
        """Barge-in: stop the voice NOW; return remaining audio for later resume
        (the tail of the current segment first, then every queued segment)."""
        self._cancel.set()
        self._q.join()  # queued items funnel into _leftovers almost instantly
        with self._lock:
            leftovers = self._leftovers
            self._leftovers = []
        self._cancel.clear()
        return leftovers

    def stop(self) -> None:
        """Hard stop: cancel and throw the rest of the show away."""
        self.interrupt()

    def wait(self) -> None:
        self._q.join()

    def idle(self) -> bool:
        return self._q.unfinished_tasks == 0 and not self._playing

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
                if self._cancel.is_set():
                    with self._lock:
                        self._leftovers.append(item)  # unplayed → keep whole
                else:
                    self._playing = True
                    self._play(sd, item)
            finally:
                self._playing = False
                self._q.task_done()

    def _play(self, sd, audio: Audio) -> None:
        samples = audio.samples.reshape(-1, 1)
        frames_done = 0
        with sd.OutputStream(
            samplerate=audio.samplerate, channels=1, dtype="float32"
        ) as stream:
            for start in range(0, len(samples), _CHUNK_FRAMES):
                if self._cancel.is_set():
                    break
                block = np.ascontiguousarray(samples[start:start + _CHUNK_FRAMES])
                stream.write(block)
                frames_done = start + len(block)
        remaining = len(samples) - frames_done
        if self._cancel.is_set() and remaining > _MIN_LEFTOVER_S * audio.samplerate:
            with self._lock:
                self._leftovers.append(
                    Audio(audio.samples[frames_done:], audio.samplerate)
                )


class NullPlayer:
    """--mute: exercises the whole pipeline without touching an audio device."""

    def enqueue(self, audio: Audio) -> None:
        pass

    def interrupt(self) -> list[Audio]:
        return []

    def stop(self) -> None:
        pass

    def wait(self) -> None:
        pass

    def idle(self) -> bool:
        return True

    def close(self) -> None:
        pass

"""TTS engines: Kokoro (local, preferred) with edge-tts fallback."""

from __future__ import annotations

import asyncio
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reporadio.config import get_settings


class TTSError(RuntimeError):
    pass


@dataclass
class Audio:
    samples: np.ndarray  # float32 mono
    samplerate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.samplerate


def _to_mono_f32(samples: np.ndarray) -> np.ndarray:
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples.astype(np.float32, copy=False)


class KokoroEngine:
    """Local Kokoro — used when the model files are present in data_dir/kokoro."""

    name = "kokoro"

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._kokoro = None

    @staticmethod
    def model_paths() -> tuple[Path, Path]:
        d = get_settings().data_dir / "kokoro"
        return d / "kokoro-v1.0.onnx", d / "voices-v1.0.bin"

    @classmethod
    def available(cls) -> bool:
        onnx, voices = cls.model_paths()
        return onnx.is_file() and voices.is_file()

    def synth(self, text: str) -> Audio:
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            onnx, voices = self.model_paths()
            self._kokoro = Kokoro(str(onnx), str(voices))
        samples, sr = self._kokoro.create(
            text, voice=self.voice, speed=self.speed, lang="en-us"
        )
        return Audio(_to_mono_f32(np.asarray(samples)), sr)


class EdgeEngine:
    """edge-tts fallback — free neural voices, needs internet."""

    name = "edge"

    def __init__(self, voice: str = "en-US-ChristopherNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    async def _collect(self, text: str) -> bytes:
        import edge_tts

        stream = edge_tts.Communicate(text, self.voice, rate=self.rate).stream()
        return b"".join(
            [c["data"] async for c in stream if c["type"] == "audio"]
        )

    def synth(self, text: str) -> Audio:
        mp3 = asyncio.run(self._collect(text))
        if not mp3:
            raise TTSError("edge-tts returned no audio — is the internet up?")
        return _decode_mp3(mp3)


def _decode_mp3(data: bytes) -> Audio:
    try:
        import soundfile as sf

        samples, sr = sf.read(io.BytesIO(data), dtype="float32")
        return Audio(_to_mono_f32(samples), sr)
    except Exception:
        pass  # older libsndfile without mpeg support → ffmpeg
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", "pipe:0",
             "-f", "f32le", "-ac", "1", "-ar", "24000", "pipe:1"],
            input=data, capture_output=True, check=True,
        ).stdout
        return Audio(np.frombuffer(out, dtype=np.float32), 24000)
    except (subprocess.SubprocessError, OSError) as err:
        raise TTSError(
            "Couldn't decode TTS audio — install ffmpeg or a libsndfile with mp3 support."
        ) from err


def get_engine(preferred: str = "auto", voice: str | None = None, console=None):
    """Pick the best available engine; fall back loudly, never silently."""
    if preferred in ("auto", "kokoro"):
        if KokoroEngine.available():
            return KokoroEngine(voice=voice or "af_heart")
        if preferred == "kokoro" and console:
            onnx, voices_path = KokoroEngine.model_paths()
            console.print(
                f"[yellow]Kokoro model not found — falling back to edge-tts.[/]\n"
                f"[dim]To go local, place kokoro-v1.0.onnx and voices-v1.0.bin in "
                f"{onnx.parent} (github.com/thewh1teagle/kokoro-onnx releases).[/]"
            )
    return EdgeEngine(voice=voice or "en-US-ChristopherNeural")

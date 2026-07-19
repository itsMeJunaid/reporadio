"""Caller speech → text via Groq Whisper."""

from __future__ import annotations

import io

import numpy as np

MODEL = "whisper-large-v3-turbo"


def transcribe(
    samples: np.ndarray,
    samplerate: int = 16000,
    *,
    client=None,
    model: str = MODEL,
) -> str:
    if client is None:
        from groq import Groq

        from reporadio.config import require_groq_key

        client = Groq(api_key=require_groq_key())

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, samplerate, format="WAV", subtype="PCM_16")
    resp = client.audio.transcriptions.create(
        model=model, file=("question.wav", buf.getvalue())
    )
    return resp.text.strip()

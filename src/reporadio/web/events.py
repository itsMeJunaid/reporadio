"""Typed WebSocket event protocol between the studio page and the server.

server → client:
  status          {stage: ingest|index|context|flush|off_air, detail}
  segment_start   {n, title}
  transcript_line {who: host|you, text, files?}
  audio_chunk     {data: base64 int16 PCM mono, samplerate, last: bool}
  ready           {repo, commit, files, tokens, mode, freq, voice, greeting}
  error           {message}

client → server:
  tune_in       {url, mode, lang}
  caller_audio  {data: base64 int16 PCM mono @16k, end: bool}
  pause | resume | skip {}
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

S2C_TYPES = {"status", "segment_start", "transcript_line", "audio_chunk", "ready", "error"}


def event(type_: str, **payload) -> dict:
    assert type_ in S2C_TYPES, type_
    return {"type": type_, **payload}


class TuneIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    mode: str = "standard"
    lang: str | None = None


class CallerAudio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: str = ""  # base64 int16 PCM mono @ 16k
    end: bool = False


class Control(BaseModel):
    model_config = ConfigDict(extra="ignore")


_CLIENT_MODELS: dict[str, type[BaseModel]] = {
    "tune_in": TuneIn,
    "caller_audio": CallerAudio,
    "pause": Control,
    "resume": Control,
    "skip": Control,
}


class ProtocolError(ValueError):
    pass


def parse_client(msg: dict) -> tuple[str, BaseModel]:
    """Validate a client message → (type, payload model). Raises ProtocolError."""
    if not isinstance(msg, dict) or "type" not in msg:
        raise ProtocolError("message must be an object with a 'type' field")
    type_ = msg["type"]
    model = _CLIENT_MODELS.get(type_)
    if model is None:
        raise ProtocolError(
            f"unknown message type '{type_}' — expected one of: "
            + ", ".join(sorted(_CLIENT_MODELS))
        )
    try:
        return type_, model(**{k: v for k, v in msg.items() if k != "type"})
    except ValidationError as err:
        raise ProtocolError(f"bad {type_} payload: {err}") from err

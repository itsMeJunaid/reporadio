"""Typed settings loaded from .env — validation is lazy so the CLI never
crashes at import time; the key is only demanded when a feature needs it."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    data_dir: Path = Path.home() / ".reporadio"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class MissingGroqKeyError(RuntimeError):
    pass


def require_groq_key() -> str:
    key = get_settings().groq_api_key
    if not key:
        raise MissingGroqKeyError(
            "Station's off the air — GROQ_API_KEY is missing.\n"
            "Fix: copy .env.example to .env and paste your free key "
            "from https://console.groq.com"
        )
    return key

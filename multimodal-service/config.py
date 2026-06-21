from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    OCR_MODEL: str = "microsoft/trocr-base-handwritten"
    STT_MODEL: str = "tiny.en"
    STT_DEVICE: str = "cpu"
    STT_COMPUTE_TYPE: str = "int8"
    TTS_LANGUAGE: str = "a"
    TTS_VOICE: str = "af_heart"
    OCR_MAX_BYTES: int = 10 * 1024 * 1024
    AUDIO_MAX_BYTES: int = 25 * 1024 * 1024
    TTS_MAX_CHARS: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()

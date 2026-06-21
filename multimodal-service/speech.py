import re
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from config import get_settings
from models import get_stt_model, get_tts_pipeline


def transcribe(content: bytes, suffix: str = ".webm") -> tuple[str, str, float]:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as audio_file:
        audio_file.write(content)
        audio_path = Path(audio_file.name)

    try:
        segments, info = get_stt_model().transcribe(
            str(audio_path),
            language="en",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=(
                "A financial question about SEC filings. Terms may include "
                "10-K, 10-Q, 8-K, EBITDA, EPS, revenue, gross margin, and ticker symbols."
            ),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info.language, float(info.language_probability)
    finally:
        audio_path.unlink(missing_ok=True)


def _speech_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>`~|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[: get_settings().TTS_MAX_CHARS]


def synthesize(text: str, voice: str | None = None) -> bytes:
    clean = _speech_text(text)
    if not clean:
        raise ValueError("No speakable text")

    pipeline = get_tts_pipeline()
    samples = [
        audio
        for _, _, audio in pipeline(
            clean,
            voice=voice or get_settings().TTS_VOICE,
        )
    ]
    if not samples:
        raise RuntimeError("TTS produced no audio")

    combined = np.concatenate(samples)
    with tempfile.NamedTemporaryFile(suffix=".wav") as output:
        sf.write(output.name, combined, 24000, format="WAV")
        output.seek(0)
        return output.read()

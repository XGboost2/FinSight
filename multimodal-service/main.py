import io
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from config import get_settings
from ocr import extract_handwriting
from speech import synthesize, transcribe


app = FastAPI(title="FinSight Local Multimodal Service", version="1.0.0")

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUDIO_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
}


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "models": {
            "ocr": get_settings().OCR_MODEL,
            "stt": get_settings().STT_MODEL,
            "tts": "hexgrad/Kokoro-82M",
        },
    }


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)):
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Use a JPEG, PNG, or WebP image")
    content = await file.read()
    if not content or len(content) > get_settings().OCR_MAX_BYTES:
        raise HTTPException(413, "Image is empty or too large")

    started = time.perf_counter()
    try:
        text, line_count = await run_in_threadpool(extract_handwriting, content)
    except Exception as exc:
        raise HTTPException(422, f"Handwriting extraction failed: {exc}") from exc
    if not text:
        raise HTTPException(422, "No handwriting was detected")

    return {
        "text": text,
        "modality": "handwriting",
        "model": get_settings().OCR_MODEL,
        "line_count": line_count,
        "processing_ms": round((time.perf_counter() - started) * 1000, 1),
        "requires_confirmation": True,
    }


@app.post("/transcribe")
async def transcription(file: UploadFile = File(...)):
    if file.content_type not in AUDIO_TYPES:
        raise HTTPException(415, "Unsupported audio format")
    content = await file.read()
    if not content or len(content) > get_settings().AUDIO_MAX_BYTES:
        raise HTTPException(413, "Audio is empty or too large")

    started = time.perf_counter()
    suffix = Path(file.filename or "recording.webm").suffix or ".webm"
    try:
        text, language, probability = await run_in_threadpool(
            transcribe,
            content,
            suffix,
        )
    except Exception as exc:
        raise HTTPException(422, f"Transcription failed: {exc}") from exc
    if not text:
        raise HTTPException(422, "No speech was detected")

    return {
        "text": text,
        "modality": "speech",
        "model": f"faster-whisper-{get_settings().STT_MODEL}",
        "language": language,
        "language_probability": round(probability, 4),
        "processing_ms": round((time.perf_counter() - started) * 1000, 1),
        "requires_confirmation": True,
    }


@app.post("/speech")
async def speech(request: SpeechRequest):
    try:
        audio = await run_in_threadpool(
            synthesize,
            request.text,
            request.voice,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Speech synthesis failed: {exc}") from exc

    return StreamingResponse(
        io.BytesIO(audio),
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="finsight-answer.wav"'},
    )

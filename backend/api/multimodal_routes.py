import logging

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import get_settings
from limiter import limiter


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/multimodal", tags=["multimodal"])

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
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str | None = Field(default=None, max_length=50)


def _service_url(path: str) -> str:
    return f"{get_settings().MULTIMODAL_SERVICE_URL.rstrip('/')}/{path.lstrip('/')}"


def _upstream_error(response: httpx.Response) -> HTTPException:
    try:
        detail = response.json().get("detail", "Local multimodal service failed")
    except Exception:
        detail = "Local multimodal service failed"
    return HTTPException(response.status_code, detail)


async def _proxy_upload(
    file: UploadFile,
    path: str,
    allowed_types: set[str],
    max_bytes: int,
) -> dict:
    if file.content_type not in allowed_types:
        raise HTTPException(415, "Unsupported media type")
    content = await file.read()
    if not content:
        raise HTTPException(422, "Uploaded media is empty")
    if len(content) > max_bytes:
        raise HTTPException(413, "Uploaded media is too large")

    try:
        async with httpx.AsyncClient(timeout=get_settings().MULTIMODAL_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _service_url(path),
                files={
                    "file": (
                        file.filename or "upload",
                        content,
                        file.content_type,
                    )
                },
            )
    except httpx.RequestError as exc:
        logger.warning("Multimodal service unavailable for %s: %s", path, exc)
        raise HTTPException(503, "Local multimodal service is unavailable") from exc
    if response.is_error:
        raise _upstream_error(response)
    return response.json()


@router.get("/health")
async def multimodal_health():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(_service_url("/health"))
        if response.is_error:
            raise _upstream_error(response)
        return response.json()
    except httpx.RequestError:
        return {"status": "unavailable"}


@router.post("/ocr")
@limiter.limit("10/minute")
async def extract_handwritten_question(
    request: Request,
    file: UploadFile = File(...),
):
    return await _proxy_upload(
        file,
        "/ocr",
        IMAGE_TYPES,
        get_settings().MULTIMODAL_IMAGE_MAX_BYTES,
    )


@router.post("/transcribe")
@limiter.limit("10/minute")
async def transcribe_question(
    request: Request,
    file: UploadFile = File(...),
):
    return await _proxy_upload(
        file,
        "/transcribe",
        AUDIO_TYPES,
        get_settings().MULTIMODAL_AUDIO_MAX_BYTES,
    )


@router.post("/speech")
@limiter.limit("20/minute")
async def synthesize_answer(request: Request, body: SpeechRequest):
    try:
        async with httpx.AsyncClient(timeout=get_settings().MULTIMODAL_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _service_url("/speech"),
                json=body.model_dump(exclude_none=True),
            )
    except httpx.RequestError as exc:
        logger.warning("Multimodal TTS service unavailable: %s", exc)
        raise HTTPException(503, "Local multimodal service is unavailable") from exc
    if response.is_error:
        raise _upstream_error(response)
    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "audio/wav"),
        headers={"Cache-Control": "no-store"},
    )

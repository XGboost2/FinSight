from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def disable_rate_limits():
    from limiter import limiter

    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def _mock_client(response: httpx.Response):
    client = AsyncMock()
    client.post.return_value = response
    client.get.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context, client


def test_ocr_proxies_image_to_local_service(client):
    response = httpx.Response(
        200,
        json={
            "text": "What are Tesla's margins?",
            "modality": "handwriting",
            "model": "microsoft/trocr-base-handwritten",
            "requires_confirmation": True,
        },
        request=httpx.Request("POST", "http://multimodal/ocr"),
    )
    context, upstream = _mock_client(response)

    with patch("api.multimodal_routes.httpx.AsyncClient", return_value=context):
        result = client.post(
            "/api/multimodal/ocr",
            files={"file": ("question.png", b"png-data", "image/png")},
        )

    assert result.status_code == 200
    assert result.json()["text"] == "What are Tesla's margins?"
    assert upstream.post.call_args.kwargs["files"]["file"][2] == "image/png"


def test_ocr_rejects_non_image(client):
    result = client.post(
        "/api/multimodal/ocr",
        files={"file": ("question.txt", b"text", "text/plain")},
    )
    assert result.status_code == 415


def test_transcription_proxies_audio(client):
    response = httpx.Response(
        200,
        json={
            "text": "What is the revenue trend?",
            "modality": "speech",
            "model": "faster-whisper-tiny.en",
            "requires_confirmation": True,
        },
        request=httpx.Request("POST", "http://multimodal/transcribe"),
    )
    context, _ = _mock_client(response)

    with patch("api.multimodal_routes.httpx.AsyncClient", return_value=context):
        result = client.post(
            "/api/multimodal/transcribe",
            files={"file": ("question.webm", b"audio-data", "audio/webm")},
        )

    assert result.status_code == 200
    assert result.json()["text"] == "What is the revenue trend?"


def test_speech_returns_audio(client):
    response = httpx.Response(
        200,
        content=b"RIFF-audio",
        headers={"content-type": "audio/wav"},
        request=httpx.Request("POST", "http://multimodal/speech"),
    )
    context, upstream = _mock_client(response)

    with patch("api.multimodal_routes.httpx.AsyncClient", return_value=context):
        result = client.post(
            "/api/multimodal/speech",
            json={"text": "Tesla reported higher revenue."},
        )

    assert result.status_code == 200
    assert result.headers["content-type"] == "audio/wav"
    assert result.content == b"RIFF-audio"
    upstream.post.assert_awaited_once()

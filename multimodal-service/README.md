# FinSight Local Multimodal Service

This service converts non-text chat input into the existing FinSight chat
contract and renders existing answers as speech.

## Models

- Handwriting OCR: `microsoft/trocr-base-handwritten`
- Speech-to-text: Faster Whisper `tiny.en`, CPU INT8
- Text-to-speech: Kokoro 82M, voice `af_heart`

Models are loaded lazily and cached in the `multimodal_hf_cache` Docker volume.
The first request for each modality downloads its model and is slower than
subsequent requests.

Preload the models before a demo:

```bash
docker compose run --rm multimodal python preload_models.py
```

## Endpoints

- `POST /ocr` — JPEG, PNG, or WebP handwritten question
- `POST /transcribe` — recorded audio
- `POST /speech` — JSON text to WAV
- `GET /health` — configuration health; does not load models

The service does not store uploaded media. Temporary audio files are deleted
after transcription.

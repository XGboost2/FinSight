from functools import lru_cache

from config import get_settings


@lru_cache(maxsize=1)
def get_ocr_model():
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    model_name = get_settings().OCR_MODEL
    processor = TrOCRProcessor.from_pretrained(model_name, use_fast=False)
    model = VisionEncoderDecoderModel.from_pretrained(model_name)
    model.eval()
    return processor, model


@lru_cache(maxsize=1)
def get_stt_model():
    from faster_whisper import WhisperModel

    settings = get_settings()
    return WhisperModel(
        settings.STT_MODEL,
        device=settings.STT_DEVICE,
        compute_type=settings.STT_COMPUTE_TYPE,
    )


@lru_cache(maxsize=1)
def get_tts_pipeline():
    from kokoro import KPipeline

    return KPipeline(lang_code=get_settings().TTS_LANGUAGE)

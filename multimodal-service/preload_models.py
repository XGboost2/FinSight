"""Download local model weights into the persistent Hugging Face cache."""

import gc

from models import get_ocr_model, get_stt_model, get_tts_pipeline


def main() -> None:
    print("Loading handwriting OCR model...")
    processor, model = get_ocr_model()
    del processor, model
    get_ocr_model.cache_clear()
    gc.collect()
    print("OCR model cached.")

    print("Loading speech-to-text model...")
    stt = get_stt_model()
    del stt
    get_stt_model.cache_clear()
    gc.collect()
    print("Speech-to-text model cached.")

    print("Loading text-to-speech model...")
    tts = get_tts_pipeline()
    del tts
    get_tts_pipeline.cache_clear()
    gc.collect()
    print("Text-to-speech model cached.")


if __name__ == "__main__":
    main()

import io

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps

from models import get_ocr_model


def _prepare_image(content: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(content))
    image = ImageOps.exif_transpose(image).convert("RGB")
    if max(image.size) > 2400:
        image.thumbnail((2400, 2400))
    return image


def _line_images(image: Image.Image) -> list[Image.Image]:
    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    red = rgb[:, :, 0].astype(np.int16)
    green = rgb[:, :, 1].astype(np.int16)
    blue = rgb[:, :, 2].astype(np.int16)
    color_range = np.maximum.reduce([red, green, blue]) - np.minimum.reduce(
        [red, green, blue]
    )
    colored_ink = (
        (color_range > 18)
        & (np.minimum.reduce([red, green, blue]) < 170)
    ).astype(np.uint8) * 255

    # Colored pen is much easier to separate from textured paper than a plain
    # grayscale threshold. For black ink, subtract a blurred paper background
    # so shadows and paper grain do not become one page-sized contour.
    if cv2.countNonZero(colored_ink) >= max(100, image.width * image.height // 5000):
        binary = colored_ink
    else:
        background = cv2.GaussianBlur(gray, (0, 0), sigmaX=15, sigmaY=15)
        dark_ink = cv2.subtract(background, gray)
        _, binary = cv2.threshold(dark_ink, 18, 255, cv2.THRESH_BINARY)
        binary = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)),
        )

    kernel_width = max(15, image.width // 30)
    connected = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 3)),
    )
    contours, _ = cv2.findContours(
        connected,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    boxes = []
    minimum_area = max(80, image.width * image.height // 5000)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width * height >= minimum_area and width >= 20 and height >= 10:
            boxes.append((x, y, width, height))
    boxes.sort(key=lambda box: (box[1], box[0]))

    # Morphology can still produce several word-level contours. Merge contours
    # sharing the same vertical band so TrOCR receives a complete text line.
    merged_boxes: list[list[int]] = []
    for x, y, width, height in boxes:
        if not merged_boxes:
            merged_boxes.append([x, y, width, height])
            continue
        last_x, last_y, last_width, last_height = merged_boxes[-1]
        overlap = max(
            0,
            min(y + height, last_y + last_height) - max(y, last_y),
        )
        center_distance = abs(
            (y + height / 2) - (last_y + last_height / 2)
        )
        same_line = (
            overlap >= min(height, last_height) * 0.25
            or center_distance <= max(height, last_height) * 0.6
        )
        if same_line:
            right = max(x + width, last_x + last_width)
            bottom = max(y + height, last_y + last_height)
            left = min(x, last_x)
            top = min(y, last_y)
            merged_boxes[-1] = [left, top, right - left, bottom - top]
        else:
            merged_boxes.append([x, y, width, height])

    lines = []
    margin = 12
    for x, y, width, height in merged_boxes:
        left = max(0, x - margin)
        top = max(0, y - margin)
        right = min(image.width, x + width + margin)
        bottom = min(image.height, y + height + margin)
        crop = image.crop((left, top, right, bottom))
        if crop.width > crop.height * 1.5:
            lines.append(crop)

    # TrOCR is line-oriented. Fall back to the whole image for a single-line note.
    return lines or [image]


def extract_handwriting(content: bytes) -> tuple[str, int]:
    image = _prepare_image(content)
    lines = _line_images(image)
    processor, model = get_ocr_model()
    extracted = []

    for line in lines:
        pixel_values = processor(images=line, return_tensors="pt").pixel_values
        with torch.inference_mode():
            generated_ids = model.generate(pixel_values, max_new_tokens=128)
        text = processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
        )[0].strip()
        if text:
            extracted.append(text)

    return " ".join(extracted).strip(), len(lines)

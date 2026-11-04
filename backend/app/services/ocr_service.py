from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR


# Load the OCR model only once.
_ocr_engine = None


def get_ocr_engine():
    global _ocr_engine

    if _ocr_engine is None:
        _ocr_engine = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    return _ocr_engine


def extract_text_from_image(
    image_bytes: bytes,
    page_number: int
) -> dict[str, Any]:
    """
    Extract text from a page image using PaddleOCR.
    """

    if not image_bytes:
        raise ValueError("Image data is empty")

    try:
        # Convert PNG/JPEG bytes into a NumPy image.
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_array = np.array(image)

        # Run OCR.
        engine = get_ocr_engine()
        results = engine.predict(input=image_array)

        if not results:
            return {
                "page_number": page_number,
                "text": "",
                "lines": [],
                "average_confidence": 0.0,
                "source": "paddleocr",
            }

        result = results[0]

        recognized_texts = result.get("rec_texts", [])
        confidence_scores = result.get("rec_scores", [])

        lines = []

        for text, score in zip(recognized_texts, confidence_scores):
            text = str(text).strip()
            score = float(score)

            if text:
                lines.append({
                    "text": text,
                    "confidence": round(score, 4),
                })

        full_text = "\n".join(
            line["text"] for line in lines
        )

        average_confidence = (
            sum(line["confidence"] for line in lines) / len(lines)
            if lines else 0.0
        )

        return {
            "page_number": page_number,
            "text": full_text,
            "lines": lines,
            "average_confidence": round(average_confidence, 4),
            "source": "paddleocr",
        }

    except Exception as exc:
        raise RuntimeError(
            f"OCR failed on page {page_number}"
        ) from exc
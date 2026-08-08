"""OCR extraction and text analysis"""

import pytesseract
from PIL import Image
import re

def extract_and_analyze_text(image_path: str) -> tuple[float, dict, list[str]]:
    """
    Extract text from image using OCR and analyze quality.

    Returns:
        (score, ocr_data, flags) - quality score 0-1, extracted text data, findings
    """
    flags = []
    score = 0.5
    ocr_data = {"text": "", "words": [], "confidence": 0}

    try:
        img = Image.open(image_path)

        # Extract text using Tesseract
        try:
            text = pytesseract.image_to_string(img)
            ocr_data["text"] = text.strip()

            # Get word-level data with confidence
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            # Extract words with confidence
            words = []
            confidences = []
            for i, word in enumerate(data['text']):
                if word.strip():
                    words.append(word)
                    conf = int(data['conf'][i])
                    if conf > 0:
                        confidences.append(conf)

            ocr_data["words"] = words

            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                ocr_data["confidence"] = avg_confidence

                # Score based on OCR confidence (stricter thresholds)
                if avg_confidence > 85:
                    score += 0.3
                    flags.append(f"✓ High OCR confidence: {avg_confidence:.1f}%")
                elif avg_confidence > 75:
                    score += 0.1
                    flags.append(f"✓ Good OCR confidence: {avg_confidence:.1f}%")
                elif avg_confidence > 60:
                    score -= 0.1
                    flags.append(f"⚠️ Medium OCR confidence: {avg_confidence:.1f}%")
                else:
                    score -= 0.3
                    flags.append(f"❌ Low OCR confidence: {avg_confidence:.1f}% (suspicious)")

            # Check text quantity
            word_count = len(words)
            if word_count > 10:
                score += 0.2
                flags.append(f"✓ Substantial text detected: {word_count} words")
            elif word_count > 0:
                flags.append(f"⚠️ Limited text: {word_count} words")
            else:
                flags.append("⚠️ No text detected in image")

        except Exception as e:
            flags.append(f"⚠️ OCR processing error: {str(e)}")
            score -= 0.1

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        return score, ocr_data, flags

    except Exception as e:
        return 0.3, ocr_data, [f"OCR extraction failed: {str(e)}"]

"""Main analysis pipeline combining all detection methods"""

from .ai_detector import detect_ai_generated
from .metadata_detector import analyze_metadata
from .ocr_detector import extract_and_analyze_text
from .document_rules import validate_document_structure

def analyze_image(image_path: str, document_type: str = "generic", source_type: str = "image") -> dict:
    """
    Run complete analysis pipeline on an image.

    Args:
        image_path: Path to image file
        document_type: Type of document being verified
        source_type: Source of the file - "image", "pdf", or "screenshot"

    Returns:
        Complete verification results with confidence scores
    """

    # Route to appropriate analyzer based on source type
    if source_type == "pdf":
        return _analyze_pdf_document(image_path, document_type)
    else:
        # Smart detection: Check if this is a scanned/converted document
        # even though it's in image format (JPEG/PNG)
        meta_score, meta_flags = analyze_metadata(image_path)
        ocr_score, ocr_data, ocr_flags = extract_and_analyze_text(image_path)
        doc_score, doc_flags = validate_document_structure(ocr_data, document_type)

        # Detect scanned/converted documents:
        # - No camera metadata (meta_score < 0.5)
        # - Excellent OCR quality (ocr_score > 0.8)
        # - Good document structure (doc_score > 0.7)
        has_no_camera = meta_score < 0.5
        has_good_ocr = ocr_score > 0.8
        has_good_doc = doc_score > 0.7

        # If it looks like a scanned/converted document, use PDF scoring
        if has_no_camera and has_good_ocr and has_good_doc:
            return _analyze_scanned_document(image_path, document_type, meta_score, meta_flags,
                                            ocr_score, ocr_data, ocr_flags, doc_score, doc_flags)
        else:
            return _analyze_photo_image(image_path, document_type)


def _analyze_scanned_document(image_path: str, document_type: str,
                             meta_score: float, meta_flags: list,
                             ocr_score: float, ocr_data: dict, ocr_flags: list,
                             doc_score: float, doc_flags: list) -> dict:
    """
    Analyze scanned/converted documents (JPEG/PNG without camera metadata).

    These are images that look like digital documents:
    - No camera metadata (scanned or PDF-to-image conversion)
    - High OCR quality
    - Good document structure

    Uses PDF-style scoring since they're digital documents, not photos.
    """

    # Run AI detection (only one we haven't computed yet)
    ai_prob, ai_signals = detect_ai_generated(image_path)

    # Use PDF-style scoring (same as _analyze_pdf_document)
    confidence = (
        (1 - ai_prob) * 0.15 +      # AI detection (15%)
        meta_score * 0.20 +          # Metadata analysis (20%)
        ocr_score * 0.30 +           # OCR quality (30%)
        doc_score * 0.35             # Document structure (35%)
    )

    # Determine verdicts
    is_ai_generated = ai_prob > 0.65

    # Tampering detection
    has_editing_software = any("editing software detected" in flag.lower() for flag in meta_flags)
    has_suspicious_patterns = any("suspicious" in flag.lower() for flag in doc_flags)
    has_low_confidence = confidence < 0.6

    is_tampered = has_editing_software or (has_suspicious_patterns and has_low_confidence)

    # Real document requires: confidence >= 0.6 AND not AI-generated
    is_real_image = confidence >= 0.6 and not is_ai_generated

    # Compile reasoning
    reasoning = []

    # Add verdict if confidence is below threshold
    if confidence < 0.6:
        reasoning.append(f"❌ INVALID DOCUMENT: Overall confidence {confidence:.2f} is below 0.6 threshold")

    # Add auto-detection note
    reasoning.insert(0, "ℹ️ SCANNED/CONVERTED DOCUMENT: Image detected as digital document (no camera metadata, high OCR quality)")

    # Add negative flags (prioritize document structure issues)
    negative_flags = [f for f in doc_flags + ocr_flags + meta_flags if '❌' in f or '⚠️' in f]
    reasoning.extend(negative_flags[:5])

    # Add positive flags
    positive_flags = [f for f in doc_flags + ocr_flags + ai_signals if '✓' in f]
    reasoning.extend(positive_flags[:3])

    return {
        "is_real_image": is_real_image,
        "is_ai_generated": is_ai_generated,
        "is_tampered": is_tampered,
        "confidence": round(confidence, 2),
        "signals": {
            "ai_probability": round(ai_prob, 2),
            "metadata_score": round(meta_score, 2),
            "ocr_score": round(ocr_score, 2),
            "document_score": round(doc_score, 2)
        },
        "reasoning": reasoning,
        "document_type": document_type,
        "source_type": "scanned_document"
    }


def _analyze_pdf_document(image_path: str, document_type: str) -> dict:
    """
    Analyze PDF documents (digital tickets, boarding passes, invoices).

    PDFs are judged primarily on:
    - Document structure and validity (35%)
    - OCR quality and readability (30%)
    - AI detection (15%)
    - Basic metadata (20% - but PDFs lack camera info)
    """

    # Run all detectors
    ai_prob, ai_signals = detect_ai_generated(image_path)
    meta_score, meta_flags = analyze_metadata(image_path)
    ocr_score, ocr_data, ocr_flags = extract_and_analyze_text(image_path)
    doc_score, doc_flags = validate_document_structure(ocr_data, document_type)

    # PDF-specific confidence calculation
    # Focus on document validity and OCR quality rather than camera metadata
    confidence = (
        (1 - ai_prob) * 0.15 +      # AI detection (15%)
        meta_score * 0.20 +          # Metadata analysis (20% - PDFs lack camera data)
        ocr_score * 0.30 +           # OCR quality (30% - critical for PDFs)
        doc_score * 0.35             # Document structure (35% - PRIMARY for PDFs)
    )

    # Determine verdicts for PDFs
    is_ai_generated = ai_prob > 0.65

    # Tampering detection for PDFs - focus on document inconsistencies
    has_editing_software = any("editing software detected" in flag.lower() for flag in meta_flags)
    has_suspicious_patterns = any("suspicious" in flag.lower() for flag in doc_flags)
    has_low_confidence = confidence < 0.6

    # PDFs are tampered if: editing software detected OR suspicious patterns with low confidence
    is_tampered = has_editing_software or (has_suspicious_patterns and has_low_confidence)

    # Real document requires: confidence >= 0.6 AND not AI-generated
    is_real_image = confidence >= 0.6 and not is_ai_generated

    # Compile reasoning for PDFs
    reasoning = []

    # Add verdict if confidence is below threshold
    if confidence < 0.6:
        reasoning.append(f"❌ INVALID DOCUMENT: Overall confidence {confidence:.2f} is below 0.6 threshold")

    # Add negative flags (prioritize document structure issues)
    negative_flags = [f for f in doc_flags + ocr_flags + meta_flags if '❌' in f or '⚠️' in f]
    reasoning.extend(negative_flags[:5])

    # Add positive flags
    positive_flags = [f for f in doc_flags + ocr_flags + ai_signals if '✓' in f]
    reasoning.extend(positive_flags[:3])

    return {
        "is_real_image": is_real_image,
        "is_ai_generated": is_ai_generated,
        "is_tampered": is_tampered,
        "confidence": round(confidence, 2),
        "signals": {
            "ai_probability": round(ai_prob, 2),
            "metadata_score": round(meta_score, 2),
            "ocr_score": round(ocr_score, 2),
            "document_score": round(doc_score, 2)
        },
        "reasoning": reasoning,
        "document_type": document_type,
        "source_type": "pdf"
    }


def _analyze_photo_image(image_path: str, document_type: str) -> dict:
    """
    Analyze photo images (JPEG/PNG from cameras/phones or screenshots).

    STRICT MODE: Photos must have camera metadata to pass.

    Photos are judged primarily on:
    - Camera metadata (50%) - Make, Model, GPS, EXIF (CRITICAL)
    - Document structure (25%)
    - AI detection (15%)
    - OCR quality (10%) - least important for photos
    """

    # Run all detectors
    ai_prob, ai_signals = detect_ai_generated(image_path)
    meta_score, meta_flags = analyze_metadata(image_path)
    ocr_score, ocr_data, ocr_flags = extract_and_analyze_text(image_path)
    doc_score, doc_flags = validate_document_structure(ocr_data, document_type)

    # Photo-specific confidence calculation - STRICTER
    # Camera metadata is CRITICAL (50%) - without it, photos fail
    confidence = (
        (1 - ai_prob) * 0.15 +      # AI detection (15%)
        meta_score * 0.50 +          # Metadata analysis (50% - CRITICAL for photos)
        ocr_score * 0.10 +           # OCR quality (10% - least important)
        doc_score * 0.25             # Document structure (25%)
    )

    # Determine verdicts for photos
    is_ai_generated = ai_prob > 0.65

    # STRICT tampering detection for photos
    has_editing_software = any("editing software detected" in flag.lower() for flag in meta_flags)
    has_suspicious_patterns = any("suspicious" in flag.lower() for flag in doc_flags)
    has_no_camera_metadata = meta_score < 0.5  # Critical: No camera Make/Model

    # Screenshot detection - PNG without camera metadata OR JPEG without camera info
    is_png_format = any("png format" in flag.lower() for flag in meta_flags)
    has_no_exif = any("no exif" in flag.lower() for flag in meta_flags)
    is_screenshot = (is_png_format and has_no_exif) or has_no_camera_metadata

    # Photos are tampered if:
    # - Editing software detected
    # - Screenshot (PNG + no EXIF) or missing camera metadata
    # - Suspicious patterns (even with decent confidence)
    is_tampered = has_editing_software or is_screenshot or (has_suspicious_patterns and confidence < 0.75)

    # Threshold for photos: confidence >= 0.6
    # Real photo MUST have camera metadata + good document structure
    is_real_image = confidence >= 0.6 and not is_ai_generated

    # Compile reasoning for photos
    reasoning = []

    # Add verdict if confidence is below threshold
    if confidence < 0.6:
        reasoning.append(f"❌ FAKE IMAGE DETECTED: Overall confidence {confidence:.2f} is below 0.6 threshold (photos require camera metadata)")

    # Add screenshot/missing metadata warning if detected
    if is_screenshot:
        if has_no_camera_metadata:
            reasoning.append("❌ MISSING CAMERA METADATA: Real photos must have camera Make/Model info")
        else:
            reasoning.append("❌ SCREENSHOT DETECTED: PNG image without camera metadata (likely edited/tampered)")

    # Add negative flags (prioritize metadata issues for photos)
    negative_flags = [f for f in meta_flags + doc_flags + ocr_flags if '❌' in f or '⚠️' in f]
    reasoning.extend(negative_flags[:5])

    # Add positive flags
    positive_flags = [f for f in meta_flags + doc_flags + ai_signals if '✓' in f]
    reasoning.extend(positive_flags[:3])

    return {
        "is_real_image": is_real_image,
        "is_ai_generated": is_ai_generated,
        "is_tampered": is_tampered,
        "confidence": round(confidence, 2),
        "signals": {
            "ai_probability": round(ai_prob, 2),
            "metadata_score": round(meta_score, 2),
            "ocr_score": round(ocr_score, 2),
            "document_score": round(doc_score, 2)
        },
        "reasoning": reasoning,
        "document_type": document_type,
        "source_type": "image"
    }

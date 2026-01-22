"""Main analysis pipeline combining all detection methods"""

from .ai_detector import detect_ai_generated
from .metadata_detector import analyze_metadata
from .ocr_detector import extract_and_analyze_text
from .document_rules import validate_document_structure

def analyze_image(image_path: str, document_type: str = "generic") -> dict:
    """
    Run complete analysis pipeline on an image.

    Args:
        image_path: Path to image file
        document_type: Type of document being verified

    Returns:
        Complete verification results with confidence scores
    """

    # Run all detectors
    ai_prob, ai_signals = detect_ai_generated(image_path)
    meta_score, meta_flags = analyze_metadata(image_path)
    ocr_score, ocr_data, ocr_flags = extract_and_analyze_text(image_path)
    doc_score, doc_flags = validate_document_structure(ocr_data, document_type)

    # Calculate overall confidence
    # Weighted combination of all signals
    # Prioritize metadata and document validation for fake detection
    confidence = (
        (1 - ai_prob) * 0.30 +      # AI detection (inverted - higher AI prob = lower confidence)
        meta_score * 0.30 +           # Metadata analysis (increased weight)
        ocr_score * 0.15 +            # OCR quality
        doc_score * 0.25              # Document structure (increased weight)
    )

    # Determine final verdicts
    is_ai_generated = ai_prob > 0.65

    # is_tampered: Only flag if we have ACTIVE evidence of editing (not just missing metadata)
    has_editing_software = any("editing software detected" in flag.lower() for flag in meta_flags)
    has_suspicious_patterns = any("suspicious" in flag.lower() for flag in doc_flags)

    # Tampered = editing software detected OR multiple suspicious document patterns
    is_tampered = has_editing_software or (has_suspicious_patterns and confidence < 0.6)

    is_real_image = confidence > 0.7 and not is_ai_generated  # Raised threshold for stricter validation

    # Compile reasoning - prioritize negative flags (❌ and ⚠️)
    reasoning = []

    # Add all negative flags first
    negative_flags = [f for f in meta_flags + doc_flags + ocr_flags if '❌' in f or '⚠️' in f]
    reasoning.extend(negative_flags[:5])  # Show up to 5 negative signals

    # Then add positive flags
    positive_flags = [f for f in meta_flags + doc_flags + ai_signals if '✓' in f]
    reasoning.extend(positive_flags[:3])  # Show up to 3 positive signals

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
        "document_type": document_type
    }

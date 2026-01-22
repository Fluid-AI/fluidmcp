"""Metadata and EXIF analysis for tampering detection"""

from PIL import Image
from PIL.ExifTags import TAGS
import piexif

def analyze_metadata(image_path: str) -> tuple[float, list[str]]:
    """
    Analyze image metadata for signs of tampering.

    Returns:
        (score, flags) - score 0-1 (higher = more authentic), list of findings
    """
    flags = []
    score = 0.5  # Start neutral

    try:
        img = Image.open(image_path)

        # Check for EXIF data
        exif_data = img._getexif() if hasattr(img, '_getexif') else None

        if exif_data is None:
            score -= 0.3
            flags.append("⚠️ No EXIF metadata found (suspicious for photos)")
        else:
            # Check for software tags indicating editing
            software_tags = []
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)

                if tag == "Software":
                    software_tags.append(str(value))

                    # Check for editing software
                    editing_software = ["photoshop", "gimp", "canva", "figma", "sketch",
                                       "stable diffusion", "midjourney", "dall-e", "dalle"]

                    if any(soft in str(value).lower() for soft in editing_software):
                        score -= 0.4
                        flags.append(f"❌ Editing software detected: {value}")
                    else:
                        score += 0.2
                        flags.append(f"✓ Camera/phone software: {value}")

                # Check for camera make/model (authentic photos have this)
                if tag in ["Make", "Model"]:
                    score += 0.15
                    flags.append(f"✓ Camera info present: {tag} = {value}")

            # Check for GPS data (real photos often have this)
            if any(tag in ["GPSInfo"] for tag in [TAGS.get(tid) for tid in exif_data.keys()]):
                score += 0.1
                flags.append("✓ GPS data present (indicates real photo)")

        # Check file format
        if img.format == "PNG":
            score -= 0.1
            flags.append("⚠️ PNG format (screenshots and AI images often PNG)")
        elif img.format in ["JPEG", "JPG"]:
            score += 0.1
            flags.append("✓ JPEG format (common for real photos)")

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        if not flags:
            flags.append("Basic metadata analysis complete")

        return score, flags

    except Exception as e:
        return 0.3, [f"Metadata analysis error: {str(e)}"]

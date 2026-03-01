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
    score = 0.0  # Start at 0, build up based on authentic signals
    has_camera_info = False

    try:
        img = Image.open(image_path)

        # Check for EXIF data
        exif_data = img._getexif() if hasattr(img, '_getexif') else None

        if exif_data is None:
            # No EXIF = major red flag (except for legitimate scanned documents)
            score = 0.1
            flags.append("⚠️ No EXIF metadata found (suspicious for photos)")
        else:
            # Start with base score for having EXIF at all
            score = 0.3
            flags.append("✓ EXIF metadata present")

            # Check for software tags indicating editing
            software_tags = []
            camera_make = None
            camera_model = None

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
                        score += 0.15
                        flags.append(f"✓ Camera/phone software: {value}")

                # Check for camera make/model (authentic photos have this)
                if tag == "Make":
                    camera_make = str(value)
                    has_camera_info = True
                    score += 0.25  # Increased from 0.15
                    flags.append(f"✓ Camera Make: {value}")

                if tag == "Model":
                    camera_model = str(value)
                    has_camera_info = True
                    score += 0.25  # Increased from 0.15
                    flags.append(f"✓ Camera Model: {value}")

            # Bonus: If we have BOTH make and model, this is very authentic
            if camera_make and camera_model:
                score += 0.15
                flags.append("✓ Complete camera identification (strong authenticity signal)")

            # Check for GPS data (real photos often have this)
            if any(tag in ["GPSInfo"] for tag in [TAGS.get(tid) for tid in exif_data.keys()]):
                score += 0.1
                flags.append("✓ GPS data present (indicates real photo)")

        # Check file format
        if img.format == "PNG":
            # PNG without camera info is highly suspicious
            if not has_camera_info:
                score -= 0.2  # Increased penalty
                flags.append("❌ PNG format without camera metadata (likely screenshot/edited)")
            else:
                # PNG with camera info is unusual but possible (photo converted to PNG)
                flags.append("⚠️ PNG format (unusual for camera photos)")
        elif img.format in ["JPEG", "JPG"]:
            score += 0.15  # Increased from 0.1
            flags.append("✓ JPEG format (standard for camera photos)")

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        if not flags:
            flags.append("Basic metadata analysis complete")

        return score, flags

    except Exception as e:
        return 0.3, [f"Metadata analysis error: {str(e)}"]

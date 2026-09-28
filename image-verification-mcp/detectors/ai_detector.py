"""AI-generated image detection using espreso/ai-image-detector model + heuristics"""

from PIL import Image
import numpy as np
import cv2

# Global model cache
_model = None
_processor = None

def _load_model():
    """Load the AI detection model (lazy loading)"""
    global _model, _processor

    if _model is None:
        try:
            from transformers import pipeline
            print("Loading espreso/ai-image-detector model...")
            _model = pipeline("image-classification", model="Organika/sdxl-detector")
            print("✓ Model loaded successfully")
        except Exception as e:
            print(f"⚠️ Could not load AI model: {e}")
            print("⚠️ Falling back to heuristic detection")
            _model = "failed"  # Mark as failed to avoid retrying

    return _model if _model != "failed" else None

def detect_ai_generated(image_path: str) -> tuple[float, list[str]]:
    """
    Detect if image is AI-generated using ML model + heuristics.

    Returns:
        (probability, signals) - probability 0-1, list of detection signals
    """
    signals = []
    ml_score = 0.0
    heuristic_score = 0.0

    try:
        img = Image.open(image_path)

        # Try ML model first
        model = _load_model()
        if model is not None:
            try:
                # Run AI detection model
                result = model(img)

                # Model returns list like:
                # [{'label': 'artificial', 'score': 0.87}, {'label': 'natural', 'score': 0.13}]
                for pred in result:
                    if pred['label'].lower() in ['artificial', 'ai', 'generated', 'fake']:
                        ml_score = pred['score']
                        if ml_score > 0.7:
                            signals.append(f"🤖 AI model: {ml_score:.0%} confidence this is AI-generated")
                        elif ml_score > 0.4:
                            signals.append(f"⚠️ AI model: {ml_score:.0%} probability of AI generation")
                        break
                    elif pred['label'].lower() in ['natural', 'real', 'human']:
                        ml_score = 1.0 - pred['score']
                        if ml_score < 0.3:
                            signals.append(f"✓ AI model: Likely real image ({pred['score']:.0%} confidence)")
                        break

            except Exception as e:
                signals.append(f"⚠️ AI model error: {str(e)[:50]}")
                ml_score = 0.0

        # Run heuristic checks as backup/supplement
        # Convert image to RGB (remove alpha channel if present)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        elif img.mode not in ['RGB', 'L']:
            img = img.convert('RGB')

        img_array = np.array(img)

        # Convert to BGR for OpenCV
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        elif len(img_array.shape) == 2:  # Grayscale
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
        else:
            # Fallback: convert to grayscale then BGR
            gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY) if len(img_array.shape) == 3 else img_array
            img_cv = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        # Heuristic 1: Unusually smooth gradients (AI characteristic)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        if laplacian_var < 50:  # Very smooth
            heuristic_score += 0.3
            signals.append("Unusually smooth gradients (AI characteristic)")

        # Heuristic 2: Perfect symmetry (common in AI generation)
        height, width = gray.shape
        if height > 100 and width > 100:
            left_half = gray[:, :width//2]
            right_half = cv2.flip(gray[:, width//2:], 1)

            if left_half.shape == right_half.shape:
                symmetry = np.mean(np.abs(left_half.astype(float) - right_half.astype(float)))
                if symmetry < 20:
                    heuristic_score += 0.2
                    signals.append("High symmetry detected (common in AI images)")

        # Heuristic 3: Check for common AI dimensions
        ai_common_sizes = [(512, 512), (1024, 1024), (768, 768), (1024, 768)]
        if (img.width, img.height) in ai_common_sizes or (img.height, img.width) in ai_common_sizes:
            heuristic_score += 0.1
            signals.append(f"Common AI size: {img.width}x{img.height}")

        # Heuristic 4: Lack of noise (real photos have sensor noise)
        noise_level = np.std(gray.astype(float) - cv2.GaussianBlur(gray, (5, 5), 0).astype(float))
        if noise_level < 5:
            heuristic_score += 0.2
            signals.append("Lack of sensor noise")

        # Combine ML model (70% weight) and heuristics (30% weight)
        if model is not None and ml_score > 0:
            final_score = ml_score * 0.7 + min(heuristic_score, 1.0) * 0.3
        else:
            # Fallback to pure heuristics if model unavailable
            final_score = min(heuristic_score, 1.0)
            if not signals:
                signals.append("Using heuristic detection (AI model unavailable)")

        if len(signals) == 0:
            signals.append("No AI-generation artifacts detected")

        return min(final_score, 1.0), signals

    except Exception as e:
        return 0.5, [f"AI detection failed: {str(e)}"]

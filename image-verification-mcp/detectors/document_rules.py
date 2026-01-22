"""Document-specific validation rules for boarding passes and IRCTC tickets"""

import re

def validate_document_structure(ocr_data: dict, document_type: str) -> tuple[float, list[str]]:
    """
    Validate document structure based on document type.

    Args:
        ocr_data: OCR extracted data (text, words, confidence)
        document_type: "boarding_pass", "irctc", or "generic"

    Returns:
        (score, flags) - validation score 0-1, list of findings
    """
    text = ocr_data.get("text", "").lower()
    flags = []
    score = 0.5

    if document_type == "irctc":
        score, flags = validate_irctc_ticket(text, ocr_data)
    elif document_type == "boarding_pass":
        score, flags = validate_boarding_pass(text, ocr_data)
    else:
        # Generic validation
        if len(text) > 20:
            score = 0.6
            flags.append("Generic image with text content")
        else:
            score = 0.4
            flags.append("Limited text content")

    return score, flags


def validate_irctc_ticket(text: str, ocr_data: dict) -> tuple[float, list[str]]:
    """Validate Indian Railway (IRCTC) ticket structure."""
    flags = []
    score = 0.2  # Start even lower for stricter validation
    confidence = ocr_data.get("confidence", 0)

    # STRICT CHECK: OCR confidence must be reasonable
    if confidence < 30:
        score -= 0.3
        flags.append(f"❌ Very low OCR confidence: {confidence:.1f}% (likely fake/blurry)")
    elif confidence < 50:
        score -= 0.2
        flags.append(f"⚠️ Low OCR confidence: {confidence:.1f}% (suspicious)")
    elif confidence < 75:
        score -= 0.1
        flags.append(f"⚠️ Medium OCR confidence: {confidence:.1f}%")
    elif confidence > 85:
        score += 0.1
        flags.append(f"✓ High OCR confidence: {confidence:.1f}%")

    # Check for IRCTC keywords (STRICTER - need multiple)
    irctc_keywords = ["irctc", "indian railway", "pnr", "train", "booking", "passenger",
                      "reservation", "ticket", "coach", "berth", "seat"]
    found_keywords = [kw for kw in irctc_keywords if kw in text]

    if len(found_keywords) >= 3:
        score += 0.25
        flags.append(f"✓ Multiple IRCTC keywords: {', '.join(found_keywords[:3])}")
    elif len(found_keywords) >= 1:
        score += 0.1
        flags.append(f"⚠️ Few IRCTC keywords: {', '.join(found_keywords)}")
    else:
        score -= 0.2
        flags.append("❌ No IRCTC-specific keywords detected")

    # Check for PNR format (10 digits) - but flag suspicious patterns
    pnr_pattern = r'\b\d{10}\b'
    pnr_matches = re.findall(pnr_pattern, text)
    if pnr_matches:
        pnr = pnr_matches[0]
        is_suspicious = False

        # Check for suspicious patterns
        if len(set(pnr)) < 3:  # Less than 3 unique digits
            score -= 0.3
            flags.append(f"❌ Suspicious PNR: {pnr} (too repetitive)")
            is_suspicious = True
        elif pnr == ''.join(str(i % 10) for i in range(10)):  # Sequential 0123456789
            score -= 0.3
            flags.append(f"❌ Fake PNR: {pnr} (sequential)")
            is_suspicious = True
        else:
            # Check for digit pairs that repeat (like 8423242084 has "24" twice, "84" twice)
            digit_pairs = [pnr[i:i+2] for i in range(len(pnr)-1)]
            pair_counts = {}
            for pair in digit_pairs:
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

            # Count how many pairs repeat at all (even once)
            repeated_pairs_count = sum(1 for count in pair_counts.values() if count >= 2)

            # If multiple pairs repeat (2 or more pairs), it's suspicious
            if repeated_pairs_count >= 2:
                score -= 0.4  # Increased penalty
                repeated_pairs = [p for p, c in pair_counts.items() if c >= 2]
                flags.append(f"❌ Suspicious PNR pattern: {pnr} (multiple repeated pairs: {', '.join(repeated_pairs)})")
                is_suspicious = True
            elif max(pair_counts.values()) > 2:  # Or if any single pair repeats more than twice
                score -= 0.3
                repeated_pairs = [p for p, c in pair_counts.items() if c > 2]
                flags.append(f"❌ Suspicious PNR pattern: {pnr} (repeated sequences: {', '.join(repeated_pairs)})")
                is_suspicious = True

            # Check for ascending/descending sequences
            digits = [int(d) for d in pnr]
            ascending = sum(1 for i in range(len(digits)-1) if digits[i+1] == digits[i] + 1)
            descending = sum(1 for i in range(len(digits)-1) if digits[i+1] == digits[i] - 1)

            if ascending > 5 or descending > 5:
                score -= 0.2
                flags.append(f"❌ Suspicious PNR: {pnr} (contains long sequence)")
                is_suspicious = True

            # Check for alternating patterns (like 121212 or 848484)
            alternating = sum(1 for i in range(len(digits)-2) if digits[i] == digits[i+2])
            if alternating > 6:
                score -= 0.2
                flags.append(f"❌ Suspicious PNR: {pnr} (alternating pattern)")
                is_suspicious = True

        if not is_suspicious:
            score += 0.2
            flags.append(f"✓ Valid PNR format: {pnr}")
    else:
        score -= 0.15
        flags.append("❌ No valid PNR (10-digit) found")

    # Check for train number format (5 digits) - must be realistic
    train_pattern = r'\b\d{5}\b'
    train_matches = re.findall(train_pattern, text)
    if train_matches:
        train_num = train_matches[0]
        # Real Indian train numbers start with 1-9 (not 0)
        if train_num[0] == '0':
            score -= 0.1
            flags.append(f"⚠️ Suspicious train number: {train_num} (starts with 0)")
        else:
            score += 0.15
            flags.append(f"✓ Train number: {train_num}")
    else:
        score -= 0.1
        flags.append("⚠️ No 5-digit train number found")

    # Check for common station codes (3-4 letter codes) - must be uppercase
    station_pattern = r'\b[A-Z]{3,4}\b'
    stations = re.findall(station_pattern, text.upper())
    valid_stations = [s for s in stations if s not in ['FROM', 'IRCT', 'SEAT', 'BERTH', 'DATE']]

    if len(valid_stations) >= 2:
        score += 0.15
        flags.append(f"✓ Station codes: {', '.join(valid_stations[:2])}")
    else:
        score -= 0.1
        flags.append("⚠️ Missing station codes (source/destination)")

    # Check for date patterns - must be valid dates
    date_patterns = [
        r'\b\d{2}[/-]\d{2}[/-]\d{4}\b',  # DD-MM-YYYY
        r'\b\d{2}[/-]\d{2}[/-]\d{2}\b'    # DD-MM-YY
    ]
    date_matches = []
    for pattern in date_patterns:
        date_matches.extend(re.findall(pattern, text))

    if date_matches:
        # Basic date validation (day <= 31, month <= 12)
        valid_dates = []
        for date_str in date_matches:
            parts = re.split(r'[/-]', date_str)
            if len(parts) >= 2:
                day, month = int(parts[0]), int(parts[1])
                if 1 <= day <= 31 and 1 <= month <= 12:
                    valid_dates.append(date_str)

        if valid_dates:
            score += 0.1
            flags.append(f"✓ Valid date format: {valid_dates[0]}")
        else:
            score -= 0.1
            flags.append("❌ Invalid date values detected")
    else:
        score -= 0.15  # Increased penalty for missing date
        flags.append("❌ No date found")

    # Check for fare/amount (INR)
    fare_pattern = r'(?:rs\.?|inr|₹)\s*\d+'
    if re.search(fare_pattern, text, re.IGNORECASE):
        score += 0.1
        flags.append("✓ Fare/amount detected")
    else:
        score -= 0.1  # Increased penalty
        flags.append("❌ No fare amount found")

    # CRITICAL: Check for minimum required fields
    required_fields = sum([
        len(found_keywords) >= 1,  # At least one IRCTC keyword
        len(pnr_matches) > 0,      # Has PNR
        len(train_matches) > 0,    # Has train number
        len(valid_stations) >= 2,  # Has station codes
        len(date_matches) > 0      # Has date
    ])

    if required_fields < 3:
        score -= 0.3
        flags.append(f"❌ Missing critical fields ({required_fields}/5 present)")

    score = max(0.0, min(1.0, score))
    return score, flags


def validate_boarding_pass(text: str, ocr_data: dict) -> tuple[float, list[str]]:
    """Validate flight boarding pass structure."""
    flags = []
    score = 0.2
    confidence = ocr_data.get("confidence", 0)

    # STRICT CHECK: OCR confidence
    if confidence < 30:
        score -= 0.2
        flags.append(f"❌ Very low OCR confidence: {confidence:.1f}% (likely fake)")
    elif confidence < 50:
        score -= 0.1
        flags.append(f"⚠️ Low OCR confidence: {confidence:.1f}%")
    elif confidence > 70:
        score += 0.1
        flags.append(f"✓ Good OCR confidence: {confidence:.1f}%")

    # Check for boarding pass keywords (STRICTER - need multiple)
    bp_keywords = ["boarding", "flight", "gate", "seat", "departure", "arrival",
                   "passenger", "airline", "terminal", "boarding pass", "check-in"]
    found_keywords = [kw for kw in bp_keywords if kw in text]

    if len(found_keywords) >= 3:
        score += 0.25
        flags.append(f"✓ Multiple boarding keywords: {', '.join(found_keywords[:3])}")
    elif len(found_keywords) >= 1:
        score += 0.1
        flags.append(f"⚠️ Few boarding keywords: {', '.join(found_keywords)}")
    else:
        score -= 0.2
        flags.append("❌ No boarding pass keywords detected")

    # Check for PNR/Booking reference (6 characters alphanumeric)
    pnr_pattern = r'\b[A-Z0-9]{6}\b'
    pnr_matches = re.findall(pnr_pattern, text.upper())
    if pnr_matches:
        score += 0.2
        flags.append(f"✓ Booking reference: {pnr_matches[0]}")
    else:
        score -= 0.1
        flags.append("❌ No booking reference found")

    # Check for flight number (airline code + digits like AI123)
    flight_pattern = r'\b[A-Z]{2}\s*\d{3,4}\b'
    flight_matches = re.findall(flight_pattern, text.upper())
    if flight_matches:
        score += 0.2
        flags.append(f"✓ Flight number: {flight_matches[0]}")
    else:
        score -= 0.1
        flags.append("❌ No valid flight number found")

    # Check for airport codes (3 letter IATA codes) - filter out common words
    airport_pattern = r'\b[A-Z]{3}\b'
    airports = re.findall(airport_pattern, text.upper())
    valid_airports = [a for a in airports if a not in ['THE', 'AND', 'FOR', 'YOU', 'ARE', 'STA', 'SEA']]

    if len(valid_airports) >= 2:
        score += 0.15
        flags.append(f"✓ Airport codes: {', '.join(valid_airports[:2])}")
    else:
        score -= 0.1
        flags.append("❌ Missing airport codes (origin/destination)")

    # Check for gate number
    gate_pattern = r'\bgate\s*[A-Z]?\d+\b'
    if re.search(gate_pattern, text, re.IGNORECASE):
        score += 0.1
        flags.append("✓ Gate number detected")
    else:
        score -= 0.05
        flags.append("⚠️ No gate number found")

    # Check for seat number
    seat_pattern = r'\b\d{1,2}[A-F]\b'
    if re.search(seat_pattern, text.upper()):
        score += 0.1
        flags.append("✓ Seat number detected")
    else:
        score -= 0.05
        flags.append("⚠️ No seat number found")

    # Check for time format (HH:MM) - must be valid time
    time_pattern = r'\b([0-2]\d):([0-5]\d)\b'
    time_matches = re.findall(time_pattern, text)
    valid_times = [f"{h}:{m}" for h, m in time_matches if 0 <= int(h) <= 23]

    if valid_times:
        score += 0.1
        flags.append(f"✓ Valid time format: {valid_times[0]}")
    else:
        score -= 0.05
        flags.append("⚠️ No valid time found")

    # Check for date patterns
    date_patterns = [
        r'\b\d{2}[/-]\d{2}[/-]\d{4}\b',
        r'\b\d{2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b'
    ]
    has_date = any(re.search(pattern, text, re.IGNORECASE) for pattern in date_patterns)
    if has_date:
        score += 0.05
        flags.append("✓ Date format detected")

    # CRITICAL: Check for minimum required fields
    required_fields = sum([
        len(found_keywords) >= 1,    # At least one keyword
        len(pnr_matches) > 0,        # Has PNR
        len(flight_matches) > 0,     # Has flight number
        len(valid_airports) >= 2,    # Has airport codes
        len(valid_times) > 0         # Has time
    ])

    if required_fields < 3:
        score -= 0.3
        flags.append(f"❌ Missing critical fields ({required_fields}/5 present)")

    score = max(0.0, min(1.0, score))
    return score, flags

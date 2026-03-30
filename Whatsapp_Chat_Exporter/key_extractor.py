"""
Extract WhatsApp encryption key from screenshots.
Supports OCR extraction via pytesseract or manual input cleanup.
"""

import re
import os
import logging
import string
from typing import Optional


def extract_key_from_image(image_path: str) -> Optional[str]:
    """
    Extract a 64-character hex encryption key from a WhatsApp screenshot.

    WhatsApp displays the key as groups of 2 hex digits arranged in rows.
    This function uses OCR to read the key from the screenshot.

    Args:
        image_path: Path to the screenshot image file.

    Returns:
        The 64-character hex key string, or None if extraction failed.
    """
    if not os.path.isfile(image_path):
        logging.error(f"Image file not found: {image_path}")
        return None

    # Try pytesseract OCR
    try:
        key = _extract_with_tesseract(image_path)
        if key:
            return key
    except ImportError:
        logging.info("pytesseract not installed, trying alternative methods...")
    except Exception as e:
        logging.warning(f"Tesseract OCR failed: {e}")

    # Try EasyOCR as fallback
    try:
        key = _extract_with_easyocr(image_path)
        if key:
            return key
    except ImportError:
        logging.info("easyocr not installed either.")
    except Exception as e:
        logging.warning(f"EasyOCR failed: {e}")

    logging.error(
        "Could not extract key from image. Install an OCR engine:\n"
        "  pip install pytesseract   (+ install Tesseract system package)\n"
        "  pip install easyocr\n"
        "Or enter the key manually with -k 'your_64_hex_chars'"
    )
    return None


def _extract_with_tesseract(image_path: str) -> Optional[str]:
    """Extract key using pytesseract OCR."""
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(image_path)

    # Preprocess: convert to grayscale, increase contrast, sharpen
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img, cutoff=5)
    img = img.filter(ImageFilter.SHARPEN)

    # Try multiple PSM modes for best results
    for psm in [6, 4, 3, 11]:
        try:
            text = pytesseract.image_to_string(
                img,
                config=f'--psm {psm} -c tessedit_char_whitelist=0123456789abcdefABCDEF '
            )
            key = _clean_hex_from_text(text)
            if key:
                logging.info(f"Key extracted successfully via Tesseract (PSM {psm})")
                return key
        except Exception:
            continue

    # Also try without whitelist constraint
    text = pytesseract.image_to_string(img)
    key = _clean_hex_from_text(text)
    if key:
        logging.info("Key extracted successfully via Tesseract (unrestricted)")
        return key

    return None


def _extract_with_easyocr(image_path: str) -> Optional[str]:
    """Extract key using EasyOCR."""
    import easyocr

    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    results = reader.readtext(image_path, detail=0)

    full_text = ' '.join(results)
    key = _clean_hex_from_text(full_text)
    if key:
        logging.info("Key extracted successfully via EasyOCR")
        return key

    return None


def _clean_hex_from_text(text: str) -> Optional[str]:
    """
    Extract a 64-character hex key from OCR text output.

    Handles common OCR mistakes and various formatting:
    - Groups separated by spaces: "a1 b2 c3 d4..."
    - Groups with newlines
    - Common OCR substitutions: O->0, l->1, I->1, S->5, B->8, G->6
    """
    if not text:
        return None

    # Common OCR character substitutions for hex digits
    ocr_fixes = {
        'O': '0', 'o': '0',
        'I': '1', 'l': '1', '|': '1',
        'S': '5', 's': '5',
        'G': '6', 'g': '6',  # only when in hex context
        'Z': '2', 'z': '2',
        'T': '7',
    }

    # Remove all whitespace, newlines, dashes
    cleaned = text.replace('\n', ' ').replace('\r', '')

    # Find all hex-looking sequences (2+ hex chars)
    hex_groups = re.findall(r'[0-9a-fA-F]{2,}', cleaned)

    if hex_groups:
        # Join all hex groups
        combined = ''.join(hex_groups).lower()

        if len(combined) >= 64:
            # Take first 64 valid hex chars
            result = combined[:64]
            if validate_hex_key(result):
                return result

    # More aggressive: try to fix OCR errors character by character
    raw = ''.join(cleaned.split())  # remove all spaces
    fixed = []
    for char in raw:
        if char in string.hexdigits:
            fixed.append(char.lower())
        elif char in ocr_fixes:
            fixed.append(ocr_fixes[char].lower())
        # Skip non-hex characters entirely

    combined = ''.join(fixed)
    if len(combined) >= 64:
        result = combined[:64]
        if validate_hex_key(result):
            return result

    return None


def validate_hex_key(key: str) -> bool:
    """Validate that a string is a valid 64-character hex key."""
    if len(key) != 64:
        return False
    return all(c in string.hexdigits for c in key)


def clean_key_input(key_input: str) -> Optional[str]:
    """
    Clean and validate a manually entered key.
    Handles various input formats:
    - With spaces: "a1 b2 c3 d4 ..."
    - With dashes: "a1-b2-c3-d4-..."
    - With colons: "a1:b2:c3:d4:..."
    - Plain: "a1b2c3d4..."
    - With 0x prefix: "0xa1b2c3d4..."

    Returns:
        Cleaned 64-char hex string or None if invalid.
    """
    if not key_input:
        return None

    # Remove common separators and prefixes
    cleaned = key_input.strip()
    cleaned = cleaned.replace('0x', '').replace('0X', '')
    cleaned = cleaned.replace(' ', '').replace('-', '').replace(':', '')
    cleaned = cleaned.replace('\n', '').replace('\r', '').replace('\t', '')
    cleaned = cleaned.lower()

    if validate_hex_key(cleaned):
        return cleaned

    # Maybe it's longer with some garbage - try to extract hex chars only
    hex_only = ''.join(c for c in cleaned if c in string.hexdigits)
    if len(hex_only) >= 64:
        result = hex_only[:64]
        if validate_hex_key(result):
            logging.info(f"Key cleaned: extracted {len(hex_only)} hex chars, using first 64")
            return result

    logging.error(
        f"Invalid key: expected 64 hex characters, got {len(hex_only)} hex chars "
        f"from input of length {len(key_input)}"
    )
    return None

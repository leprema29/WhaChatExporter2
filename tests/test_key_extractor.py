"""Tests for key_extractor.py."""
import pytest
from Whatsapp_Chat_Exporter.key_extractor import (
    validate_hex_key, clean_key_input, _clean_hex_from_text
)


class TestValidateHexKey:
    def test_valid_key(self):
        key = "a" * 64
        assert validate_hex_key(key) is True

    def test_valid_key_mixed(self):
        key = "0123456789abcdef" * 4
        assert validate_hex_key(key) is True

    def test_too_short(self):
        assert validate_hex_key("abc") is False

    def test_too_long(self):
        assert validate_hex_key("a" * 65) is False

    def test_invalid_chars(self):
        key = "g" * 64
        assert validate_hex_key(key) is False


class TestCleanKeyInput:
    def test_plain_hex(self):
        key = "0123456789abcdef" * 4
        assert clean_key_input(key) == key

    def test_with_spaces(self):
        raw = "01 23 45 67 89 ab cd ef " * 4
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_with_dashes(self):
        raw = "01-23-45-67-89-ab-cd-ef-" * 4
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_with_colons(self):
        raw = "01:23:45:67:89:ab:cd:ef:" * 4
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_with_0x_prefix(self):
        raw = "0x" + "0123456789abcdef" * 4
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_uppercase(self):
        raw = "0123456789ABCDEF" * 4
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_with_newlines(self):
        raw = "0123456789abcdef\n0123456789abcdef\n0123456789abcdef\n0123456789abcdef"
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4

    def test_too_short_returns_none(self):
        assert clean_key_input("abc") is None

    def test_empty_returns_none(self):
        assert clean_key_input("") is None
        assert clean_key_input(None) is None

    def test_extra_garbage_extracted(self):
        raw = "xxx=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef!!!"
        result = clean_key_input(raw)
        assert result == "0123456789abcdef" * 4


class TestCleanHexFromText:
    def test_clean_ocr_text(self):
        # Simulate OCR output with groups
        text = "01 23 45 67 89 ab cd ef 01 23 45 67 89 ab cd ef 01 23 45 67 89 ab cd ef 01 23 45 67 89 ab cd ef"
        result = _clean_hex_from_text(text)
        assert result == "0123456789abcdef" * 4 + "0" * 0  # 64 chars

    def test_multiline_ocr(self):
        text = "0123456789abcdef\n0123456789abcdef\n0123456789abcdef\n0123456789abcdef"
        result = _clean_hex_from_text(text)
        assert result == "0123456789abcdef" * 4

    def test_empty_text(self):
        assert _clean_hex_from_text("") is None
        assert _clean_hex_from_text(None) is None

    def test_insufficient_hex(self):
        assert _clean_hex_from_text("abc") is None

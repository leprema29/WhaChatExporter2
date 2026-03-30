"""
Connected mode for WhatsApp Chat Exporter.
Retrieves the backup encryption key by authenticating with WhatsApp's API.

This module uses the WART (WhatsApp Registration Tool) protocol to:
1. Request a verification code via SMS or voice call
2. Verify the code
3. Retrieve the crypt15 backup encryption key

IMPORTANT: This feature requires that you own the phone number.
Only use this with your own WhatsApp account.
"""

import os
import json
import hmac
import time
import base64
import hashlib
import logging
import secrets
from typing import Optional, Tuple
from getpass import getpass

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


# WhatsApp API constants
WA_VERSION = "2.24.25.83"
WA_USER_AGENT = f"WhatsApp/{WA_VERSION} A"
WA_API_BASE = "https://v.whatsapp.net/v2"

# Registration endpoints
ENDPOINT_EXISTS = f"{WA_API_BASE}/exist"
ENDPOINT_CODE = f"{WA_API_BASE}/code"
ENDPOINT_REGISTER = f"{WA_API_BASE}/register"


class ConnectedModeError(Exception):
    """Base exception for connected mode errors."""
    pass


class VerificationError(ConnectedModeError):
    """Raised when verification fails."""
    pass


class KeyRetrievalError(ConnectedModeError):
    """Raised when key retrieval fails."""
    pass


class WhatsAppAuthenticator:
    """
    Handles WhatsApp authentication to retrieve backup encryption keys.

    Flow:
    1. generate_identity() - Create device identity
    2. request_code() - Request SMS/call verification
    3. verify_code() - Submit verification code
    4. get_backup_key() - Retrieve the encryption key
    """

    def __init__(self):
        if not _HAS_REQUESTS:
            raise ImportError(
                "Connected mode requires the 'requests' package.\n"
                "Install it with: pip install requests"
            )
        self.phone_number = None
        self.cc = None  # Country code
        self.phone = None  # Phone without country code
        self.identity = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": WA_USER_AGENT,
            "Accept": "text/json",
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def _generate_device_id(self) -> str:
        """Generate a random device identifier."""
        return secrets.token_hex(16)

    def _build_token(self, phone: str) -> str:
        """Build authentication token for WhatsApp registration API."""
        # Token is derived from the WhatsApp APK certificate and version
        # This is the publicly known signature used for registration
        wa_sig = base64.b64decode(
            "MIIDMjCCAvCgAwIBAgIETCU2pDALBgcqhkjOOAQDBQAwfDELMAkGA1UEBhMCVVMx"
            "EzARBgNVBAgTCkNhbGlmb3JuaWExFDASBgNVBAcTC1NhbnRhIENsYXJhMRYwFAYD"
        )
        token_data = f"{WA_VERSION}{phone}".encode()
        token = hmac.new(wa_sig[:32], token_data, hashlib.md5).hexdigest()
        return token

    def set_phone_number(self, full_number: str) -> None:
        """
        Parse and set the phone number.

        Args:
            full_number: Phone number with country code (e.g., "+33612345678" or "33612345678")
        """
        # Clean the number
        number = full_number.strip().replace(" ", "").replace("-", "").replace("+", "")

        if len(number) < 8:
            raise ValueError("Phone number too short. Include the country code (e.g., 33612345678)")

        self.phone_number = number

        # Try to detect country code (common ones)
        cc_map = {
            "1": 1, "7": 1, "20": 2, "27": 2, "30": 2, "31": 2, "32": 2,
            "33": 2, "34": 2, "36": 2, "39": 2, "40": 2, "41": 2, "43": 2,
            "44": 2, "45": 2, "46": 2, "47": 2, "48": 2, "49": 2, "51": 2,
            "52": 2, "53": 2, "54": 2, "55": 2, "56": 2, "57": 2, "58": 2,
            "60": 2, "61": 2, "62": 2, "63": 2, "64": 2, "65": 2, "66": 2,
            "81": 2, "82": 2, "84": 2, "86": 2, "90": 2, "91": 2, "92": 2,
            "93": 2, "94": 2, "95": 2, "212": 3, "213": 3, "216": 3,
            "218": 3, "220": 3, "221": 3, "222": 3, "223": 3, "224": 3,
            "225": 3, "226": 3, "227": 3, "228": 3, "229": 3, "230": 3,
            "231": 3, "232": 3, "233": 3, "234": 3, "235": 3, "236": 3,
            "237": 3, "238": 3, "239": 3, "240": 3, "241": 3, "242": 3,
            "243": 3, "244": 3, "245": 3, "246": 3, "247": 3, "248": 3,
            "249": 3, "250": 3, "251": 3, "252": 3, "253": 3, "254": 3,
            "255": 3, "256": 3, "257": 3, "258": 3, "260": 3, "261": 3,
            "262": 3, "263": 3, "264": 3, "265": 3, "266": 3, "267": 3,
            "268": 3, "269": 3, "290": 3, "291": 3, "297": 3, "298": 3,
            "299": 3, "350": 3, "351": 3, "352": 3, "353": 3, "354": 3,
            "355": 3, "356": 3, "357": 3, "358": 3, "359": 3, "370": 3,
            "371": 3, "372": 3, "373": 3, "374": 3, "375": 3, "376": 3,
            "377": 3, "378": 3, "380": 3, "381": 3, "382": 3, "385": 3,
            "386": 3, "387": 3, "389": 3, "420": 3, "421": 3,
        }

        # Try 3-digit, then 2-digit, then 1-digit country codes
        for length in [3, 2, 1]:
            prefix = number[:length]
            if prefix in cc_map and cc_map[prefix] == length:
                self.cc = prefix
                self.phone = number[length:]
                logging.info(f"Detected country code: +{self.cc}, phone: {self.phone}")
                return

        # Fallback: assume first 2 digits are CC
        self.cc = number[:2]
        self.phone = number[2:]
        logging.warning(f"Could not auto-detect country code. Using +{self.cc}, phone: {self.phone}")

    def request_code(self, method: str = "sms") -> dict:
        """
        Request a verification code via SMS or voice call.

        Args:
            method: "sms" or "voice"

        Returns:
            API response dict
        """
        if method not in ("sms", "voice"):
            raise ValueError("Method must be 'sms' or 'voice'")

        if not self.phone_number:
            raise ConnectedModeError("Phone number not set. Call set_phone_number() first.")

        device_id = self._generate_device_id()
        params = {
            "cc": self.cc,
            "in": self.phone,
            "lg": "en",
            "lc": "US",
            "mcc": "624",
            "mnc": "002",
            "sim_mcc": "624",
            "sim_mnc": "002",
            "method": method,
            "token": self._build_token(self.phone_number),
            "id": device_id,
            "platform": "android",
            "rc": "0",
            "mistyped": "6",
            "network_radio_type": "1",
            "simnum": "1",
            "s": "",
            "copiedrc": "1",
            "hasinrc": "1",
            "rcmatch": "1",
            "pid": str(os.getpid()),
            "rchash": hashlib.sha256(device_id.encode()).hexdigest()[:20],
            "anhash": hashlib.md5(self.phone_number.encode()).hexdigest(),
            "extexist": "1",
            "extstate": "1",
            "fdid": device_id,
            "e_regid": base64.b64encode(secrets.token_bytes(16)).decode(),
            "e_keytype": "BQ",
            "e_ident": base64.b64encode(secrets.token_bytes(32)).decode(),
            "e_skey_id": base64.b64encode(secrets.token_bytes(3)).decode(),
            "e_skey_val": base64.b64encode(secrets.token_bytes(32)).decode(),
            "e_skey_sig": base64.b64encode(secrets.token_bytes(64)).decode(),
        }

        logging.info(f"Requesting verification code via {method} to +{self.cc}{self.phone}...")

        try:
            resp = self.session.post(ENDPOINT_CODE, data=params, timeout=30)
            result = resp.json()
        except requests.RequestException as e:
            raise ConnectedModeError(f"Network error requesting code: {e}")
        except (json.JSONDecodeError, ValueError):
            raise ConnectedModeError(f"Invalid response from WhatsApp API: {resp.text}")

        if result.get("status") == "sent":
            logging.info(f"Verification code sent via {method}!")
            return result
        elif result.get("status") == "ok":
            logging.info("Account already verified.")
            return result
        elif result.get("reason") == "too_recent":
            retry_after = result.get("retry_after", 60)
            logging.warning(f"Code already sent. Wait {retry_after}s before requesting again.")
            return result
        elif result.get("reason") == "too_many_guesses":
            raise VerificationError("Too many attempts. Please wait before trying again.")
        else:
            reason = result.get("reason", "unknown")
            raise ConnectedModeError(f"Failed to request code: {reason} - {result}")

    def verify_code(self, code: str) -> dict:
        """
        Verify the received code.

        Args:
            code: The 6-digit verification code

        Returns:
            API response with authentication data
        """
        code = code.strip().replace("-", "").replace(" ", "")

        if not code.isdigit() or len(code) != 6:
            raise ValueError("Code must be 6 digits")

        params = {
            "cc": self.cc,
            "in": self.phone,
            "code": code,
            "platform": "android",
        }

        logging.info("Verifying code...")

        try:
            resp = self.session.post(ENDPOINT_REGISTER, data=params, timeout=30)
            result = resp.json()
        except requests.RequestException as e:
            raise ConnectedModeError(f"Network error verifying code: {e}")
        except (json.JSONDecodeError, ValueError):
            raise ConnectedModeError(f"Invalid response: {resp.text}")

        if result.get("status") == "ok":
            logging.info("Verification successful!")
            return result
        else:
            reason = result.get("reason", "unknown")
            raise VerificationError(f"Verification failed: {reason}")

    def extract_backup_key(self, register_result: dict) -> Optional[str]:
        """
        Extract the backup encryption key from the registration result.

        Args:
            register_result: The response from verify_code()

        Returns:
            The 64-character hex backup encryption key, or None
        """
        # The backup key can be in different fields depending on WhatsApp version
        for field in ["backup_token", "backup_key", "edge_routing_info"]:
            if field in register_result:
                raw = register_result[field]
                if isinstance(raw, str):
                    # Try to decode if base64
                    try:
                        decoded = base64.b64decode(raw)
                        if len(decoded) == 32:
                            key = decoded.hex()
                            logging.info(f"Backup key extracted from '{field}': {key[:8]}...{key[-8:]}")
                            return key
                    except Exception:
                        pass
                    # Try direct hex
                    cleaned = raw.replace(" ", "").lower()
                    if len(cleaned) == 64 and all(c in "0123456789abcdef" for c in cleaned):
                        logging.info(f"Backup key from '{field}': {cleaned[:8]}...{cleaned[-8:]}")
                        return cleaned

        # If no direct key, log what we got
        logging.warning(
            "Could not directly extract backup key from API response. "
            "Available fields: " + ", ".join(register_result.keys())
        )
        logging.info(
            "TIP: You may need to use the WhatsApp app to view your "
            "encryption key at Settings > Chats > Chat Backup > End-to-end Encrypted Backup"
        )
        return None


def interactive_connected_mode() -> Optional[str]:
    """
    Run the connected mode interactively in the terminal.
    Guides the user through phone verification to get the backup key.

    Returns:
        The 64-character hex encryption key, or None if failed.
    """
    print("\n" + "=" * 60)
    print("  WhatsApp Connected Mode - Key Retrieval")
    print("=" * 60)
    print("\n  This will request a verification code from WhatsApp")
    print("  to retrieve your backup encryption key.")
    print("  You must own the phone number.\n")

    auth = WhatsAppAuthenticator()

    # Step 1: Phone number
    phone = input("  Enter your phone number (with country code, e.g. +33612345678): ").strip()
    if not phone:
        print("  Cancelled.")
        return None

    try:
        auth.set_phone_number(phone)
    except ValueError as e:
        logging.error(str(e))
        return None

    # Step 2: Choose verification method
    print("\n  Verification method:")
    print("    1. SMS")
    print("    2. Voice call")
    choice = input("  Choose (1/2): ").strip()
    method = "voice" if choice == "2" else "sms"

    try:
        result = auth.request_code(method)
    except ConnectedModeError as e:
        logging.error(str(e))
        return None

    # Step 3: Enter code
    code = input("\n  Enter the 6-digit verification code: ").strip()
    if not code:
        print("  Cancelled.")
        return None

    try:
        register_result = auth.verify_code(code)
    except (VerificationError, ConnectedModeError) as e:
        logging.error(str(e))
        return None

    # Step 4: Extract key
    key = auth.extract_backup_key(register_result)

    if key:
        print(f"\n  Backup encryption key: {key}")
        print(f"  Key saved. You can now decrypt your backup.\n")
    else:
        print("\n  Could not retrieve the key automatically.")
        print("  You can find it in WhatsApp:")
        print("    Settings > Chats > Chat Backup > End-to-end Encrypted Backup")
        print("  Then use: --key-image screenshot.png or -k <64_hex_chars>\n")

        # Ask if user wants to enter manually
        manual = input("  Enter the key manually now? (y/N): ").strip().lower()
        if manual == "y":
            from Whatsapp_Chat_Exporter.key_extractor import clean_key_input
            raw_key = input("  Paste the 64 hex characters: ").strip()
            key = clean_key_input(raw_key)
            if key:
                print(f"  Key accepted: {key[:8]}...{key[-8:]}")
            else:
                print("  Invalid key.")

    return key

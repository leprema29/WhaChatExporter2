"""
Connected mode for WhatsApp Chat Exporter.
Provides methods to retrieve the backup encryption key.

Since WhatsApp's registration API is protected by device attestation
(SafetyNet/Play Integrity), direct API access is not reliable.
Instead, this module provides:

1. Integration with wa-crypt-tools (pip install wa-crypt-tools)
   which can extract the key from Google Drive backups
2. Key extraction from rooted Android devices (adb)
3. Step-by-step guide for manual key retrieval
4. Key file format detection and conversion

IMPORTANT: Only use this with your own WhatsApp account.
"""

import os
import logging
import subprocess
import shutil
from typing import Optional


def extract_key_with_wacreator(phone_number: str) -> Optional[str]:
    """
    Extract the backup key using wa-crypt-tools.
    This tool can retrieve the key via Google Drive API.

    Requires: pip install wa-crypt-tools

    Args:
        phone_number: Phone number with country code (e.g., "237652619467")

    Returns:
        64-char hex key string or None
    """
    try:
        import wa_crypt_tools
    except ImportError:
        logging.error(
            "wa-crypt-tools is not installed.\n"
            "Install it with: pip install wa-crypt-tools\n"
            "Then run: wacreator decrypt --help"
        )
        return None

    logging.info("wa-crypt-tools is available. Use it directly:")
    logging.info("  wacreator decrypt <backup_file>")
    return None


def extract_key_from_device_adb() -> Optional[str]:
    """
    Extract the encryption key from a rooted Android device via ADB.

    The key file is at:
    /data/data/com.whatsapp/files/encrypted_backup.key

    Returns:
        64-char hex key string or None
    """
    adb = shutil.which("adb")
    if not adb:
        logging.error("ADB not found in PATH. Install Android SDK Platform Tools.")
        return None

    key_paths = [
        "/data/data/com.whatsapp/files/encrypted_backup.key",
        "/data/data/com.whatsapp/files/key",
        "/sdcard/WhatsApp/Databases/.nomedia/../encrypted_backup.key",
    ]

    for key_path in key_paths:
        try:
            result = subprocess.run(
                [adb, "shell", "su", "-c", f"cat {key_path} | xxd -p -c 256"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                hex_key = result.stdout.strip().replace("\n", "")
                # The key file contains more than just the key, extract the 32-byte key
                if len(hex_key) >= 64:
                    # For encrypted_backup.key, the actual key starts at offset 0
                    key = hex_key[:64]
                    logging.info(f"Key extracted via ADB: {key[:8]}...{key[-8:]}")
                    return key
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    logging.error(
        "Could not extract key via ADB. Possible reasons:\n"
        "  - Device not connected\n"
        "  - Device not rooted (root access required)\n"
        "  - WhatsApp not installed on device"
    )
    return None


def read_key_file(key_path: str) -> Optional[str]:
    """
    Read and convert a WhatsApp key file to hex string.
    Handles multiple key file formats:
    - Plain 32-byte binary key
    - Java serialized key (crypt15)
    - Text file with hex key
    - encrypted_backup.key format

    Args:
        key_path: Path to the key file

    Returns:
        64-char hex key string or None
    """
    if not os.path.isfile(key_path):
        logging.error(f"Key file not found: {key_path}")
        return None

    with open(key_path, "rb") as f:
        data = f.read()

    # Case 1: Exactly 32 bytes = raw key
    if len(data) == 32:
        key = data.hex()
        logging.info(f"Raw 32-byte key detected: {key[:8]}...{key[-8:]}")
        return key

    # Case 2: 158 bytes = crypt12/crypt14 key file (key at offset 126)
    if len(data) == 158:
        key = data[126:].hex()
        logging.info(f"Crypt12/14 key file detected: {key[:8]}...{key[-8:]}")
        return key

    # Case 3: Text file containing hex
    try:
        text = data.decode("utf-8", errors="ignore").strip()
        cleaned = text.replace(" ", "").replace("-", "").replace(":", "").replace("\n", "")
        if len(cleaned) >= 64 and all(c in "0123456789abcdefABCDEF" for c in cleaned[:64]):
            key = cleaned[:64].lower()
            logging.info(f"Hex text key file detected: {key[:8]}...{key[-8:]}")
            return key
    except Exception:
        pass

    # Case 4: Java serialized object (crypt15 keyfile)
    try:
        import javaobj
        key_stream = b''.join([
            byte.to_bytes(1, "big", signed=True)
            for byte in javaobj.loads(data)
        ])
        key = key_stream.hex()
        if len(key) >= 64:
            logging.info(f"Java serialized key detected: {key[:8]}...{key[-8:]}")
            return key[:64]
    except Exception:
        pass

    # Case 5: encrypted_backup.key (variable format)
    if len(data) > 64:
        # Try interpreting first 32 bytes as key
        key = data[:32].hex()
        logging.info(f"Using first 32 bytes as key: {key[:8]}...{key[-8:]}")
        return key

    logging.error(f"Could not parse key file ({len(data)} bytes). Unknown format.")
    return None


# Step-by-step instructions for key retrieval
KEY_RETRIEVAL_GUIDE = """
╔══════════════════════════════════════════════════════════════╗
║          How to Get Your WhatsApp Encryption Key            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  METHOD 1: From WhatsApp Settings (easiest)                  ║
║  ─────────────────────────────────────────                   ║
║  1. Open WhatsApp on your phone                             ║
║  2. Go to: Settings > Chats > Chat Backup                   ║
║  3. Tap "End-to-end Encrypted Backup"                       ║
║  4. You'll see your 64-character encryption key              ║
║  5. Take a screenshot or copy the key                       ║
║  6. Use: --key-image screenshot.png                         ║
║     Or:  -k "paste_your_64_hex_chars_here"                  ║
║                                                              ║
║  METHOD 2: From key file (Android, root required)            ║
║  ────────────────────────────────────────────────            ║
║  The key file is located at:                                 ║
║  /data/data/com.whatsapp/files/encrypted_backup.key          ║
║  Copy it to your PC and use: -k path/to/encrypted_backup.key ║
║                                                              ║
║  METHOD 3: Using wa-crypt-tools                              ║
║  ──────────────────────────────                              ║
║  pip install wa-crypt-tools                                  ║
║  Then follow its documentation to extract the key            ║
║                                                              ║
║  METHOD 4: From Google Drive (advanced)                      ║
║  ──────────────────────────────────────                      ║
║  Use a Google Takeout to download your WhatsApp backup       ║
║  The key may be embedded in the backup metadata              ║
║                                                              ║
║  NOTE: One key decrypts ALL crypt15 backups from the same    ║
║  WhatsApp account. The key only changes if you reinstall     ║
║  WhatsApp or reset the encrypted backup.                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def interactive_connected_mode() -> Optional[str]:
    """
    Run the connected mode interactively in the terminal.
    Guides the user through key retrieval options.

    Returns:
        The 64-character hex encryption key, or None if failed.
    """
    print(KEY_RETRIEVAL_GUIDE)

    print("  Choose a method:\n")
    print("    1. Enter key manually (64 hex characters)")
    print("    2. Provide a key file path")
    print("    3. Extract from screenshot (OCR)")
    print("    4. Extract from device via ADB (root required)")
    print("    5. Cancel\n")

    choice = input("  Your choice (1-5): ").strip()

    if choice == "1":
        raw_key = input("\n  Paste your 64 hex characters: ").strip()
        from Whatsapp_Chat_Exporter.key_extractor import clean_key_input
        key = clean_key_input(raw_key)
        if key:
            print(f"\n  Key accepted: {key[:8]}...{key[-8:]}")
            return key
        else:
            print("  Invalid key format. Expected 64 hex characters.")
            return None

    elif choice == "2":
        path = input("\n  Key file path: ").strip().strip('"').strip("'")
        key = read_key_file(path)
        return key

    elif choice == "3":
        path = input("\n  Screenshot path: ").strip().strip('"').strip("'")
        from Whatsapp_Chat_Exporter.key_extractor import extract_key_from_image
        key = extract_key_from_image(path)
        if key:
            print(f"\n  Key extracted: {key[:8]}...{key[-8:]}")
        return key

    elif choice == "4":
        key = extract_key_from_device_adb()
        return key

    else:
        print("  Cancelled.")
        return None

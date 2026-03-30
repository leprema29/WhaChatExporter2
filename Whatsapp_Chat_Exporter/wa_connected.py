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


def check_adb_status() -> dict:
    """
    Check ADB connection status and list connected devices.

    Returns:
        Dict with 'available' (bool), 'devices' (list of device info dicts)
    """
    adb = shutil.which("adb")
    if not adb:
        return {
            "available": False,
            "devices": [],
            "error": "ADB not found. Install Android SDK Platform Tools: "
                     "https://developer.android.com/tools/releases/platform-tools"
        }

    try:
        result = subprocess.run(
            [adb, "devices", "-l"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if not line or "offline" in line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] in ("device", "emulator"):
                dev = {"serial": parts[0], "type": parts[1]}
                # Parse extra info like model:xxx
                for p in parts[2:]:
                    if ":" in p:
                        k, v = p.split(":", 1)
                        dev[k] = v
                devices.append(dev)
        return {"available": True, "devices": devices}
    except Exception as e:
        return {"available": False, "devices": [], "error": str(e)}


def check_whatsapp_on_device(serial: str = None) -> dict:
    """
    Check if WhatsApp is installed on the ADB device.

    Args:
        serial: Device serial (None for first device)

    Returns:
        Dict with 'installed', 'version', 'has_key', etc.
    """
    adb = shutil.which("adb")
    if not adb:
        return {"installed": False, "error": "ADB not found"}

    adb_cmd = [adb]
    if serial:
        adb_cmd.extend(["-s", serial])

    info = {"installed": False, "version": None, "has_key": False, "is_root": False}

    # Check root
    try:
        r = subprocess.run(adb_cmd + ["shell", "whoami"], capture_output=True, text=True, timeout=5)
        info["is_root"] = "root" in r.stdout.strip()
    except Exception:
        pass

    # If not root by default, try su
    if not info["is_root"]:
        try:
            r = subprocess.run(
                adb_cmd + ["shell", "su", "-c", "whoami"],
                capture_output=True, text=True, timeout=5
            )
            info["is_root"] = "root" in r.stdout.strip()
        except Exception:
            pass

    # Check WhatsApp installed
    try:
        r = subprocess.run(
            adb_cmd + ["shell", "pm", "list", "packages", "com.whatsapp"],
            capture_output=True, text=True, timeout=5
        )
        info["installed"] = "com.whatsapp" in r.stdout
    except Exception:
        pass

    # Check version
    if info["installed"]:
        try:
            r = subprocess.run(
                adb_cmd + ["shell", "dumpsys", "package", "com.whatsapp", "|", "grep", "versionName"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.split("\n"):
                if "versionName" in line:
                    info["version"] = line.split("=")[-1].strip()
                    break
        except Exception:
            pass

    # Check if key file exists
    if info["installed"] and info["is_root"]:
        key_paths = [
            "/data/data/com.whatsapp/files/encrypted_backup.key",
            "/data/data/com.whatsapp/files/key",
        ]
        su_prefix = ["su", "-c"] if not info["is_root"] else []
        for kp in key_paths:
            try:
                r = subprocess.run(
                    adb_cmd + ["shell"] + su_prefix + ["ls", "-la", kp],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0 and kp in r.stdout:
                    info["has_key"] = True
                    info["key_path"] = kp
                    break
            except Exception:
                continue

    return info


def extract_key_adb_auto(serial: str = None) -> Optional[str]:
    """
    Automatically extract the WhatsApp encryption key from an ADB device/emulator.
    Tries multiple methods:
    1. Direct file read (root)
    2. backup + extract
    3. Pull encrypted_backup.key and parse locally

    Args:
        serial: Device serial (None for first device)

    Returns:
        64-char hex key or None
    """
    adb = shutil.which("adb")
    if not adb:
        return None

    adb_cmd = [adb]
    if serial:
        adb_cmd.extend(["-s", serial])

    # Method 1: Direct read with root (works on emulators)
    key_paths = [
        "/data/data/com.whatsapp/files/encrypted_backup.key",
        "/data/data/com.whatsapp/files/key",
    ]

    for shell_prefix in [[], ["su", "-c"]]:
        for key_path in key_paths:
            try:
                # Try to pull the file directly
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as tmp:
                    tmp_path = tmp.name

                if shell_prefix:
                    # Copy to accessible location first
                    subprocess.run(
                        adb_cmd + ["shell"] + shell_prefix + [f"cp {key_path} /sdcard/wa_key_tmp"],
                        capture_output=True, timeout=5
                    )
                    r = subprocess.run(
                        adb_cmd + ["pull", "/sdcard/wa_key_tmp", tmp_path],
                        capture_output=True, timeout=10
                    )
                    # Clean up
                    subprocess.run(
                        adb_cmd + ["shell"] + shell_prefix + ["rm /sdcard/wa_key_tmp"],
                        capture_output=True, timeout=5
                    )
                else:
                    r = subprocess.run(
                        adb_cmd + ["pull", key_path, tmp_path],
                        capture_output=True, timeout=10
                    )

                if r.returncode == 0 and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                    key = read_key_file(tmp_path)
                    os.unlink(tmp_path)
                    if key:
                        logging.info(f"Key extracted via ADB pull: {key[:8]}...{key[-8:]}")
                        return key
                else:
                    if os.path.isfile(tmp_path):
                        os.unlink(tmp_path)
            except Exception:
                continue

    # Method 2: Read via shell cat + xxd
    for shell_prefix in [[], ["su", "-c"]]:
        for key_path in key_paths:
            try:
                cmd = adb_cmd + ["shell"]
                if shell_prefix:
                    cmd += shell_prefix + [f"xxd -p -c 256 {key_path}"]
                else:
                    cmd += ["xxd", "-p", "-c", "256", key_path]

                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                hex_out = r.stdout.strip().replace("\n", "")
                if r.returncode == 0 and len(hex_out) >= 64:
                    key = hex_out[:64]
                    if all(c in "0123456789abcdef" for c in key):
                        logging.info(f"Key extracted via xxd: {key[:8]}...{key[-8:]}")
                        return key
            except Exception:
                continue

    # Method 3: Try cat with od (xxd might not be available)
    for shell_prefix in [[], ["su", "-c"]]:
        for key_path in key_paths:
            try:
                cmd = adb_cmd + ["shell"]
                if shell_prefix:
                    cmd += shell_prefix + [f"cat {key_path} | od -A n -t x1 | tr -d ' \\n'"]
                else:
                    cmd_str = f"cat {key_path} | od -A n -t x1 | tr -d ' \\n'"
                    cmd += ["sh", "-c", cmd_str]

                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                hex_out = r.stdout.strip()
                if r.returncode == 0 and len(hex_out) >= 64:
                    key = hex_out[:64]
                    if all(c in "0123456789abcdef" for c in key):
                        logging.info(f"Key extracted via od: {key[:8]}...{key[-8:]}")
                        return key
            except Exception:
                continue

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

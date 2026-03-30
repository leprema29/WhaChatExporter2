"""
Google Drive WhatsApp backup extractor.
Downloads WhatsApp backup files from Google Drive using OAuth authentication.

This is how forensic tools (UFED Cloud, Oxygen Cloud) access WhatsApp data:
they authenticate to Google Drive and download the backup files stored there.

Flow:
1. User authenticates via Google OAuth (browser-based)
2. Tool lists all WhatsApp backup files on Google Drive
3. User selects which backups to download
4. Tool downloads the encrypted .crypt14/.crypt15 files
5. User provides key (emulator method, manual, etc.) to decrypt

Requires: pip install google-auth google-auth-oauthlib google-api-python-client
"""

import os
import io
import json
import logging
import time
from typing import Optional, List, Dict
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False


# Google Drive API scope for WhatsApp backups
# WhatsApp uses the appDataFolder (hidden app data)
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.appdata",
]

# Default OAuth client config for desktop app
# Users can also provide their own client_secret.json
DEFAULT_CLIENT_CONFIG = {
    "installed": {
        "client_id": "",
        "client_secret": "",
        "redirect_uris": ["http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

TOKEN_FILE = "google_drive_token.json"


class CloudExtractor:
    """
    Extracts WhatsApp backups from Google Drive.
    """

    def __init__(self, client_secret_path: Optional[str] = None):
        """
        Initialize the extractor.

        Args:
            client_secret_path: Path to Google OAuth client_secret.json.
                              Get one from: https://console.cloud.google.com/apis/credentials
        """
        if not _HAS_GOOGLE:
            raise ImportError(
                "Google Drive extraction requires these packages:\n"
                "  pip install google-auth google-auth-oauthlib google-api-python-client\n"
            )
        self.client_secret_path = client_secret_path
        self.creds = None
        self.service = None

    def authenticate(self, token_path: str = TOKEN_FILE) -> bool:
        """
        Authenticate with Google OAuth.
        Opens a browser window for the user to log in.

        Args:
            token_path: Path to save/load the OAuth token

        Returns:
            True if authentication succeeded
        """
        self.creds = None

        # Load existing token
        if os.path.isfile(token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                pass

        # Refresh or get new token
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None

            if not self.creds:
                if not self.client_secret_path or not os.path.isfile(self.client_secret_path):
                    logging.error(
                        "Google OAuth client_secret.json required.\n"
                        "Get one from: https://console.cloud.google.com/apis/credentials\n"
                        "  1. Create a project\n"
                        "  2. Enable Google Drive API\n"
                        "  3. Create OAuth 2.0 Client ID (Desktop app)\n"
                        "  4. Download client_secret.json\n"
                        "  5. Provide the path with --google-secret"
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_path, SCOPES
                )
                self.creds = flow.run_local_server(port=8090, open_browser=True)

            # Save token for reuse
            with open(token_path, "w") as f:
                f.write(self.creds.to_json())
            logging.info(f"Token saved to {token_path}")

        self.service = build("drive", "v3", credentials=self.creds)
        logging.info("Google Drive authentication successful!")
        return True

    def list_whatsapp_backups(self) -> List[Dict]:
        """
        List all WhatsApp backup files on Google Drive.

        Returns:
            List of file info dicts with id, name, size, date
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        backups = []

        # Search in regular Drive files
        queries = [
            # WhatsApp database backups
            "name contains 'msgstore' and name contains 'crypt'",
            # WhatsApp key files
            "name contains 'encrypted_backup' or name = 'key'",
            # WhatsApp backup metadata
            "name contains 'whatsapp' and name contains 'backup'",
        ]

        for query in queries:
            try:
                results = self.service.files().list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, size, modifiedTime, mimeType)",
                    orderBy="modifiedTime desc",
                    pageSize=100,
                ).execute()

                for f in results.get("files", []):
                    backups.append({
                        "id": f["id"],
                        "name": f["name"],
                        "size": int(f.get("size", 0)),
                        "date": f.get("modifiedTime", ""),
                        "mime": f.get("mimeType", ""),
                        "source": "drive",
                    })
            except Exception as e:
                logging.debug(f"Query failed: {query} - {e}")

        # Search in appDataFolder (hidden WhatsApp data)
        try:
            results = self.service.files().list(
                spaces="appDataFolder",
                fields="files(id, name, size, modifiedTime, mimeType)",
                orderBy="modifiedTime desc",
                pageSize=100,
            ).execute()

            for f in results.get("files", []):
                backups.append({
                    "id": f["id"],
                    "name": f["name"],
                    "size": int(f.get("size", 0)),
                    "date": f.get("modifiedTime", ""),
                    "mime": f.get("mimeType", ""),
                    "source": "appData",
                })
        except Exception as e:
            logging.debug(f"appDataFolder access failed: {e}")

        # Deduplicate
        seen = set()
        unique = []
        for b in backups:
            key = (b["name"], b["size"])
            if key not in seen:
                seen.add(key)
                unique.append(b)

        logging.info(f"Found {len(unique)} WhatsApp backup file(s) on Google Drive")
        return unique

    def download_file(self, file_id: str, output_path: str, file_name: str = "") -> bool:
        """
        Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID
            output_path: Local path to save the file
            file_name: Display name for logging

        Returns:
            True if download succeeded
        """
        if not self.service:
            raise RuntimeError("Not authenticated.")

        try:
            request = self.service.files().get_media(fileId=file_id)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            with open(output_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        pct = int(status.progress() * 100)
                        logging.info(
                            f"Downloading {file_name}: {pct}%",
                            extra={"clear": True}
                        )

            size = os.path.getsize(output_path)
            logging.info(f"Downloaded: {file_name} ({size:,} bytes)")
            return True

        except Exception as e:
            logging.error(f"Download failed for {file_name}: {e}")
            return False

    def download_all_backups(self, output_dir: str = "gdrive_backups") -> List[str]:
        """
        Download all WhatsApp backup files to a local directory.

        Args:
            output_dir: Directory to save downloaded files

        Returns:
            List of downloaded file paths
        """
        backups = self.list_whatsapp_backups()
        if not backups:
            logging.warning("No WhatsApp backups found on Google Drive.")
            return []

        os.makedirs(output_dir, exist_ok=True)
        downloaded = []

        for backup in backups:
            # Skip very small files that aren't actual backups
            if backup["size"] < 100 and "crypt" not in backup["name"]:
                continue

            output_path = os.path.join(output_dir, backup["name"])

            # Skip if already downloaded
            if os.path.isfile(output_path) and os.path.getsize(output_path) == backup["size"]:
                logging.info(f"Already downloaded: {backup['name']}")
                downloaded.append(output_path)
                continue

            if self.download_file(backup["id"], output_path, backup["name"]):
                downloaded.append(output_path)

        logging.info(f"Downloaded {len(downloaded)} file(s) to {output_dir}/")
        return downloaded


def interactive_cloud_extraction(
    client_secret: Optional[str] = None,
    output_dir: str = "gdrive_backups"
) -> List[str]:
    """
    Interactive cloud extraction flow.

    Args:
        client_secret: Path to Google OAuth client_secret.json
        output_dir: Directory for downloaded files

    Returns:
        List of downloaded file paths
    """
    if not _HAS_GOOGLE:
        print("\n  Google Drive extraction requires these packages:")
        print("  pip install google-auth google-auth-oauthlib google-api-python-client\n")
        return []

    extractor = CloudExtractor(client_secret)

    print("\n  Google Drive WhatsApp Backup Extraction")
    print("  " + "=" * 45)
    print("  Your browser will open for Google login.\n")

    if not extractor.authenticate():
        return []

    backups = extractor.list_whatsapp_backups()
    if not backups:
        print("\n  No WhatsApp backups found on your Google Drive.")
        return []

    print(f"\n  Found {len(backups)} file(s):\n")
    for i, b in enumerate(backups):
        size_mb = b["size"] / (1024 * 1024)
        date = b["date"][:10] if b["date"] else "unknown"
        print(f"    {i+1}. {b['name']} ({size_mb:.1f} MB, {date}) [{b['source']}]")

    print(f"\n    a. Download all")
    print(f"    q. Cancel\n")

    choice = input("  Select files (e.g. 1,3 or 'a' for all): ").strip().lower()
    if choice == "q":
        return []

    if choice == "a":
        selected = backups
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            selected = [backups[i] for i in indices if 0 <= i < len(backups)]
        except (ValueError, IndexError):
            print("  Invalid selection.")
            return []

    downloaded = []
    os.makedirs(output_dir, exist_ok=True)
    for backup in selected:
        output_path = os.path.join(output_dir, backup["name"])
        if extractor.download_file(backup["id"], output_path, backup["name"]):
            downloaded.append(output_path)

    print(f"\n  Downloaded {len(downloaded)} file(s) to {output_dir}/")
    return downloaded

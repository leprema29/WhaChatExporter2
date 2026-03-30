"""
Multi-database comparator for WhatsApp Chat Exporter.
Compares multiple msgstore.db files to detect deleted messages
and merge them into a complete history.
"""

import os
import sqlite3
import logging
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field, asdict
from tqdm import tqdm
from Whatsapp_Chat_Exporter.utility import convert_time_unit, safe_name


@dataclass
class ComparedMessage:
    """A message found during comparison."""
    key_id: str
    chat_jid: str
    timestamp: int
    from_me: bool
    text: Optional[str]
    sender: Optional[str] = None
    found_in: List[str] = field(default_factory=list)
    deleted_from: List[str] = field(default_factory=list)
    is_deleted: bool = False


@dataclass
class ComparisonReport:
    """Report of database comparison."""
    total_unique_messages: int = 0
    total_deleted_messages: int = 0
    total_chats: int = 0
    databases_compared: List[str] = field(default_factory=list)
    deleted_messages: List[ComparedMessage] = field(default_factory=list)
    chats_with_deletions: Dict[str, int] = field(default_factory=dict)


class DatabaseComparator:
    """
    Compares multiple WhatsApp msgstore.db databases to find
    messages that were deleted between backups.
    """

    def __init__(self):
        self.databases: List[Tuple[str, str]] = []  # (path, label)
        self._messages: Dict[str, Dict[str, ComparedMessage]] = {}  # chat -> {key_id -> msg}
        self._db_message_keys: Dict[str, Set[str]] = {}  # db_label -> set of key_ids

    def add_database(self, db_path: str, label: Optional[str] = None) -> None:
        """
        Add a database to compare.

        Args:
            db_path: Path to the msgstore.db file
            label: Optional label (defaults to filename)
        """
        if not os.path.isfile(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")

        if label is None:
            label = os.path.basename(db_path)
            # Add index if duplicate
            existing_labels = [l for _, l in self.databases]
            if label in existing_labels:
                label = f"{label}_{len(self.databases)}"

        self.databases.append((db_path, label))
        logging.info(f"Added database: {label} ({db_path})")

    def _load_messages_from_db(self, db_path: str) -> Dict[str, Dict[str, dict]]:
        """
        Load all messages from a database.

        Returns:
            Dict of chat_jid -> {key_id -> message_info}
        """
        messages = {}

        with sqlite3.connect(db_path) as db:
            db.row_factory = sqlite3.Row

            # Try new schema first
            try:
                cursor = db.execute("""
                    SELECT
                        COALESCE(jid.raw_string, '') as chat_jid,
                        message.key_id,
                        message.timestamp,
                        message.from_me,
                        message.text_data as data,
                        message.message_type,
                        chat.subject as chat_name,
                        jid_sender.raw_string as sender_jid
                    FROM message
                        LEFT JOIN chat ON chat._id = message.chat_row_id
                        INNER JOIN jid ON jid._id = chat.jid_row_id
                        LEFT JOIN jid jid_sender ON jid_sender._id = message.sender_jid_row_id
                    ORDER BY message.timestamp ASC
                """)
            except sqlite3.OperationalError:
                # Legacy schema
                cursor = db.execute("""
                    SELECT
                        key_remote_jid as chat_jid,
                        key_id,
                        timestamp,
                        key_from_me as from_me,
                        data,
                        media_wa_type as message_type,
                        NULL as chat_name,
                        remote_resource as sender_jid
                    FROM messages
                    WHERE key_remote_jid != '-1'
                    ORDER BY timestamp ASC
                """)

            for row in cursor:
                chat_jid = row["chat_jid"] or ""
                key_id = row["key_id"]

                if not key_id:
                    continue

                if chat_jid not in messages:
                    messages[chat_jid] = {}

                messages[chat_jid][key_id] = {
                    "key_id": key_id,
                    "chat_jid": chat_jid,
                    "timestamp": row["timestamp"],
                    "from_me": bool(row["from_me"]),
                    "text": row["data"],
                    "sender": row["sender_jid"],
                    "chat_name": row["chat_name"],
                    "message_type": row["message_type"],
                }

        return messages

    def compare(self) -> ComparisonReport:
        """
        Compare all added databases and generate a report.

        The comparison works by:
        1. Loading all messages from each database
        2. Building a union of all unique messages (by key_id)
        3. Checking which messages exist in which databases
        4. Messages present in older DBs but missing from newer ones = deleted

        Returns:
            ComparisonReport with findings
        """
        if len(self.databases) < 2:
            raise ValueError("At least 2 databases are required for comparison")

        report = ComparisonReport()
        report.databases_compared = [label for _, label in self.databases]

        # Step 1: Load all databases
        all_db_messages = {}
        db_timestamps = {}  # Track "age" of each DB by its newest message

        logging.info(f"Loading {len(self.databases)} databases for comparison...")

        for db_path, label in self.databases:
            logging.info(f"Loading {label}...", extra={"clear": True})
            try:
                messages = self._load_messages_from_db(db_path)
                all_db_messages[label] = messages

                # Find newest timestamp to determine DB age
                max_ts = 0
                total_msgs = 0
                for chat_msgs in messages.values():
                    total_msgs += len(chat_msgs)
                    for msg in chat_msgs.values():
                        ts = msg["timestamp"] or 0
                        if ts > max_ts:
                            max_ts = ts

                db_timestamps[label] = max_ts
                logging.info(f"Loaded {label}: {total_msgs} messages, newest: {datetime.fromtimestamp(max_ts / 1000 if max_ts > 9999999999 else max_ts)}")

                # Track all key_ids per DB
                all_keys = set()
                for chat_msgs in messages.values():
                    all_keys.update(chat_msgs.keys())
                self._db_message_keys[label] = all_keys

            except Exception as e:
                logging.error(f"Failed to load {label}: {e}")
                continue

        # Use addition order (user provides oldest first) as primary ordering
        # Fall back to timestamp-based ordering if all timestamps differ
        sorted_dbs = [label for _, label in self.databases if label in all_db_messages]
        logging.info(f"Database order (oldest to newest): {' -> '.join(sorted_dbs)}")

        # Step 2: Build union of all messages per chat
        all_chats: Dict[str, Dict[str, ComparedMessage]] = {}

        for label in sorted_dbs:
            messages = all_db_messages[label]
            for chat_jid, chat_msgs in messages.items():
                if chat_jid not in all_chats:
                    all_chats[chat_jid] = {}

                for key_id, msg_data in chat_msgs.items():
                    if key_id not in all_chats[chat_jid]:
                        all_chats[chat_jid][key_id] = ComparedMessage(
                            key_id=key_id,
                            chat_jid=chat_jid,
                            timestamp=msg_data["timestamp"],
                            from_me=msg_data["from_me"],
                            text=msg_data["text"],
                            sender=msg_data.get("sender"),
                            found_in=[label],
                        )
                    else:
                        all_chats[chat_jid][key_id].found_in.append(label)
                        # Prefer text from later DB (might have edits)
                        if msg_data["text"]:
                            all_chats[chat_jid][key_id].text = msg_data["text"]

        # Step 3: Detect deletions using index-based ordering
        # Databases are ordered oldest-first as provided by the user
        newest_db = sorted_dbs[-1]
        db_order = {label: idx for idx, label in enumerate(sorted_dbs)}

        total_unique = 0
        total_deleted = 0

        with tqdm(total=len(all_chats), desc="Comparing chats", unit="chat", leave=False) as pbar:
            for chat_jid, chat_msgs in all_chats.items():
                chat_deletions = 0

                for key_id, msg in chat_msgs.items():
                    total_unique += 1

                    # A message is "deleted" if it exists in an older DB
                    # but is missing from a newer DB (by addition order)
                    oldest_found_idx = min(db_order[l] for l in msg.found_in)
                    missing_from = []
                    for db_label in sorted_dbs:
                        if db_label not in msg.found_in and db_order[db_label] > oldest_found_idx:
                            missing_from.append(db_label)

                    if missing_from and newest_db in missing_from:
                        msg.is_deleted = True
                        msg.deleted_from = missing_from
                        report.deleted_messages.append(msg)
                        total_deleted += 1
                        chat_deletions += 1

                if chat_deletions > 0:
                    # Get chat name
                    chat_name = chat_jid
                    for label in sorted_dbs:
                        if chat_jid in all_db_messages.get(label, {}):
                            for msg_data in all_db_messages[label][chat_jid].values():
                                if msg_data.get("chat_name"):
                                    chat_name = msg_data["chat_name"]
                                    break
                            if chat_name != chat_jid:
                                break

                    report.chats_with_deletions[chat_name] = chat_deletions

                pbar.update(1)

        report.total_unique_messages = total_unique
        report.total_deleted_messages = total_deleted
        report.total_chats = len(all_chats)

        self._messages = all_chats

        return report

    def batch_decrypt(self, encrypted_paths: List[str], key: str, output_dir: str = ".") -> List[str]:
        """
        Decrypt multiple encrypted backup files using the same key.

        Args:
            encrypted_paths: List of paths to .crypt12/.crypt14/.crypt15 files
            key: Hex key string (64 chars) or path to key file
            output_dir: Directory for decrypted files

        Returns:
            List of paths to decrypted database files
        """
        import string as string_module
        from Whatsapp_Chat_Exporter.utility import Crypt, DbType
        from Whatsapp_Chat_Exporter import android_crypt

        os.makedirs(output_dir, exist_ok=True)
        decrypted_paths = []

        # Determine if key is hex string or file
        key_is_hex = not os.path.isfile(key) and all(
            c in string_module.hexdigits for c in key.replace(" ", "")
        )

        if key_is_hex:
            key_bytes = bytes.fromhex(key.replace(" ", ""))
            keyfile_stream = False
        else:
            key_bytes = open(key, "rb").read()
            keyfile_stream = True

        for i, enc_path in enumerate(encrypted_paths):
            if not os.path.isfile(enc_path):
                logging.warning(f"File not found, skipping: {enc_path}")
                continue

            # Determine crypt type
            if "crypt12" in enc_path:
                crypt = Crypt.CRYPT12
            elif "crypt14" in enc_path:
                crypt = Crypt.CRYPT14
            elif "crypt15" in enc_path:
                crypt = Crypt.CRYPT15
            else:
                logging.warning(f"Unknown format, skipping: {enc_path}")
                continue

            # Output path
            base_name = os.path.basename(enc_path)
            out_name = f"decrypted_{i}_{base_name.split('.')[0]}.db"
            out_path = os.path.join(output_dir, out_name)

            logging.info(f"Decrypting {base_name}...", extra={"clear": True})

            try:
                db_data = open(enc_path, "rb").read()

                # For crypt15 with hex key, need to handle key properly
                if key_is_hex:
                    key_to_use = key_bytes
                else:
                    key_to_use = key_bytes

                android_crypt.decrypt_backup(
                    db_data,
                    key_to_use,
                    out_path,
                    crypt,
                    False,
                    DbType.MESSAGE,
                    keyfile_stream=keyfile_stream,
                )
                decrypted_paths.append(out_path)
                logging.info(f"Decrypted: {base_name} -> {out_name}")
            except Exception as e:
                logging.error(f"Failed to decrypt {base_name}: {e}")

        return decrypted_paths

    def merge_to_collection(self) -> 'ChatCollection':
        """
        After compare(), merge all messages into a ChatCollection
        with is_deleted flags set on recovered messages.

        Returns:
            ChatCollection with all messages, deleted ones marked
        """
        from Whatsapp_Chat_Exporter.data_model import ChatCollection, ChatStore, Message, Timing

        if not self._messages:
            raise ValueError("Run compare() first")

        data = ChatCollection()
        timing = Timing(0)

        for chat_jid, chat_msgs in self._messages.items():
            # Get chat name from any available source
            chat_name = None
            for msg in chat_msgs.values():
                if msg.sender and not msg.from_me:
                    chat_name = msg.sender
                    break
            if not chat_name and "@" in chat_jid:
                chat_name = chat_jid.split("@")[0]

            chat = ChatStore("android", chat_name)

            # Sort messages by timestamp and add them
            sorted_msgs = sorted(chat_msgs.values(), key=lambda m: m.timestamp)

            for i, comp_msg in enumerate(sorted_msgs):
                ts = comp_msg.timestamp
                msg = Message(
                    from_me=comp_msg.from_me,
                    timestamp=ts,
                    time=ts,
                    key_id=comp_msg.key_id,
                    timezone_offset=timing,
                )
                msg.data = comp_msg.text
                msg.sender = comp_msg.sender
                msg.is_deleted = comp_msg.is_deleted

                if msg.data is None:
                    msg.data = "[media/attachment]"
                    msg.meta = True

                chat.add_message(str(i), msg)

            if len(chat) > 0:
                data.add_chat(chat_jid, chat)

        total = sum(len(c) for c in data.values())
        deleted = sum(1 for c in data.values() for m in c.values() if getattr(m, 'is_deleted', False))
        logging.info(f"Merged collection: {total} messages ({deleted} recovered/deleted)")

        return data

    def print_report(self, report: ComparisonReport) -> None:
        """Print a human-readable comparison report."""
        print("\n" + "=" * 60)
        print("  WhatsApp Database Comparison Report")
        print("=" * 60)
        print(f"\n  Databases compared: {len(report.databases_compared)}")
        for db in report.databases_compared:
            print(f"    - {db}")
        print(f"\n  Total unique messages: {report.total_unique_messages}")
        print(f"  Deleted messages found: {report.total_deleted_messages}")
        print(f"  Chats analyzed: {report.total_chats}")

        if report.chats_with_deletions:
            print(f"\n  Chats with deletions:")
            for chat_name, count in sorted(report.chats_with_deletions.items(), key=lambda x: -x[1]):
                print(f"    - {chat_name}: {count} deleted message(s)")

        if report.deleted_messages:
            print(f"\n  Sample deleted messages (first 20):")
            for msg in report.deleted_messages[:20]:
                ts = msg.timestamp
                if ts > 9999999999:
                    ts = ts / 1000
                date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                sender = "You" if msg.from_me else (msg.sender or "Unknown")
                text = (msg.text or "[media]")[:60]
                text = text.replace("\n", " ")
                print(f"    [{date}] {sender}: {text}")
                print(f"      Found in: {', '.join(msg.found_in)} | Missing from: {', '.join(msg.deleted_from)}")

        print("\n" + "=" * 60)

    def export_report_json(self, report: ComparisonReport, output_path: str) -> None:
        """Export the comparison report as JSON."""
        data = {
            "databases_compared": report.databases_compared,
            "total_unique_messages": report.total_unique_messages,
            "total_deleted_messages": report.total_deleted_messages,
            "total_chats": report.total_chats,
            "chats_with_deletions": report.chats_with_deletions,
            "deleted_messages": [
                {
                    "key_id": m.key_id,
                    "chat": m.chat_jid,
                    "timestamp": m.timestamp,
                    "date": datetime.fromtimestamp(
                        m.timestamp / 1000 if m.timestamp > 9999999999 else m.timestamp
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "from_me": m.from_me,
                    "sender": m.sender,
                    "text": m.text,
                    "found_in": m.found_in,
                    "deleted_from": m.deleted_from,
                }
                for m in report.deleted_messages
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logging.info(f"Comparison report saved to: {output_path}")

    def export_deleted_messages_txt(self, report: ComparisonReport, output_path: str) -> None:
        """Export deleted messages as a readable text file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("DELETED MESSAGES REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Databases: {', '.join(report.databases_compared)}\n")
            f.write(f"Total deleted: {report.total_deleted_messages}\n")
            f.write("=" * 60 + "\n\n")

            # Group by chat
            by_chat: Dict[str, List[ComparedMessage]] = {}
            for msg in report.deleted_messages:
                if msg.chat_jid not in by_chat:
                    by_chat[msg.chat_jid] = []
                by_chat[msg.chat_jid].append(msg)

            for chat_jid, messages in sorted(by_chat.items()):
                chat_name = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
                f.write(f"\n--- {chat_name} ({len(messages)} deleted) ---\n\n")

                for msg in sorted(messages, key=lambda m: m.timestamp):
                    ts = msg.timestamp
                    if ts > 9999999999:
                        ts = ts / 1000
                    date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    sender = "You" if msg.from_me else (msg.sender or chat_name)
                    if "@" in sender:
                        sender = sender.split("@")[0]
                    text = (msg.text or "[media/attachment]").replace("\n", "\n    ")
                    f.write(f"[{date}] {sender}: {text}\n")
                    f.write(f"  (was in: {', '.join(msg.found_in)})\n\n")

        logging.info(f"Deleted messages exported to: {output_path}")


def compare_databases_interactive(
    db_paths: List[str],
    output_dir: str = "comparison_result",
    key: Optional[str] = None,
) -> ComparisonReport:
    """
    Compare multiple databases interactively.
    Supports both decrypted .db files and encrypted .crypt* files (with key).

    Args:
        db_paths: List of paths to msgstore.db or .crypt* files
        output_dir: Directory for output files
        key: Optional encryption key (hex string or key file path) for encrypted backups

    Returns:
        ComparisonReport
    """
    comparator = DatabaseComparator()

    # Check if any files are encrypted
    encrypted = [p for p in db_paths if any(x in p for x in ["crypt12", "crypt14", "crypt15"])]
    decrypted = [p for p in db_paths if p not in encrypted]

    if encrypted:
        if not key:
            logging.error(
                "Encrypted backup files detected but no key provided. "
                "Use -k to specify the encryption key."
            )
            raise ValueError("Key required for encrypted backups")

        decrypt_dir = os.path.join(output_dir, "_decrypted")
        decrypted_from_enc = comparator.batch_decrypt(encrypted, key, decrypt_dir)
        decrypted.extend(decrypted_from_enc)

    for path in decrypted:
        comparator.add_database(path)

    report = comparator.compare()
    comparator.print_report(report)

    # Save outputs
    os.makedirs(output_dir, exist_ok=True)
    comparator.export_report_json(report, os.path.join(output_dir, "comparison_report.json"))

    if report.deleted_messages:
        comparator.export_deleted_messages_txt(report, os.path.join(output_dir, "deleted_messages.txt"))

    return report

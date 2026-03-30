"""Tests for db_comparator.py."""
import os
import sqlite3
import tempfile
import pytest
from Whatsapp_Chat_Exporter.db_comparator import DatabaseComparator, ComparisonReport


def _create_test_db(path, messages):
    """Create a minimal msgstore.db with the given messages.
    messages: list of (key_id, chat_jid, timestamp, from_me, text)
    """
    with sqlite3.connect(path) as db:
        # Create minimal schema (legacy style for simplicity)
        db.execute("""
            CREATE TABLE messages (
                _id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_remote_jid TEXT,
                key_id TEXT,
                timestamp INTEGER,
                key_from_me INTEGER,
                data TEXT,
                media_wa_type INTEGER DEFAULT 0,
                remote_resource TEXT
            )
        """)
        for key_id, chat_jid, ts, from_me, text in messages:
            db.execute(
                "INSERT INTO messages (key_remote_jid, key_id, timestamp, key_from_me, data) VALUES (?, ?, ?, ?, ?)",
                (chat_jid, key_id, ts, int(from_me), text)
            )
        db.commit()


class TestDatabaseComparator:
    def test_detect_deleted_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1_path = os.path.join(tmpdir, "old.db")
            db2_path = os.path.join(tmpdir, "new.db")

            # Old DB has 3 messages
            _create_test_db(db1_path, [
                ("msg1", "user@s.whatsapp.net", 1000000, False, "Hello"),
                ("msg2", "user@s.whatsapp.net", 2000000, True, "Hi there"),
                ("msg3", "user@s.whatsapp.net", 3000000, False, "Secret message"),
            ])
            # New DB is missing msg3 (deleted)
            _create_test_db(db2_path, [
                ("msg1", "user@s.whatsapp.net", 1000000, False, "Hello"),
                ("msg2", "user@s.whatsapp.net", 2000000, True, "Hi there"),
            ])

            comp = DatabaseComparator()
            comp.add_database(db1_path, "old_backup")
            comp.add_database(db2_path, "new_backup")
            report = comp.compare()

            assert report.total_unique_messages == 3
            assert report.total_deleted_messages == 1
            assert len(report.deleted_messages) == 1
            assert report.deleted_messages[0].text == "Secret message"
            assert report.deleted_messages[0].key_id == "msg3"
            assert "new_backup" in report.deleted_messages[0].deleted_from

    def test_no_deletions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1_path = os.path.join(tmpdir, "old.db")
            db2_path = os.path.join(tmpdir, "new.db")

            msgs = [
                ("msg1", "user@s.whatsapp.net", 1000000, False, "Hello"),
                ("msg2", "user@s.whatsapp.net", 2000000, True, "Hi"),
            ]
            _create_test_db(db1_path, msgs)
            _create_test_db(db2_path, msgs)

            comp = DatabaseComparator()
            comp.add_database(db1_path, "old")
            comp.add_database(db2_path, "new")
            report = comp.compare()

            assert report.total_deleted_messages == 0

    def test_multiple_chats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1_path = os.path.join(tmpdir, "old.db")
            db2_path = os.path.join(tmpdir, "new.db")

            _create_test_db(db1_path, [
                ("msg1", "alice@s.whatsapp.net", 1000000, False, "From Alice"),
                ("msg2", "bob@s.whatsapp.net", 2000000, False, "From Bob"),
                ("msg3", "alice@s.whatsapp.net", 3000000, False, "Deleted from Alice"),
            ])
            _create_test_db(db2_path, [
                ("msg1", "alice@s.whatsapp.net", 1000000, False, "From Alice"),
                ("msg2", "bob@s.whatsapp.net", 2000000, False, "From Bob"),
            ])

            comp = DatabaseComparator()
            comp.add_database(db1_path, "old")
            comp.add_database(db2_path, "new")
            report = comp.compare()

            assert report.total_deleted_messages == 1
            assert report.deleted_messages[0].chat_jid == "alice@s.whatsapp.net"

    def test_export_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1_path = os.path.join(tmpdir, "old.db")
            db2_path = os.path.join(tmpdir, "new.db")

            _create_test_db(db1_path, [
                ("msg1", "user@s.whatsapp.net", 1000000, False, "Kept"),
                ("msg2", "user@s.whatsapp.net", 2000000, True, "Deleted"),
            ])
            _create_test_db(db2_path, [
                ("msg1", "user@s.whatsapp.net", 1000000, False, "Kept"),
            ])

            comp = DatabaseComparator()
            comp.add_database(db1_path, "old")
            comp.add_database(db2_path, "new")
            report = comp.compare()

            # Test JSON export
            json_path = os.path.join(tmpdir, "report.json")
            comp.export_report_json(report, json_path)
            assert os.path.isfile(json_path)

            # Test TXT export
            txt_path = os.path.join(tmpdir, "deleted.txt")
            comp.export_deleted_messages_txt(report, txt_path)
            assert os.path.isfile(txt_path)
            content = open(txt_path).read()
            assert "Deleted" in content

    def test_needs_at_least_2_dbs(self):
        comp = DatabaseComparator()
        comp.add_database(__file__, "single")  # Any existing file
        with pytest.raises(ValueError, match="At least 2"):
            comp.compare()

    def test_file_not_found(self):
        comp = DatabaseComparator()
        with pytest.raises(FileNotFoundError):
            comp.add_database("/nonexistent/path.db")

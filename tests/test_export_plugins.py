"""Tests for export_plugins.py."""
import os
import csv
import tempfile
import pytest
from Whatsapp_Chat_Exporter.data_model import ChatCollection, ChatStore, Message
from Whatsapp_Chat_Exporter.export_plugins import (
    MarkdownExportPlugin, CSVExportPlugin, PDFExportPlugin, get_plugin, list_plugins
)


@pytest.fixture
def sample_data():
    data = ChatCollection()
    chat = ChatStore("android", "Test Contact")
    msg1 = Message(from_me=True, timestamp=1678838400, time="10:00", key_id="k1")
    msg1.data = "Hello there!"
    msg2 = Message(from_me=False, timestamp=1678838460, time="10:01", key_id="k2")
    msg2.data = "Hi! How are you?"
    msg2.sender = "Test Contact"
    msg3 = Message(from_me=True, timestamp=1678838520, time="10:02", key_id="k3")
    msg3.data = "I'm good"
    msg3.reactions = {"Test Contact": "\U0001f44d"}
    chat.add_message("1", msg1)
    chat.add_message("2", msg2)
    chat.add_message("3", msg3)
    data.add_chat("1234567890@s.whatsapp.net", chat)
    return data


class TestMarkdownExport:
    def test_export(self, sample_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = MarkdownExportPlugin()
            plugin.export_all(sample_data, tmpdir)
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].endswith(".md")
            content = open(os.path.join(tmpdir, files[0])).read()
            assert "Test Contact" in content
            assert "Hello there!" in content
            assert "\U0001f44d" in content


class TestCSVExport:
    def test_export(self, sample_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = CSVExportPlugin()
            plugin.export_all(sample_data, tmpdir)
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].endswith(".csv")
            with open(os.path.join(tmpdir, files[0])) as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 4  # header + 3 messages
                assert rows[0][0] == "timestamp"


def _can_import_fpdf():
    try:
        import fpdf  # noqa: F401
        return True
    except Exception:
        return False


class TestPDFExport:
    @pytest.mark.skipif(not _can_import_fpdf(), reason="fpdf2 not available in this environment")
    def test_export(self, sample_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = PDFExportPlugin()
            plugin.export_all(sample_data, tmpdir)
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].endswith(".pdf")
            path = os.path.join(tmpdir, files[0])
            with open(path, "rb") as f:
                header = f.read(5)
                assert header == b"%PDF-"

    def test_safe_text(self):
        assert PDFExportPlugin._safe_text("Hello<br>World") == "Hello\nWorld"
        assert PDFExportPlugin._safe_text("<b>bold</b>") == "bold"
        assert PDFExportPlugin._safe_text("") == ""
        assert PDFExportPlugin._safe_text(None) == ""


class TestPluginRegistry:
    def test_get_plugin_markdown(self):
        plugin = get_plugin("markdown")
        assert plugin is not None
        assert isinstance(plugin, MarkdownExportPlugin)

    def test_get_plugin_csv(self):
        plugin = get_plugin("csv")
        assert plugin is not None
        assert isinstance(plugin, CSVExportPlugin)

    def test_get_plugin_pdf(self):
        plugin = get_plugin("pdf")
        assert plugin is not None
        assert isinstance(plugin, PDFExportPlugin)

    def test_get_plugin_unknown(self):
        assert get_plugin("unknown_format") is None

    def test_list_plugins(self):
        plugins = list_plugins()
        assert "Markdown" in plugins
        assert "CSV" in plugins
        assert "PDF" in plugins

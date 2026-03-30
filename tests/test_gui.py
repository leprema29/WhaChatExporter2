"""Tests for gui.py."""
import pytest


class TestGUIImport:
    def test_gui_module_imports(self):
        """Test that the GUI module can be imported."""
        from Whatsapp_Chat_Exporter import gui
        assert hasattr(gui, 'create_app')
        assert hasattr(gui, 'main')
        assert hasattr(gui, 'GUI_TEMPLATE')

    def test_gui_template_has_key_elements(self):
        """Test that the GUI template contains key UI elements."""
        from Whatsapp_Chat_Exporter.gui import GUI_TEMPLATE
        assert "WhatsApp Chat Exporter" in GUI_TEMPLATE
        assert "android" in GUI_TEMPLATE
        assert "ios" in GUI_TEMPLATE
        assert "exported" in GUI_TEMPLATE
        assert "Start Export" in GUI_TEMPLATE
        assert "PDF" in GUI_TEMPLATE
        assert "Markdown" in GUI_TEMPLATE
        assert "CSV" in GUI_TEMPLATE
        assert "Anonymize" in GUI_TEMPLATE
        assert "Overview Page" in GUI_TEMPLATE

    def test_create_app(self):
        """Test Flask app creation (only if flask is installed)."""
        flask = pytest.importorskip("flask")
        from Whatsapp_Chat_Exporter.gui import create_app
        app = create_app()
        assert app is not None
        client = app.test_client()
        response = client.get('/')
        assert response.status_code == 200
        assert b"WhatsApp Chat Exporter" in response.data

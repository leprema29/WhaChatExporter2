"""Tests for anonymizer.py."""
import pytest
from Whatsapp_Chat_Exporter.data_model import ChatCollection, ChatStore, Message
from Whatsapp_Chat_Exporter.anonymizer import Anonymizer


@pytest.fixture
def sample_data():
    data = ChatCollection()
    chat = ChatStore("android", "John Doe")
    chat.their_avatar = "/path/to/avatar.jpg"
    chat.status = "Available"
    msg1 = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
    msg1.data = "Call me at +1234567890"
    msg2 = Message(from_me=False, timestamp=2000, time="11:00", key_id="k2")
    msg2.data = "Sure, my number is 555-123-4567"
    msg2.sender = "John Doe"
    msg2.reactions = {"John Doe": "\U0001f44d"}
    chat.add_message("1", msg1)
    chat.add_message("2", msg2)
    data.add_chat("1234567890@s.whatsapp.net", chat)
    return data


class TestAnonymizer:
    def test_anonymize_names(self, sample_data):
        anon = Anonymizer()
        anon.anonymize(sample_data)
        chat = sample_data.get_chat("1234567890@s.whatsapp.net")
        assert chat.name != "John Doe"
        assert chat.name.startswith("Contact_")

    def test_anonymize_removes_avatars(self, sample_data):
        anon = Anonymizer()
        anon.anonymize(sample_data)
        chat = sample_data.get_chat("1234567890@s.whatsapp.net")
        assert chat.their_avatar is None
        assert chat.status is None

    def test_anonymize_phone_in_text(self, sample_data):
        anon = Anonymizer()
        anon.anonymize(sample_data)
        chat = sample_data.get_chat("1234567890@s.whatsapp.net")
        for msg in chat.values():
            if msg.data:
                assert "+1234567890" not in msg.data
                assert "555-123-4567" not in msg.data

    def test_anonymize_reactions(self, sample_data):
        anon = Anonymizer()
        anon.anonymize(sample_data)
        chat = sample_data.get_chat("1234567890@s.whatsapp.net")
        msg2 = chat.get_message("2")
        assert "John Doe" not in msg2.reactions

    def test_you_preserved(self, sample_data):
        """'You' should not be anonymized."""
        chat = sample_data.get_chat("1234567890@s.whatsapp.net")
        msg = Message(from_me=True, timestamp=3000, time="12:00", key_id="k3")
        msg.sender = "You"
        chat.add_message("3", msg)
        anon = Anonymizer()
        anon.anonymize(sample_data)
        # "You" should remain
        msg3 = chat.get_message("3")
        assert msg3.sender == "You"

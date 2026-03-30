"""Tests for data_model.py - covering ChatCollection, ChatStore, Message, Timing, TimeZone."""
import pytest
from Whatsapp_Chat_Exporter.data_model import (
    Timing, TimeZone, ChatCollection, ChatStore, Message
)


class TestTimeZone:
    def test_utcoffset(self):
        tz = TimeZone(5)
        from datetime import timedelta
        assert tz.utcoffset(None) == timedelta(hours=5)

    def test_dst(self):
        tz = TimeZone(0)
        from datetime import timedelta
        assert tz.dst(None) == timedelta(0)

    def test_none_offset_defaults_to_zero(self):
        """Fix for issue #205 - timezone_offset can be None."""
        tz = TimeZone(None)
        from datetime import timedelta
        assert tz.utcoffset(None) == timedelta(hours=0)

    def test_negative_offset(self):
        tz = TimeZone(-5)
        from datetime import timedelta
        assert tz.utcoffset(None) == timedelta(hours=-5)


class TestTiming:
    def test_format_timestamp(self):
        t = Timing(0)
        result = t.format_timestamp(1678838400, "%Y-%m-%d")
        assert result is not None
        assert "2023" in result

    def test_format_timestamp_none(self):
        t = Timing(0)
        assert t.format_timestamp(None, "%Y-%m-%d") is None

    def test_format_timestamp_milliseconds(self):
        t = Timing(0)
        result = t.format_timestamp(1678838400000, "%Y-%m-%d")
        assert result is not None

    def test_none_timezone_offset(self):
        """Fix for issue #205."""
        t = Timing(None)
        result = t.format_timestamp(1678838400, "%Y-%m-%d")
        assert result is not None


class TestChatCollection:
    def test_add_and_get_chat(self):
        cc = ChatCollection()
        chat = ChatStore("android", "Test Chat")
        cc.add_chat("123@s.whatsapp.net", chat)
        assert cc.get_chat("123@s.whatsapp.net") is not None
        assert cc.get_chat("123@s.whatsapp.net").name == "Test Chat"

    def test_len(self):
        cc = ChatCollection()
        assert len(cc) == 0
        cc.add_chat("a@s.whatsapp.net", ChatStore("android"))
        assert len(cc) == 1

    def test_remove_chat(self):
        cc = ChatCollection()
        cc.add_chat("a@s.whatsapp.net", ChatStore("android"))
        cc.remove_chat("a@s.whatsapp.net")
        assert len(cc) == 0

    def test_remove_nonexistent(self):
        cc = ChatCollection()
        cc.remove_chat("nonexistent")  # Should not raise

    def test_setitem_type_check(self):
        cc = ChatCollection()
        with pytest.raises(TypeError):
            cc["key"] = "not a ChatStore"

    def test_iter(self):
        cc = ChatCollection()
        cc.add_chat("a", ChatStore("android"))
        cc.add_chat("b", ChatStore("android"))
        keys = list(cc)
        assert "a" in keys
        assert "b" in keys

    def test_to_dict(self):
        cc = ChatCollection()
        cc.add_chat("a", ChatStore("android", "Chat A"))
        result = cc.to_dict()
        assert "a" in result
        assert result["a"]["name"] == "Chat A"

    def test_system_values(self):
        cc = ChatCollection()
        cc.set_system("key", "value")
        assert cc.get_system("key") == "value"
        assert cc.get_system("missing") is None


class TestChatStore:
    def test_create(self):
        cs = ChatStore("android", "Test")
        assert cs.name == "Test"
        assert cs.type == "android"

    def test_add_message(self):
        cs = ChatStore("android")
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        cs.add_message("1", msg)
        assert len(cs) == 1

    def test_add_message_type_check(self):
        cs = ChatStore("android")
        with pytest.raises(TypeError):
            cs.add_message("1", "not a message")

    def test_name_type_check(self):
        with pytest.raises(TypeError):
            ChatStore("android", name=123)

    def test_delete_message(self):
        cs = ChatStore("android")
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        cs.add_message("1", msg)
        cs.delete_message("1")
        assert len(cs) == 0

    def test_to_json_roundtrip(self):
        cs = ChatStore("android", "Test Chat")
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        msg.data = "Hello"
        cs.add_message("1", msg)

        json_data = cs.to_json()
        restored = ChatStore.from_json(json_data)
        assert restored.name == "Test Chat"
        assert len(restored) == 1

    def test_merge_with(self):
        cs1 = ChatStore("android", "Chat 1")
        cs2 = ChatStore("android", "Chat 2")
        msg1 = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        msg2 = Message(from_me=False, timestamp=2000, time="11:00", key_id="k2")
        cs1.add_message("1", msg1)
        cs2.add_message("2", msg2)
        cs1.merge_with(cs2)
        assert len(cs1) == 2
        assert cs1.name == "Chat 2"

    def test_merge_type_check(self):
        cs = ChatStore("android")
        with pytest.raises(TypeError):
            cs.merge_with("not a ChatStore")

    def test_get_last_message(self):
        cs = ChatStore("android")
        msg1 = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        msg2 = Message(from_me=True, timestamp=2000, time="11:00", key_id="k2")
        cs.add_message("1", msg1)
        cs.add_message("2", msg2)
        assert cs.get_last_message().key_id == "k2"


class TestMessage:
    def test_create(self):
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        assert msg.from_me is True
        assert msg.data is None

    def test_from_me_coercion(self):
        msg = Message(from_me=1, timestamp=1000, time="10:00", key_id="k1")
        assert msg.from_me is True
        msg2 = Message(from_me=0, timestamp=1000, time="10:00", key_id="k2")
        assert msg2.from_me is False

    def test_timestamp_millisecond_conversion(self):
        msg = Message(from_me=True, timestamp=1678838400000, time="10:00", key_id="k1")
        assert msg.timestamp == 1678838400

    def test_time_as_int(self):
        msg = Message(from_me=True, timestamp=1678838400, time=1678838400, key_id="k1")
        assert msg.time is not None

    def test_time_invalid_type(self):
        with pytest.raises(TypeError):
            Message(from_me=True, timestamp=1000, time=[1, 2, 3], key_id="k1")

    def test_reactions(self):
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        msg.reactions["Alice"] = "\U0001f44d"
        assert "Alice" in msg.reactions

    def test_to_json_roundtrip(self):
        msg = Message(from_me=True, timestamp=1000, time="10:00", key_id="k1")
        msg.data = "Hello"
        msg.reactions = {"Alice": "\U0001f44d"}
        json_data = msg.to_json()
        restored = Message.from_json(json_data)
        assert restored.data == "Hello"
        assert restored.reactions == {"Alice": "\U0001f44d"}

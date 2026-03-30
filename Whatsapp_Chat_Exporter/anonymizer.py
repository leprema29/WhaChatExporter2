"""
Data anonymization module for WhatsApp Chat Exporter.
Provides options to anonymize personal data in exports.
"""

import hashlib
import logging
import re
from typing import Dict, Optional
from tqdm import tqdm
from Whatsapp_Chat_Exporter.data_model import ChatCollection
from Whatsapp_Chat_Exporter.utility import convert_time_unit


class Anonymizer:
    """Anonymizes personal data in chat exports."""

    def __init__(self, salt: str = "wtsexporter"):
        self.salt = salt
        self._name_map: Dict[str, str] = {}
        self._phone_counter = 0
        self._name_counter = 0

    def _hash_value(self, value: str) -> str:
        """Create a short hash of a value."""
        return hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:8]

    def _anonymize_phone(self, phone: str) -> str:
        """Replace a phone number with a fake one."""
        if phone not in self._name_map:
            self._phone_counter += 1
            self._name_map[phone] = f"+1555000{self._phone_counter:04d}"
        return self._name_map[phone]

    def _anonymize_name(self, name: str) -> str:
        """Replace a name with a pseudonym."""
        if name is None:
            return None
        if name in ("You", "you"):
            return name
        if name not in self._name_map:
            self._name_counter += 1
            self._name_map[name] = f"Contact_{self._name_counter}"
        return self._name_map[name]

    def _anonymize_text(self, text: Optional[str]) -> Optional[str]:
        """Redact phone numbers from text content."""
        if text is None:
            return None
        # Redact phone numbers in text
        text = re.sub(
            r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
            '[REDACTED_PHONE]',
            text
        )
        return text

    def anonymize(self, data: ChatCollection) -> None:
        """Anonymize all data in the collection in-place."""
        total = len(data)
        logging.info("Anonymizing chat data...")

        with tqdm(total=total, desc="Anonymizing chats", unit="chat", leave=False) as pbar:
            for chat_id, chat in data.items():
                # Anonymize chat name
                chat.name = self._anonymize_name(chat.name)

                # Remove avatars
                chat.my_avatar = None
                chat.their_avatar = None
                chat.their_avatar_thumb = None
                chat.status = None

                # Anonymize messages
                for msg_id, msg in chat.items():
                    msg.sender = self._anonymize_name(msg.sender)
                    msg.data = self._anonymize_text(msg.data)
                    msg.caption = self._anonymize_text(msg.caption)
                    msg.quoted_data = self._anonymize_text(msg.quoted_data)

                    # Anonymize reactions
                    if msg.reactions:
                        new_reactions = {}
                        for sender, emoji in msg.reactions.items():
                            new_reactions[self._anonymize_name(sender)] = emoji
                        msg.reactions = new_reactions

                pbar.update(1)
            total_time = pbar.format_dict['elapsed']

        logging.info(f"Anonymized {total} chats in {convert_time_unit(total_time)}")
        logging.info(
            "WARNING: Anonymization removes names and phone numbers from text, "
            "but media files are NOT modified. Review output before sharing."
        )

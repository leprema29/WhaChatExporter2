"""
Plugin system for export formats.
Provides base class and implementations for PDF, Markdown, and CSV exports.
"""

import csv
import os
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from tqdm import tqdm
from Whatsapp_Chat_Exporter.data_model import ChatCollection, ChatStore
from Whatsapp_Chat_Exporter.utility import convert_time_unit, safe_name


class ExportPlugin(ABC):
    """Base class for export plugins."""

    name: str = ""
    file_extension: str = ""

    @abstractmethod
    def export_chat(self, chat_id: str, chat: ChatStore, output_path: str) -> None:
        """Export a single chat."""
        pass

    def export_all(self, data: ChatCollection, output_dir: str) -> None:
        """Export all chats."""
        os.makedirs(output_dir, exist_ok=True)
        total = len(data)
        with tqdm(total=total, desc=f"Exporting {self.name}", unit="chat", leave=False) as pbar:
            for chat_id, chat in data.items():
                if len(chat) == 0:
                    continue
                name = chat.name or chat_id.split('@')[0]
                safe = safe_name(name)
                output_path = os.path.join(output_dir, f"{safe}.{self.file_extension}")
                try:
                    self.export_chat(chat_id, chat, output_path)
                except Exception as e:
                    logging.warning(f"Failed to export chat {name}: {e}")
                pbar.update(1)
            total_time = pbar.format_dict['elapsed']
        logging.info(f"Exported {total} chats as {self.name} in {convert_time_unit(total_time)}")


class MarkdownExportPlugin(ExportPlugin):
    """Export chats as Markdown files."""

    name = "Markdown"
    file_extension = "md"

    def export_chat(self, chat_id: str, chat: ChatStore, output_path: str) -> None:
        name = chat.name or chat_id.split('@')[0]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# Chat with {name}\n\n")

            current_date = None
            for msg in chat.values():
                msg_date = datetime.fromtimestamp(msg.timestamp).date()
                if msg_date != current_date:
                    current_date = msg_date
                    f.write(f"\n## {current_date}\n\n")

                sender = "**You**" if msg.from_me else f"**{msg.sender or name}**"

                if msg.meta and not msg.media:
                    data = msg.data or "Unknown system message"
                    data = data.replace("<br>", "\n")
                    f.write(f"*{data}*\n\n")
                    continue

                f.write(f"{sender} ({msg.time}):\n")

                if msg.media and msg.data and msg.data != "The media is missing":
                    f.write(f"![media]({msg.data})\n")
                elif msg.data:
                    data = msg.data.replace("<br>", "\n").replace(" <br>", "\n")
                    f.write(f"{data}\n")

                if msg.caption:
                    f.write(f"_{msg.caption}_\n")

                if msg.reactions:
                    reactions = " ".join([f"{emoji}({sender})" for sender, emoji in msg.reactions.items()])
                    f.write(f"Reactions: {reactions}\n")

                f.write("\n")


class CSVExportPlugin(ExportPlugin):
    """Export chats as CSV files."""

    name = "CSV"
    file_extension = "csv"

    def export_chat(self, chat_id: str, chat: ChatStore, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "date", "time", "sender", "from_me",
                "message", "media", "media_type", "caption",
                "is_meta", "reactions"
            ])

            name = chat.name or chat_id.split('@')[0]
            for msg in chat.values():
                msg_date = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d")
                sender = "You" if msg.from_me else (msg.sender or name)
                data = (msg.data or "").replace("<br>", "\n").replace(" <br>", "\n")
                reactions_str = "; ".join([f"{s}:{e}" for s, e in msg.reactions.items()]) if msg.reactions else ""

                writer.writerow([
                    msg.timestamp,
                    msg_date,
                    msg.time,
                    sender,
                    msg.from_me,
                    data,
                    msg.media,
                    msg.mime or "",
                    msg.caption or "",
                    msg.meta,
                    reactions_str
                ])


# Registry of available plugins
EXPORT_PLUGINS: Dict[str, type] = {
    "markdown": MarkdownExportPlugin,
    "md": MarkdownExportPlugin,
    "csv": CSVExportPlugin,
}


def get_plugin(name: str) -> Optional[ExportPlugin]:
    """Get an export plugin by name."""
    plugin_class = EXPORT_PLUGINS.get(name.lower())
    if plugin_class:
        return plugin_class()
    return None


def list_plugins() -> list:
    """List available export plugin names."""
    return list(set(cls.name for cls in EXPORT_PLUGINS.values()))

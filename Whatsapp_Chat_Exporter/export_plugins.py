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


class PDFExportPlugin(ExportPlugin):
    """Export chats as PDF files."""

    name = "PDF"
    file_extension = "pdf"

    def export_chat(self, chat_id: str, chat: ChatStore, output_path: str) -> None:
        try:
            from fpdf import FPDF
        except ImportError:
            raise ImportError(
                "PDF export requires the 'fpdf2' package. "
                "Install it with: pip install fpdf2"
            )

        name = chat.name or chat_id.split('@')[0]

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Use built-in Helvetica (no Unicode but works everywhere)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, f"Chat with {self._safe_text(name)}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        current_date = None
        pdf.set_font("Helvetica", "", 9)

        for msg in chat.values():
            msg_date = datetime.fromtimestamp(msg.timestamp).date()

            # Date separator
            if msg_date != current_date:
                current_date = msg_date
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_fill_color(230, 243, 255)
                pdf.cell(0, 7, str(current_date), new_x="LMARGIN", new_y="NEXT", align="C", fill=True)
                pdf.ln(2)
                pdf.set_font("Helvetica", "", 9)

            # Sender
            sender = "You" if msg.from_me else (msg.sender or name)

            # Skip empty system messages
            if msg.meta and not msg.data:
                continue

            # System messages
            if msg.meta and not msg.media:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(120, 120, 120)
                data = self._safe_text(msg.data or "System message")
                pdf.multi_cell(0, 5, data, new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 9)
                pdf.ln(1)
                continue

            # Message header: sender + time
            if msg.from_me:
                pdf.set_fill_color(231, 255, 219)  # WhatsApp green
            else:
                pdf.set_fill_color(255, 255, 255)

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(56, 146, 218)
            header = f"{self._safe_text(sender)}  [{msg.time}]"
            pdf.cell(0, 5, header, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            # Message body
            pdf.set_font("Helvetica", "", 9)
            if msg.media and msg.data:
                if msg.data == "The media is missing":
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.cell(0, 5, "[Media missing]", new_x="LMARGIN", new_y="NEXT")
                elif msg.mime and msg.mime.startswith("image/") and os.path.isfile(msg.data):
                    try:
                        img_w = min(pdf.w - pdf.l_margin - pdf.r_margin, 80)
                        pdf.image(msg.data, w=img_w)
                        pdf.ln(2)
                    except Exception:
                        pdf.set_font("Helvetica", "I", 8)
                        pdf.cell(0, 5, f"[Image: {self._safe_text(os.path.basename(msg.data))}]", new_x="LMARGIN", new_y="NEXT")
                elif msg.mime and msg.mime.startswith("audio/"):
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.set_text_color(100, 100, 100)
                    duration_text = ""
                    if msg.caption and msg.caption.startswith('"') and msg.caption.endswith('"'):
                        duration_text = f" - Transcription: {self._safe_text(msg.caption)}"
                        msg.caption = None  # Don't print caption twice
                    pdf.cell(0, 5, f"[Voice message{duration_text}]", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_text_color(0, 0, 0)
                elif msg.mime and msg.mime.startswith("video/"):
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.set_text_color(100, 100, 100)
                    fname = os.path.basename(msg.data) if os.path.isfile(msg.data) else "missing"
                    pdf.cell(0, 5, f"[Video: {self._safe_text(fname)}]", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_text_color(0, 0, 0)
                    # If thumbnail exists, embed it
                    if hasattr(msg, 'thumb') and msg.thumb and os.path.isfile(msg.thumb):
                        try:
                            pdf.image(msg.thumb, w=40)
                            pdf.ln(1)
                        except Exception:
                            pass
                elif msg.mime and "vcard" in msg.mime:
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.cell(0, 5, "[Contact card]", new_x="LMARGIN", new_y="NEXT")
                else:
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.cell(0, 5, f"[File: {self._safe_text(os.path.basename(msg.data) if os.path.isfile(msg.data) else msg.data)}]", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
            elif msg.data:
                data = self._safe_text(msg.data)
                pdf.multi_cell(0, 5, data, new_x="LMARGIN", new_y="NEXT")

            # Caption
            if msg.caption:
                pdf.set_font("Helvetica", "I", 8)
                pdf.multi_cell(0, 5, self._safe_text(msg.caption), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)

            # Reactions
            if msg.reactions:
                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(100, 100, 100)
                reactions_text = "  ".join([
                    f"{self._safe_text(s)}: {self._safe_text(e)}"
                    for s, e in msg.reactions.items()
                ])
                pdf.cell(0, 4, f"Reactions: {reactions_text}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Helvetica", "", 9)

            pdf.ln(2)

        # Footer
        pdf.ln(5)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 5, "Generated by WhatsApp Chat Exporter Enhanced", new_x="LMARGIN", new_y="NEXT", align="C")

        pdf.output(output_path)

    @staticmethod
    def _safe_text(text: str) -> str:
        """Convert HTML breaks and sanitize text for PDF output."""
        if not text:
            return ""
        text = text.replace("<br>", "\n").replace(" <br>", "\n")
        # Remove HTML tags
        import re
        text = re.sub(r'<[^>]+>', '', text)
        # Replace chars that Helvetica can't render with closest ASCII
        text = text.encode('latin-1', errors='replace').decode('latin-1')
        return text


# Registry of available plugins
EXPORT_PLUGINS: Dict[str, type] = {
    "markdown": MarkdownExportPlugin,
    "md": MarkdownExportPlugin,
    "csv": CSVExportPlugin,
    "pdf": PDFExportPlugin,
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

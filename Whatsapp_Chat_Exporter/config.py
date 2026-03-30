"""
Configuration file support for WhatsApp Chat Exporter.
Supports TOML configuration files to avoid repeating CLI arguments.
"""

import os
import logging
from typing import Any, Dict, Optional

# Use tomllib (Python 3.11+) or fallback
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


DEFAULT_CONFIG_PATHS = [
    "wtsexporter.toml",
    ".wtsexporter.toml",
    os.path.expanduser("~/.config/wtsexporter/config.toml"),
]

SAMPLE_CONFIG = '''# WhatsApp Chat Exporter Configuration
# Save as wtsexporter.toml in your working directory

[device]
# type = "android"  # or "ios"
# business = false

[input]
# db = "msgstore.db"
# wa = "wa.db"
# media = "WhatsApp"
# backup = ""
# key = ""

[output]
# directory = "result"
# no_html = false
# json = ""
# txt = ""
# markdown = ""
# csv = ""
# per_chat = false

[html]
# template = ""
# no_avatar = false
# old_theme = false
# offline = ""
# headline = "Chat history with ??"

[filter]
# timezone_offset = 0
# date = ""
# date_format = "%Y-%m-%d %H:%M"
# include = []
# exclude = []
# chat_names = []
# dont_filter_empty = false

[export]
# size = ""
# move_media = false
# separate_media = false
# fix_dot_files = false

[json_options]
# avoid_encoding = false
# pretty_print = 2
# telegram_format = false

[contacts]
# enrich_from_vcards = ""
# default_country_code = ""

[security]
# anonymize = false

[advanced]
# decrypt_chunk_size = 1048576
# max_bruteforce_worker = 4
# no_banner = false
# debug = false
'''

# Mapping from config keys to argparse argument names
CONFIG_KEY_MAP = {
    "device.type": lambda args, v: (setattr(args, "android", v == "android"), setattr(args, "ios", v == "ios")),
    "device.business": ("business",),
    "input.db": ("db",),
    "input.wa": ("wa",),
    "input.media": ("media",),
    "input.backup": ("backup",),
    "input.key": ("key",),
    "output.directory": ("output",),
    "output.no_html": ("no_html",),
    "output.json": ("json",),
    "output.txt": ("text_format",),
    "output.per_chat": ("json_per_chat",),
    "output.markdown": ("markdown_export",),
    "output.csv": ("csv_export",),
    "html.template": ("template",),
    "html.no_avatar": ("no_avatar",),
    "html.old_theme": ("telegram_theme",),
    "html.offline": ("offline",),
    "html.headline": ("headline",),
    "filter.timezone_offset": ("timezone_offset",),
    "filter.date": ("filter_date",),
    "filter.date_format": ("filter_date_format",),
    "filter.include": ("filter_chat_include",),
    "filter.exclude": ("filter_chat_exclude",),
    "filter.chat_names": ("filter_chat_names",),
    "filter.dont_filter_empty": ("filter_empty",),
    "export.size": ("size",),
    "export.move_media": ("move_media",),
    "export.separate_media": ("separate_media",),
    "export.fix_dot_files": ("fix_dot_files",),
    "json_options.avoid_encoding": ("avoid_encoding_json",),
    "json_options.pretty_print": ("pretty_print_json",),
    "json_options.telegram_format": ("telegram",),
    "contacts.enrich_from_vcards": ("enrich_from_vcards",),
    "contacts.default_country_code": ("default_country_code",),
    "security.anonymize": ("anonymize",),
    "advanced.decrypt_chunk_size": ("decrypt_chunk_size",),
    "advanced.max_bruteforce_worker": ("max_bruteforce_worker",),
    "advanced.no_banner": ("no_banner",),
    "advanced.debug": ("debug",),
}


def find_config_file(explicit_path: Optional[str] = None) -> Optional[str]:
    """Find a configuration file."""
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        logging.warning(f"Config file not found: {explicit_path}")
        return None

    for path in DEFAULT_CONFIG_PATHS:
        if os.path.isfile(path):
            return path
    return None


def load_config(config_path: str) -> Dict[str, Any]:
    """Load a TOML configuration file."""
    if tomllib is None:
        logging.warning(
            "TOML support not available. Install 'tomli' package for Python < 3.11, "
            "or upgrade to Python 3.11+."
        )
        return {}

    with open(config_path, "rb") as f:
        return tomllib.load(f)


def apply_config_to_args(config: Dict[str, Any], args) -> None:
    """Apply configuration values to argparse namespace, without overriding CLI arguments."""
    for section_name, section in config.items():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            full_key = f"{section_name}.{key}"
            mapping = CONFIG_KEY_MAP.get(full_key)

            if mapping is None:
                logging.debug(f"Unknown config key: {full_key}")
                continue

            if callable(mapping) and not isinstance(mapping, tuple):
                mapping(args, value)
            elif isinstance(mapping, tuple):
                attr_name = mapping[0]
                # Only set if the CLI didn't explicitly set it (check for default values)
                current = getattr(args, attr_name, None)
                if current is None or current is False or current == 0:
                    setattr(args, attr_name, value)


def generate_sample_config(output_path: str = "wtsexporter.toml") -> None:
    """Generate a sample configuration file."""
    with open(output_path, "w") as f:
        f.write(SAMPLE_CONFIG)
    logging.info(f"Sample configuration file generated: {output_path}")

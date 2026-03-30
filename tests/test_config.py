"""Tests for config.py."""
import os
import tempfile
import pytest
from argparse import Namespace
from Whatsapp_Chat_Exporter.config import (
    find_config_file, load_config, apply_config_to_args, generate_sample_config
)


class TestFindConfigFile:
    def test_explicit_path_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[device]\n")
            path = f.name
        try:
            assert find_config_file(path) == path
        finally:
            os.unlink(path)

    def test_explicit_path_not_exists(self):
        assert find_config_file("/nonexistent/path.toml") is None

    def test_no_path_no_default(self):
        # In a temp directory, no config files exist
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            result = find_config_file()
            os.chdir(old_cwd)
        assert result is None


class TestGenerateSampleConfig:
    def test_generate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_config.toml")
            generate_sample_config(path)
            assert os.path.isfile(path)
            content = open(path).read()
            assert "[device]" in content
            assert "[output]" in content


class TestApplyConfig:
    def test_apply_simple_values(self):
        args = Namespace(
            output=None, no_html=False, debug=False,
            no_banner=False, anonymize=False
        )
        config = {
            "output": {"directory": "my_output"},
            "advanced": {"debug": True, "no_banner": True},
            "security": {"anonymize": True},
        }
        apply_config_to_args(config, args)
        assert args.output == "my_output"
        assert args.debug is True
        assert args.anonymize is True

    def test_no_override_existing_cli_values(self):
        """Config should not override values already set by CLI."""
        args = Namespace(
            output="cli_value", no_html=False, debug=False,
            no_banner=False, anonymize=False
        )
        config = {
            "output": {"directory": "config_value"},
        }
        apply_config_to_args(config, args)
        # CLI value should be preserved since it's a non-default truthy value
        assert args.output == "cli_value"

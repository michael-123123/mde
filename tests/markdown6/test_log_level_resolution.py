"""Tests for ``logger.resolve_level``.

The resolution chain is: CLI flag → ``MDE_LOG_LEVEL`` env var → default.
Pin each branch so a misordered fallback or a typo doesn't silently
demote a user's debug request to the default.
"""

import logging
import os

import pytest

from markdown_editor.markdown6.logger import resolve_level


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip MDE_LOG_LEVEL so each test starts from a known state."""
    monkeypatch.delenv("MDE_LOG_LEVEL", raising=False)


class TestDefault:
    def test_no_inputs_returns_default(self):
        assert resolve_level() == logging.INFO

    def test_custom_default_used_when_no_inputs(self):
        assert resolve_level(default=logging.WARNING) == logging.WARNING


class TestCliFlag:
    def test_cli_debug(self):
        assert resolve_level("debug") == logging.DEBUG

    def test_cli_info(self):
        assert resolve_level("info") == logging.INFO

    def test_cli_warning(self):
        assert resolve_level("warning") == logging.WARNING

    def test_cli_warn_alias(self):
        assert resolve_level("warn") == logging.WARNING

    def test_cli_error(self):
        assert resolve_level("error") == logging.ERROR

    def test_cli_case_insensitive(self):
        assert resolve_level("DEBUG") == logging.DEBUG
        assert resolve_level("Info") == logging.INFO

    def test_cli_whitespace_tolerated(self):
        assert resolve_level("  debug  ") == logging.DEBUG

    def test_cli_unknown_falls_back_to_default(self):
        assert resolve_level("nonsense") == logging.INFO


class TestEnvVar:
    def test_env_debug(self, monkeypatch):
        monkeypatch.setenv("MDE_LOG_LEVEL", "debug")
        assert resolve_level() == logging.DEBUG

    def test_env_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("MDE_LOG_LEVEL", "ERROR")
        assert resolve_level() == logging.ERROR

    def test_env_unknown_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MDE_LOG_LEVEL", "xyz")
        assert resolve_level() == logging.INFO


class TestPrecedence:
    def test_cli_beats_env(self, monkeypatch):
        """CLI flag wins over env var - explicit invocation wins."""
        monkeypatch.setenv("MDE_LOG_LEVEL", "error")
        assert resolve_level("debug") == logging.DEBUG

    def test_env_used_when_cli_is_none(self, monkeypatch):
        monkeypatch.setenv("MDE_LOG_LEVEL", "warning")
        assert resolve_level(None) == logging.WARNING

    def test_env_used_when_cli_is_empty_string(self, monkeypatch):
        """argparse can pass '' for an option that was specified with no
        value - treat it as "no choice" and fall through to env."""
        monkeypatch.setenv("MDE_LOG_LEVEL", "warning")
        assert resolve_level("") == logging.WARNING

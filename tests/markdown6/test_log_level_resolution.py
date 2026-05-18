"""Tests for ``logger.resolve_level``.

The resolution chain is:
    CLI flag → ``MDE_LOG_LEVEL`` env var → settings.log.level → default.

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


class TestSettingsLayer:
    """The persisted ``log.level`` setting is the third tier - below
    CLI flag and env var, above the built-in default. Surfaced via
    Settings → Diagnostics so users can change log level without
    touching shell config."""

    def test_settings_value_used_when_no_cli_no_env(self):
        assert resolve_level(settings_value="warning") == logging.WARNING

    def test_settings_value_case_insensitive(self):
        assert resolve_level(settings_value="DEBUG") == logging.DEBUG

    def test_settings_value_unknown_falls_back_to_default(self):
        assert resolve_level(settings_value="nonsense") == logging.INFO

    def test_settings_value_none_falls_to_default(self):
        assert resolve_level(settings_value=None) == logging.INFO

    def test_env_beats_settings(self, monkeypatch):
        """A user's shell env override should win over their persisted
        choice - same logic as CLI > env."""
        monkeypatch.setenv("MDE_LOG_LEVEL", "error")
        assert resolve_level(settings_value="debug") == logging.ERROR

    def test_cli_beats_settings(self):
        assert resolve_level("error", settings_value="debug") == logging.ERROR

    def test_cli_beats_env_beats_settings(self, monkeypatch):
        """All three set: CLI wins."""
        monkeypatch.setenv("MDE_LOG_LEVEL", "warning")
        assert (
            resolve_level("error", settings_value="debug") == logging.ERROR
        )

    def test_settings_layer_below_env(self, monkeypatch):
        """No CLI, env present, settings present → env wins."""
        monkeypatch.setenv("MDE_LOG_LEVEL", "warning")
        assert resolve_level(settings_value="debug") == logging.WARNING


class TestSetLevel:
    """`set_level` updates installed handlers in place. Used after
    AppContext loads to re-apply the level with the persisted setting
    factored in (the initial setup() runs before settings load)."""

    def test_set_level_updates_existing_handler(self):
        from markdown_editor.markdown6.logger import setup, set_level
        # setup is idempotent; safe to call from a test.
        setup(level=logging.INFO)
        set_level(logging.WARNING)
        root = logging.getLogger("mde")
        for h in root.handlers:
            assert h.level == logging.WARNING

    def test_set_level_can_lower_threshold(self):
        from markdown_editor.markdown6.logger import setup, set_level
        setup(level=logging.WARNING)
        set_level(logging.DEBUG)
        root = logging.getLogger("mde")
        for h in root.handlers:
            assert h.level == logging.DEBUG

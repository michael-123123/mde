"""Tests for the settings module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from fun.markdown6.settings import (
    Settings,
    DEFAULT_SETTINGS,
    DEFAULT_SHORTCUTS,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def settings(temp_config_dir):
    """Create a Settings instance with a temp directory."""
    return Settings(config_dir=temp_config_dir)


class TestSettingsInit:
    """Tests for Settings initialization."""

    def test_creates_config_directory(self, tmp_path):
        """Test that Settings creates the config directory if it doesn't exist."""
        config_dir = tmp_path / "new_config"
        assert not config_dir.exists()
        Settings(config_dir=config_dir)
        assert config_dir.exists()

    def test_loads_default_settings(self, settings):
        """Test that default settings are loaded."""
        for key, default_value in DEFAULT_SETTINGS.items():
            assert settings.get(key) == default_value

    def test_loads_default_shortcuts(self, settings):
        """Test that default shortcuts are loaded."""
        for action, shortcut in DEFAULT_SHORTCUTS.items():
            assert settings.get_shortcut(action) == shortcut


class TestSettingsGetSet:
    """Tests for get/set operations."""

    def test_get_existing_setting(self, settings):
        """Test getting an existing setting."""
        assert settings.get("editor.font_size") == 11

    def test_get_nonexistent_setting_returns_none(self, settings):
        """Test getting a nonexistent setting returns None."""
        assert settings.get("nonexistent.key") is None

    def test_get_nonexistent_setting_with_default(self, settings):
        """Test getting a nonexistent setting with a default value."""
        assert settings.get("nonexistent.key", "default") == "default"

    def test_set_setting(self, settings):
        """Test setting a value."""
        settings.set("editor.font_size", 14)
        assert settings.get("editor.font_size") == 14

    def test_set_new_setting(self, settings):
        """Test setting a new key."""
        settings.set("custom.setting", "value")
        assert settings.get("custom.setting") == "value"

    def test_set_emits_signal(self, settings, qtbot):
        """Test that set emits settings_changed signal."""
        with qtbot.waitSignal(settings.settings_changed) as blocker:
            settings.set("editor.font_size", 16)
        assert blocker.args == ["editor.font_size", 16]

    def test_set_theme_emits_theme_signal(self, settings, qtbot):
        """Test that setting theme emits theme_changed signal."""
        with qtbot.waitSignal(settings.theme_changed) as blocker:
            settings.set("view.theme", "dark")
        assert blocker.args == ["dark"]

    def test_set_same_value_no_signal(self, settings, qtbot):
        """Test that setting the same value doesn't emit signal."""
        current = settings.get("editor.font_size")
        with qtbot.assertNotEmitted(settings.settings_changed):
            settings.set("editor.font_size", current)


class TestShortcuts:
    """Tests for shortcut operations."""

    def test_get_shortcut(self, settings):
        """Test getting a shortcut."""
        assert settings.get_shortcut("file.new") == "Ctrl+N"

    def test_get_nonexistent_shortcut(self, settings):
        """Test getting a nonexistent shortcut returns empty string."""
        assert settings.get_shortcut("nonexistent.action") == ""

    def test_set_shortcut(self, settings):
        """Test setting a shortcut."""
        settings.set_shortcut("file.new", "Ctrl+Shift+N")
        assert settings.get_shortcut("file.new") == "Ctrl+Shift+N"

    def test_set_shortcut_emits_signal(self, settings, qtbot):
        """Test that set_shortcut emits shortcut_changed signal."""
        with qtbot.waitSignal(settings.shortcut_changed) as blocker:
            settings.set_shortcut("file.new", "Ctrl+Shift+N")
        assert blocker.args == ["file.new", "Ctrl+Shift+N"]

    def test_get_all_shortcuts(self, settings):
        """Test getting all shortcuts."""
        shortcuts = settings.get_all_shortcuts()
        assert shortcuts == DEFAULT_SHORTCUTS

    def test_reset_shortcuts(self, settings):
        """Test resetting shortcuts to defaults."""
        settings.set_shortcut("file.new", "Ctrl+Shift+N")
        settings.reset_shortcuts()
        assert settings.get_shortcut("file.new") == "Ctrl+N"


class TestPersistence:
    """Tests for saving and loading settings."""

    def test_save_creates_settings_file(self, settings, temp_config_dir):
        """Test that save creates the settings file."""
        settings.set("editor.font_size", 14)
        assert (temp_config_dir / "settings.json").exists()

    def test_save_only_non_defaults(self, settings, temp_config_dir):
        """Test that only non-default values are saved."""
        settings.set("editor.font_size", 14)
        with open(temp_config_dir / "settings.json") as f:
            saved = json.load(f)
        assert saved == {"editor.font_size": 14}
        assert "editor.tab_size" not in saved  # Default value not saved

    def test_load_persisted_settings(self, temp_config_dir):
        """Test loading persisted settings."""
        # Save some settings
        settings1 = Settings(config_dir=temp_config_dir)
        settings1.set("editor.font_size", 18)

        # Create new instance and verify
        settings2 = Settings(config_dir=temp_config_dir)
        assert settings2.get("editor.font_size") == 18

    def test_load_handles_corrupt_file(self, temp_config_dir):
        """Test that corrupt settings file is handled gracefully."""
        # Write corrupt JSON
        settings_file = temp_config_dir / "settings.json"
        settings_file.write_text("not valid json{{{")

        # Should not raise, should use defaults
        settings = Settings(config_dir=temp_config_dir)
        assert settings.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]


class TestRecentFiles:
    """Tests for recent files functionality."""

    def test_add_recent_file(self, settings, tmp_path):
        """Test adding a recent file."""
        test_file = tmp_path / "test.md"
        test_file.touch()
        settings.add_recent_file(test_file)
        recent = settings.get("files.recent_files")
        assert str(test_file.resolve()) in recent

    def test_add_recent_file_moves_to_front(self, settings, tmp_path):
        """Test that adding an existing file moves it to front."""
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file1.touch()
        file2.touch()

        settings.add_recent_file(file1)
        settings.add_recent_file(file2)
        settings.add_recent_file(file1)

        recent = settings.get("files.recent_files")
        assert recent[0] == str(file1.resolve())

    def test_recent_files_max_limit(self, settings, tmp_path):
        """Test that recent files respects max limit."""
        settings.set("files.max_recent_files", 3, save=False)

        for i in range(5):
            f = tmp_path / f"file{i}.md"
            f.touch()
            settings.add_recent_file(f)

        recent = settings.get("files.recent_files")
        assert len(recent) == 3

    def test_get_recent_files_filters_nonexistent(self, settings, tmp_path):
        """Test that get_recent_files filters out files that don't exist."""
        # Clear existing recent files first
        settings.set("files.recent_files", [], save=False)

        file1 = tmp_path / "exists.md"
        file1.touch()
        settings.add_recent_file(file1)

        # Add a non-existent file directly
        recent = settings.get("files.recent_files")
        recent.append("/nonexistent/file.md")
        settings.set("files.recent_files", recent, save=False)

        result = settings.get_recent_files()
        assert len(result) == 1
        assert result[0] == file1

    def test_clear_recent_files(self, settings, tmp_path):
        """Test clearing recent files."""
        file1 = tmp_path / "test.md"
        file1.touch()
        settings.add_recent_file(file1)
        settings.clear_recent_files()
        assert settings.get("files.recent_files") == []


class TestResetDefaults:
    """Tests for reset functionality."""

    def test_reset_settings(self, settings):
        """Test resetting settings to defaults."""
        settings.set("editor.font_size", 20, save=False)
        settings.reset_settings()
        assert settings.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]

    def test_restore_all_defaults(self, settings, temp_config_dir):
        """Test restoring all defaults including deleting files."""
        settings.set("editor.font_size", 20)
        settings.set_shortcut("file.new", "Ctrl+Shift+N")

        settings_file = temp_config_dir / "settings.json"
        shortcuts_file = temp_config_dir / "shortcuts.json"
        assert settings_file.exists()
        assert shortcuts_file.exists()

        settings.restore_all_defaults()

        assert not settings_file.exists()
        assert not shortcuts_file.exists()
        assert settings.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]
        assert settings.get_shortcut("file.new") == DEFAULT_SHORTCUTS["file.new"]


class TestEphemeralSettings:
    """Tests for ephemeral (in-memory only) settings."""

    def test_ephemeral_uses_defaults(self, tmp_path):
        """Test that ephemeral settings use defaults."""
        settings = Settings(config_dir=tmp_path, ephemeral=True)
        assert settings.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]

    def test_ephemeral_ignores_existing_settings(self, tmp_path):
        """Test that ephemeral settings don't load from disk."""
        # First create a normal settings file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings_file = config_dir / "settings.json"
        settings_file.write_text('{"editor.font_size": 99}')

        # Ephemeral settings should ignore the file
        settings = Settings(config_dir=config_dir, ephemeral=True)
        assert settings.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]
        assert settings.get("editor.font_size") != 99

    def test_ephemeral_does_not_save(self, tmp_path):
        """Test that ephemeral settings don't save to disk."""
        config_dir = tmp_path / "config"
        # Don't create the directory - ephemeral shouldn't need it

        settings = Settings(config_dir=config_dir, ephemeral=True)
        settings.set("editor.font_size", 20)

        # Should not have created the config directory
        assert not config_dir.exists()

    def test_ephemeral_changes_work_in_memory(self, tmp_path):
        """Test that ephemeral settings can be changed in memory."""
        settings = Settings(config_dir=tmp_path, ephemeral=True)

        settings.set("editor.font_size", 18, save=False)
        assert settings.get("editor.font_size") == 18

        settings.set("view.theme", "dark", save=False)
        assert settings.get("view.theme") == "dark"

    def test_init_settings_ephemeral(self, tmp_path):
        """Test init_settings with ephemeral flag."""
        from fun.markdown6.settings import init_settings, get_settings, _settings
        import fun.markdown6.settings as settings_module

        # Reset global settings
        settings_module._settings = None

        settings = init_settings(config_dir=tmp_path, ephemeral=True)
        assert settings._ephemeral is True
        assert get_settings() is settings

        # Clean up
        settings_module._settings = None

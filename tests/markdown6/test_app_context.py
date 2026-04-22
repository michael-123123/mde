"""Tests for the AppContext module."""

import json

import pytest

from markdown_editor.markdown6.app_context import (
    DEFAULT_SETTINGS,
    DEFAULT_SHORTCUTS,
    AppContext,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def ctx(temp_config_dir):
    """Create an AppContext instance with a temp directory."""
    return AppContext(config_dir=temp_config_dir)


class TestAppContextInit:
    """Tests for AppContext initialization."""

    def test_creates_config_directory(self, tmp_path):
        """Test that AppContext creates the config directory if it doesn't exist."""
        config_dir = tmp_path / "new_config"
        assert not config_dir.exists()
        AppContext(config_dir=config_dir)
        assert config_dir.exists()

    def test_loads_default_settings(self, ctx):
        """Test that default settings are loaded."""
        for key, default_value in DEFAULT_SETTINGS.items():
            assert ctx.get(key) == default_value

    def test_loads_default_shortcuts(self, ctx):
        """Test that default shortcuts are loaded."""
        for action, shortcut in DEFAULT_SHORTCUTS.items():
            assert ctx.get_shortcut(action) == shortcut


class TestAppContextGetSet:
    """Tests for get/set operations."""

    def test_get_existing_setting(self, ctx):
        """Test getting an existing setting."""
        assert ctx.get("editor.font_size") == 11

    def test_get_nonexistent_setting_returns_none(self, ctx):
        """Test getting a nonexistent setting returns None."""
        assert ctx.get("nonexistent.key") is None

    def test_get_nonexistent_setting_with_default(self, ctx):
        """Test getting a nonexistent setting with a default value."""
        assert ctx.get("nonexistent.key", "default") == "default"

    def test_set_setting(self, ctx):
        """Test setting a value."""
        ctx.set("editor.font_size", 14)
        assert ctx.get("editor.font_size") == 14

    def test_set_new_setting(self, ctx):
        """Test setting a new key."""
        ctx.set("custom.setting", "value")
        assert ctx.get("custom.setting") == "value"

    def test_set_emits_signal(self, ctx, qtbot):
        """Test that set emits settings_changed signal."""
        with qtbot.waitSignal(ctx.settings_changed) as blocker:
            ctx.set("editor.font_size", 16)
        assert blocker.args == ["editor.font_size", 16]

    def test_set_theme_emits_theme_signal(self, ctx, qtbot):
        """Test that setting theme emits theme_changed signal."""
        with qtbot.waitSignal(ctx.theme_changed) as blocker:
            ctx.set("view.theme", "dark")
        assert blocker.args == ["dark"]

    def test_set_same_value_no_signal(self, ctx, qtbot):
        """Test that setting the same value doesn't emit signal."""
        current = ctx.get("editor.font_size")
        with qtbot.assertNotEmitted(ctx.settings_changed):
            ctx.set("editor.font_size", current)


class TestShortcuts:
    """Tests for shortcut operations."""

    def test_get_shortcut(self, ctx):
        """Test getting a shortcut."""
        assert ctx.get_shortcut("file.new") == "Ctrl+N"

    def test_get_nonexistent_shortcut(self, ctx):
        """Test getting a nonexistent shortcut returns empty string."""
        assert ctx.get_shortcut("nonexistent.action") == ""

    def test_set_shortcut(self, ctx):
        """Test setting a shortcut."""
        ctx.set_shortcut("file.new", "Ctrl+Shift+N")
        assert ctx.get_shortcut("file.new") == "Ctrl+Shift+N"

    def test_set_shortcut_emits_signal(self, ctx, qtbot):
        """Test that set_shortcut emits shortcut_changed signal."""
        with qtbot.waitSignal(ctx.shortcut_changed) as blocker:
            ctx.set_shortcut("file.new", "Ctrl+Shift+N")
        assert blocker.args == ["file.new", "Ctrl+Shift+N"]

    def test_get_all_shortcuts(self, ctx):
        """Test getting all shortcuts."""
        shortcuts = ctx.get_all_shortcuts()
        assert shortcuts == DEFAULT_SHORTCUTS

    def test_reset_shortcuts(self, ctx):
        """Test resetting shortcuts to defaults."""
        ctx.set_shortcut("file.new", "Ctrl+Shift+N")
        ctx.reset_shortcuts()
        assert ctx.get_shortcut("file.new") == "Ctrl+N"


class TestPersistence:
    """Tests for saving and loading settings."""

    def test_save_creates_settings_file(self, ctx, temp_config_dir):
        """Test that save creates the settings file."""
        ctx.set("editor.font_size", 14)
        assert (temp_config_dir / "settings.json").exists()

    def test_save_only_non_defaults(self, ctx, temp_config_dir):
        """Test that only non-default values are saved."""
        ctx.set("editor.font_size", 14)
        with open(temp_config_dir / "settings.json") as f:
            saved = json.load(f)
        assert saved == {"editor.font_size": 14}
        assert "editor.tab_size" not in saved  # Default value not saved

    def test_load_persisted_settings(self, temp_config_dir):
        """Test loading persisted settings."""
        # Save some settings
        ctx1 = AppContext(config_dir=temp_config_dir)
        ctx1.set("editor.font_size", 18)

        # Create new instance and verify
        ctx2 = AppContext(config_dir=temp_config_dir)
        assert ctx2.get("editor.font_size") == 18

    def test_load_handles_corrupt_file(self, temp_config_dir):
        """Test that corrupt settings file is handled gracefully."""
        # Write corrupt JSON
        settings_file = temp_config_dir / "settings.json"
        settings_file.write_text("not valid json{{{")

        # Should not raise, should use defaults
        ctx = AppContext(config_dir=temp_config_dir)
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]


class TestRecentFiles:
    """Tests for recent files functionality."""

    def test_add_recent_file(self, ctx, tmp_path):
        """Test adding a recent file."""
        test_file = tmp_path / "test.md"
        test_file.touch()
        ctx.add_recent_file(test_file)
        recent = ctx.get("files.recent_files")
        assert str(test_file.resolve()) in recent

    def test_add_recent_file_moves_to_front(self, ctx, tmp_path):
        """Test that adding an existing file moves it to front."""
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file1.touch()
        file2.touch()

        ctx.add_recent_file(file1)
        ctx.add_recent_file(file2)
        ctx.add_recent_file(file1)

        recent = ctx.get("files.recent_files")
        assert recent[0] == str(file1.resolve())

    def test_recent_files_max_limit(self, ctx, tmp_path):
        """Test that recent files respects max limit."""
        ctx.set("files.max_recent_files", 3, save=False)

        for i in range(5):
            f = tmp_path / f"file{i}.md"
            f.touch()
            ctx.add_recent_file(f)

        recent = ctx.get("files.recent_files")
        assert len(recent) == 3

    def test_get_recent_files_filters_nonexistent(self, ctx, tmp_path):
        """Test that get_recent_files filters out files that don't exist."""
        # Clear existing recent files first
        ctx.set("files.recent_files", [], save=False)

        file1 = tmp_path / "exists.md"
        file1.touch()
        ctx.add_recent_file(file1)

        # Add a non-existent file directly
        recent = ctx.get("files.recent_files")
        recent.append("/nonexistent/file.md")
        ctx.set("files.recent_files", recent, save=False)

        result = ctx.get_recent_files()
        assert len(result) == 1
        assert result[0] == file1

    def test_clear_recent_files(self, ctx, tmp_path):
        """Test clearing recent files."""
        file1 = tmp_path / "test.md"
        file1.touch()
        ctx.add_recent_file(file1)
        ctx.clear_recent_files()
        assert ctx.get("files.recent_files") == []


class TestResetDefaults:
    """Tests for reset functionality."""

    def test_reset_settings(self, ctx):
        """Test resetting settings to defaults."""
        ctx.set("editor.font_size", 20, save=False)
        ctx.reset_settings()
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]

    def test_restore_all_defaults(self, ctx, temp_config_dir):
        """Test restoring all defaults including deleting files."""
        ctx.set("editor.font_size", 20)
        ctx.set_shortcut("file.new", "Ctrl+Shift+N")

        settings_file = temp_config_dir / "settings.json"
        shortcuts_file = temp_config_dir / "shortcuts.json"
        assert settings_file.exists()
        assert shortcuts_file.exists()

        ctx.restore_all_defaults()

        assert not settings_file.exists()
        assert not shortcuts_file.exists()
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]
        assert ctx.get_shortcut("file.new") == DEFAULT_SHORTCUTS["file.new"]


class TestEphemeralAppContext:
    """Tests for ephemeral (in-memory only) AppContext."""

    def test_ephemeral_uses_defaults(self, tmp_path):
        """Test that ephemeral settings use defaults."""
        ctx = AppContext(config_dir=tmp_path, ephemeral=True)
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]

    def test_ephemeral_ignores_existing_settings(self, tmp_path):
        """Test that ephemeral settings don't load from disk."""
        # First create a normal settings file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings_file = config_dir / "settings.json"
        settings_file.write_text('{"editor.font_size": 99}')

        # Ephemeral settings should ignore the file
        ctx = AppContext(config_dir=config_dir, ephemeral=True)
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]
        assert ctx.get("editor.font_size") != 99

    def test_ephemeral_does_not_save(self, tmp_path):
        """Test that ephemeral settings don't save to disk."""
        config_dir = tmp_path / "config"
        # Don't create the directory - ephemeral shouldn't need it

        ctx = AppContext(config_dir=config_dir, ephemeral=True)
        ctx.set("editor.font_size", 20)

        # Should not have created the config directory
        assert not config_dir.exists()

    def test_ephemeral_changes_work_in_memory(self, tmp_path):
        """Test that ephemeral settings can be changed in memory."""
        ctx = AppContext(config_dir=tmp_path, ephemeral=True)

        ctx.set("editor.font_size", 18, save=False)
        assert ctx.get("editor.font_size") == 18

        ctx.set("view.theme", "dark", save=False)
        assert ctx.get("view.theme") == "dark"

    def test_init_app_context_ephemeral(self, tmp_path):
        """Test init_app_context with ephemeral flag."""
        import markdown_editor.markdown6.app_context as ctx_module
        from markdown_editor.markdown6.app_context import (
            get_app_context,
            init_app_context,
        )

        # Reset global context
        ctx_module._app_context = None

        ctx = init_app_context(config_dir=tmp_path, ephemeral=True)
        assert ctx._ephemeral is True
        assert get_app_context() is ctx

        # Clean up
        ctx_module._app_context = None

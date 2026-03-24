"""Settings management for the Markdown editor."""

import json
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal


DEFAULT_SETTINGS = {
    # Editor settings
    "editor.font_family": "Monospace",
    "editor.font_size": 11,
    "editor.tab_size": 4,
    "editor.use_spaces": True,
    "editor.word_wrap": True,
    "editor.show_line_numbers": True,
    "editor.highlight_current_line": True,
    "editor.show_whitespace": False,
    "editor.auto_pairs": True,
    "editor.auto_indent": True,
    "editor.auto_save": False,
    "editor.auto_save_interval": 60,  # seconds
    # View settings
    "view.show_editor": True,
    "view.show_preview": True,
    "view.sync_scrolling": True,
    "view.theme": "light",  # light, dark
    "view.preview_font_size": 14,
    # File settings
    "files.recent_files": [],
    "files.max_recent_files": 10,
    "files.detect_external_changes": True,
    # Project settings
    "project.last_path": None,
    "project.open_files": [],
    "project.active_tab": 0,
    # Logseq mode
    "view.logseq_mode": False,
    # External tool paths (empty string = use system PATH)
    "tools.pandoc_path": "",
    "tools.dot_path": "",
    "tools.mmdc_path": "",
}

DEFAULT_SHORTCUTS = {
    # File operations
    "file.new": "Ctrl+N",
    "file.open": "Ctrl+O",
    "file.open_project": "Ctrl+Shift+O",
    "file.save": "Ctrl+S",
    "file.save_as": "Ctrl+Shift+S",
    "file.close_tab": "Ctrl+W",
    "file.quit": "Ctrl+Q",
    # Edit operations
    "edit.undo": "Ctrl+Z",
    "edit.redo": "Ctrl+Shift+Z",
    "edit.cut": "Ctrl+X",
    "edit.copy": "Ctrl+C",
    "edit.paste": "Ctrl+V",
    "edit.select_all": "Ctrl+A",
    "edit.find": "Ctrl+F",
    "edit.replace": "Ctrl+R",
    "edit.go_to_line": "Ctrl+G",
    "edit.duplicate_line": "Ctrl+Shift+D",
    "edit.delete_line": "Ctrl+Shift+K",
    "edit.move_line_up": "Alt+Up",
    "edit.move_line_down": "Alt+Down",
    "edit.indent": "Tab",
    "edit.outdent": "Shift+Tab",
    "edit.toggle_comment": "Ctrl+/",
    # Markdown formatting
    "markdown.bold": "Ctrl+B",
    "markdown.italic": "Ctrl+I",
    "markdown.link": "Ctrl+K",
    "markdown.image": "Ctrl+Shift+I",
    "markdown.code": "Ctrl+`",
    "markdown.heading_increase": "Ctrl+]",
    "markdown.heading_decrease": "Ctrl+[",
    # View operations
    "view.refresh_preview": "F5",
    "view.toggle_preview": "Ctrl+Shift+V",
    "view.toggle_line_numbers": "Ctrl+Shift+L",
    "view.toggle_word_wrap": "Alt+Z",
    "view.toggle_whitespace": "Ctrl+Alt+W",
    "view.fullscreen": "F11",
    "view.zoom_in": "Ctrl++",
    "view.zoom_out": "Ctrl+-",
    "view.zoom_reset": "Ctrl+0",
    "view.command_palette": "Ctrl+Shift+P",
    "view.toggle_outline": "Ctrl+Alt+O",
    "view.toggle_project": "Ctrl+Shift+E",
    "view.toggle_references": "Ctrl+Shift+R",
    "view.toggle_search": "Ctrl+Shift+F",
    "view.toggle_sidebar": "Ctrl+Shift+B",
    "view.fold_all": "Ctrl+Shift+[",
    "view.unfold_all": "Ctrl+Shift+]",
    "view.toggle_logseq_mode": "Ctrl+Alt+L",
    # Insert operations
    "insert.snippet": "Ctrl+J",
    "insert.table": "Ctrl+Shift+T",
    # Tab navigation
    "tabs.next": "Ctrl+Tab",
    "tabs.previous": "Ctrl+Shift+Tab",
    "tabs.go_to_1": "Alt+1",
    "tabs.go_to_2": "Alt+2",
    "tabs.go_to_3": "Alt+3",
    "tabs.go_to_4": "Alt+4",
    "tabs.go_to_5": "Alt+5",
    "tabs.go_to_6": "Alt+6",
    "tabs.go_to_7": "Alt+7",
    "tabs.go_to_8": "Alt+8",
    "tabs.go_to_9": "Alt+9",
    # Find operations
    "find.next": "F3",
    "find.previous": "Shift+F3",
}


def _default_config_dir() -> Path:
    """Return the platform-appropriate config directory for the editor."""
    if sys.platform == "win32":
        # %APPDATA%/markdown-editor
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # XDG_CONFIG_HOME or ~/.config
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "markdown-editor"


class Settings(QObject):
    """Application settings manager with persistence."""

    settings_changed = Signal(str, object)  # key, new_value
    shortcut_changed = Signal(str, str)  # action, new_shortcut
    theme_changed = Signal(str)  # theme name

    def __init__(self, config_dir: Path | None = None, ephemeral: bool = False):
        """Initialize settings.

        Args:
            config_dir: Directory to store settings. Platform-appropriate default.
            ephemeral: If True, use default settings in memory only - don't load or save.
        """
        super().__init__()
        self._ephemeral = ephemeral

        if config_dir is None:
            config_dir = _default_config_dir()
        self.config_dir = config_dir

        if not ephemeral:
            self.config_dir.mkdir(parents=True, exist_ok=True)

        self.settings_file = self.config_dir / "settings.json"
        self.shortcuts_file = self.config_dir / "shortcuts.json"

        self._settings: dict[str, Any] = {}
        self._shortcuts: dict[str, str] = {}

        self.load()

    def load(self):
        """Load settings from disk (or use defaults if ephemeral)."""
        # Start with defaults
        self._settings = DEFAULT_SETTINGS.copy()
        self._shortcuts = DEFAULT_SHORTCUTS.copy()

        # In ephemeral mode, don't load from disk
        if self._ephemeral:
            return

        # Load settings from disk
        if self.settings_file.exists():
            try:
                with open(self.settings_file) as f:
                    saved = json.load(f)
                self._settings.update(saved)
            except (json.JSONDecodeError, OSError):
                pass

        # Load shortcuts from disk
        if self.shortcuts_file.exists():
            try:
                with open(self.shortcuts_file) as f:
                    saved = json.load(f)
                self._shortcuts.update(saved)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        """Save settings to disk (no-op if ephemeral)."""
        # In ephemeral mode, don't save to disk
        if self._ephemeral:
            return

        # Only save non-default values
        settings_to_save = {
            k: v for k, v in self._settings.items()
            if k not in DEFAULT_SETTINGS or v != DEFAULT_SETTINGS[k]
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(settings_to_save, f, indent=2)
        except OSError:
            pass  # Silently fail - settings will be in memory but not persisted

        shortcuts_to_save = {
            k: v for k, v in self._shortcuts.items()
            if k not in DEFAULT_SHORTCUTS or v != DEFAULT_SHORTCUTS[k]
        }
        try:
            with open(self.shortcuts_file, "w") as f:
                json.dump(shortcuts_to_save, f, indent=2)
        except OSError:
            pass  # Silently fail - shortcuts will be in memory but not persisted

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any, save: bool = True):
        """Set a setting value."""
        old_value = self._settings.get(key)
        self._settings[key] = value
        if save:
            self.save()
        if old_value != value:
            self.settings_changed.emit(key, value)
            if key == "view.theme":
                self.theme_changed.emit(value)

    def get_shortcut(self, action: str) -> str:
        """Get a keyboard shortcut for an action."""
        return self._shortcuts.get(action, "")

    def set_shortcut(self, action: str, shortcut: str, save: bool = True):
        """Set a keyboard shortcut for an action."""
        old_shortcut = self._shortcuts.get(action)
        self._shortcuts[action] = shortcut
        if save:
            self.save()
        if old_shortcut != shortcut:
            self.shortcut_changed.emit(action, shortcut)

    def get_all_shortcuts(self) -> dict[str, str]:
        """Get all keyboard shortcuts."""
        return self._shortcuts.copy()

    def reset_shortcuts(self):
        """Reset all shortcuts to defaults."""
        self._shortcuts = DEFAULT_SHORTCUTS.copy()
        self.save()

    def reset_settings(self):
        """Reset all settings to defaults."""
        self._settings = DEFAULT_SETTINGS.copy()
        self.save()

    def restore_all_defaults(self):
        """Restore all defaults by deleting config files."""
        # Delete config files if they exist
        if self.settings_file.exists():
            self.settings_file.unlink()
        if self.shortcuts_file.exists():
            self.shortcuts_file.unlink()

        # Reset in-memory values to defaults
        self._settings = DEFAULT_SETTINGS.copy()
        self._shortcuts = DEFAULT_SHORTCUTS.copy()

        # Emit signals for all settings to update UI
        for key, value in self._settings.items():
            self.settings_changed.emit(key, value)

        # Emit signals for all shortcuts
        for action, shortcut in self._shortcuts.items():
            self.shortcut_changed.emit(action, shortcut)

    def add_recent_file(self, file_path: Path):
        """Add a file to the recent files list."""
        recent = self.get("files.recent_files", [])
        path_str = str(file_path.resolve())

        # Remove if already exists
        if path_str in recent:
            recent.remove(path_str)

        # Add to front
        recent.insert(0, path_str)

        # Trim to max
        max_recent = self.get("files.max_recent_files", 10)
        recent = recent[:max_recent]

        self.set("files.recent_files", recent)

    def get_recent_files(self) -> list[Path]:
        """Get list of recent files that still exist."""
        recent = self.get("files.recent_files", [])
        result = []
        for path_str in recent:
            path = Path(path_str)
            if path.exists():
                result.append(path)
        return result

    def clear_recent_files(self):
        """Clear the recent files list."""
        self.set("files.recent_files", [])


# Global settings instance
_settings: Settings | None = None


def init_settings(config_dir: Path | None = None, ephemeral: bool = False) -> Settings:
    """Initialize the global settings instance.

    Call this before get_settings() to customize settings behavior.

    Args:
        config_dir: Directory to store settings. Defaults to ~/.config/markdown-editor
        ephemeral: If True, use default settings in memory only - don't load or save.

    Returns:
        The initialized Settings instance.
    """
    global _settings
    _settings = Settings(config_dir=config_dir, ephemeral=ephemeral)
    return _settings


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

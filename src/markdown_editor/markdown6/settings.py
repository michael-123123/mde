"""Settings management for the Markdown editor."""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QStandardPaths, Signal

from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.session_state import SessionState
from markdown_editor.markdown6.shortcut_manager import (
    DEFAULT_SHORTCUTS,
    ShortcutManager,
)

logger = getLogger(__name__)


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
    "editor.scroll_past_end": True,
    # View settings
    "view.show_editor": True,
    "view.show_preview": True,
    "view.sync_scrolling": True,
    "view.theme": "light",  # light, dark
    "view.preview_font_size": 14,
    # Preview typography (empty = use built-in CSS font stack)
    "preview.body_font_family": "",
    "preview.code_font_family": "",
    "preview.heading_font_family": "",  # empty = inherit from body
    "preview.h1_size": 2.0,
    "preview.h1_size_unit": "em",
    "preview.h2_size": 1.5,
    "preview.h2_size_unit": "em",
    "preview.h3_size": 1.25,
    "preview.h3_size_unit": "em",
    "preview.h4_size": 1.0,
    "preview.h4_size_unit": "em",
    "preview.h5_size": 0.875,
    "preview.h5_size_unit": "em",
    "preview.h6_size": 0.85,
    "preview.h6_size_unit": "em",
    "preview.code_size": 85,
    "preview.code_size_unit": "%",
    "preview.line_height": 1.5,
    # File settings
    "files.detect_external_changes": True,
    # File visibility
    "files.show_hidden": False,
    # Logseq mode
    "view.logseq_mode": False,
    # External tool paths (empty string = use system PATH)
    "tools.pandoc_path": "",
    "tools.dot_path": "",
    "tools.mmdc_path": "",
}


# Re-exported for backward compatibility — canonical source is shortcut_manager.py
# DEFAULT_SHORTCUTS is imported above


MARKDOWN_EXTENSIONS = {".md", ".markdown"}
MARKDOWN_GLOBS = ["*.md", "*.markdown"]


def is_hidden_path(path: Path, root: Path) -> bool:
    """Check if any path component below root starts with '.'."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part.startswith('.') for part in rel.parts)


def get_project_markdown_files(
    project_path: Path,
    *,
    show_hidden: bool | None = None,
    max_depth: int | None = None,
) -> list[Path]:
    """Get all markdown files in a project directory, respecting hidden-file setting.

    Args:
        project_path: Root directory to scan.
        show_hidden: If None, reads from settings. If given, overrides.
        max_depth: If given, limit scan to this many directory levels.

    Returns:
        Sorted list of Path objects for .md/.markdown files.
    """
    if show_hidden is None:
        show_hidden = get_settings().get("files.show_hidden", False)

    if max_depth is not None:
        return sorted(_scan_limited_depth(project_path, max_depth, show_hidden))

    files = []
    for ext in MARKDOWN_GLOBS:
        files.extend(project_path.rglob(ext))
    if not show_hidden:
        files = [f for f in files if not is_hidden_path(f, project_path)]
    return sorted(files)


def _scan_limited_depth(
    root: Path, max_depth: int, show_hidden: bool
) -> list[Path]:
    """Scan directories up to max_depth levels, filtering hidden entries."""
    files: list[Path] = []

    def _walk(directory: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for child in directory.iterdir():
                if not show_hidden and child.name.startswith('.'):
                    continue
                if child.is_file() and child.suffix in MARKDOWN_EXTENSIONS:
                    files.append(child)
                elif child.is_dir() and depth < max_depth:
                    _walk(child, depth + 1)
        except PermissionError:
            pass

    _walk(root, 1)
    return files


def _default_config_dir() -> Path:
    """Return the platform-appropriate config directory for the editor."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericConfigLocation
    )
    return Path(base) / "markdown-editor"


class Settings(QObject):
    """Application settings manager with persistence."""

    settings_changed = Signal(str, object)  # key, new_value
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

        self._settings: dict[str, Any] = {}

        # Delegate shortcut management
        self._shortcut_manager = ShortcutManager(
            shortcuts_file=self.config_dir / "shortcuts.json",
            ephemeral=ephemeral,
        )
        # Expose the signal directly for backward compatibility
        self.shortcut_changed = self._shortcut_manager.shortcut_changed

        # Delegate session state management
        self._session_state = SessionState(
            state_file=self.config_dir / "session.json",
            ephemeral=ephemeral,
        )

        self.load()

    def load(self):
        """Load settings from disk (or use defaults if ephemeral)."""
        # Start with defaults
        self._settings = DEFAULT_SETTINGS.copy()

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
                logger.exception(f"Could not load settings from {self.settings_file}")

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
            logger.exception(f"Could not save settings to {self.settings_file}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        if SessionState.is_session_key(key):
            return self._session_state.get(key, default)
        return self._settings.get(key, default)

    def set(self, key: str, value: Any, save: bool = True):
        """Set a setting value."""
        if SessionState.is_session_key(key):
            self._session_state.set(key, value, save=save)
            # Also emit settings_changed for backward compatibility
            self.settings_changed.emit(key, value)
            return
        old_value = self._settings.get(key)
        self._settings[key] = value
        if save:
            self.save()
        if old_value != value:
            self.settings_changed.emit(key, value)
            if key == "view.theme":
                self.theme_changed.emit(value)

    @property
    def shortcuts(self) -> ShortcutManager:
        """Access the shortcut manager directly."""
        return self._shortcut_manager

    def get_shortcut(self, action: str) -> str:
        """Get a keyboard shortcut for an action."""
        return self._shortcut_manager.get_shortcut(action)

    def set_shortcut(self, action: str, shortcut: str, save: bool = True):
        """Set a keyboard shortcut for an action."""
        self._shortcut_manager.set_shortcut(action, shortcut, save=save)

    def get_all_shortcuts(self) -> dict[str, str]:
        """Get all keyboard shortcuts."""
        return self._shortcut_manager.get_all_shortcuts()

    def reset_shortcuts(self):
        """Reset all shortcuts to defaults."""
        self._shortcut_manager.reset_shortcuts()

    def reset_settings(self):
        """Reset all settings to defaults."""
        self._settings = DEFAULT_SETTINGS.copy()
        self.save()

    def restore_all_defaults(self):
        """Restore all defaults by deleting config files."""
        # Delete settings config file if it exists
        if self.settings_file.exists():
            self.settings_file.unlink()

        # Reset in-memory settings to defaults
        self._settings = DEFAULT_SETTINGS.copy()

        # Emit signals for all settings to update UI
        for key, value in self._settings.items():
            self.settings_changed.emit(key, value)

        # Restore shortcut defaults (handles file deletion and signals)
        self._shortcut_manager.restore_defaults()

        # Restore session state defaults (handles file deletion)
        self._session_state.restore_defaults()

    @property
    def session(self) -> SessionState:
        """Access the session state manager directly."""
        return self._session_state

    def add_recent_file(self, file_path: Path):
        """Add a file to the recent files list."""
        self._session_state.add_recent_file(file_path)

    def get_recent_files(self) -> list[Path]:
        """Get list of recent files that still exist."""
        return self._session_state.get_recent_files()

    def clear_recent_files(self):
        """Clear the recent files list."""
        self._session_state.clear_recent_files()


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

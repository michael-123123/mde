"""User preference management for the Markdown editor.

NON-QT-APPLICATION-SAFE: This module must remain loadable in non-Qt-application
environments (CLI exports use AppContext without a QApplication). QObject +
Signal from PySide6.QtCore are allowed. Do NOT add PySide6.QtWidgets or
QApplication dependencies. See local/html-export-unify.md §4 decision A.
"""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from markdown_editor.markdown6.logger import getLogger

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
    # Export font handling. False (default) → exported HTML uses the
    # user's `preview.*` font settings, matching the GUI preview. True
    # → renderer ignores user fonts and uses hardcoded canonical
    # defaults. Set only by the CLI's `--canonical-fonts` flag today;
    # a GUI Export-dialog checkbox is future work. Registered here so
    # the default is documented and doesn't persist on accidental
    # `set(..., False)` on a non-ephemeral ctx. See decision G in
    # local/html-export-unify.md.
    "export.use_canonical_fonts": False,
}


class SettingsManager(QObject):
    """Manages user preferences with persistence."""

    settings_changed = Signal(str, object)  # key, new_value
    theme_changed = Signal(str)  # theme name

    def __init__(self, settings_file: Path | None = None, ephemeral: bool = False):
        super().__init__()
        self._ephemeral = ephemeral
        self._settings_file = settings_file
        self._settings: dict[str, Any] = DEFAULT_SETTINGS.copy()

        if not ephemeral and settings_file is not None:
            self._load()

    def _load(self):
        """Load settings from disk."""
        if self._settings_file is None or not self._settings_file.exists():
            return
        try:
            with open(self._settings_file) as f:
                saved = json.load(f)
            self._settings.update(saved)
        except (json.JSONDecodeError, OSError):
            logger.exception(f"Could not load settings from {self._settings_file}")

    def save(self):
        """Save settings to disk (no-op if ephemeral)."""
        if self._ephemeral or self._settings_file is None:
            return
        settings_to_save = {
            k: v for k, v in self._settings.items()
            if k not in DEFAULT_SETTINGS or v != DEFAULT_SETTINGS[k]
        }
        try:
            from markdown_editor.markdown6.temp_files import atomic_write
            atomic_write(self._settings_file, json.dumps(settings_to_save, indent=2))
        except OSError:
            logger.exception(f"Could not save settings to {self._settings_file}")

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

    def reset(self):
        """Reset all settings to defaults."""
        self._settings = DEFAULT_SETTINGS.copy()
        self.save()

    def restore_defaults(self):
        """Restore defaults, delete file, and emit signals for all settings."""
        if self._settings_file is not None and self._settings_file.exists():
            self._settings_file.unlink()
        self._settings = DEFAULT_SETTINGS.copy()
        for key, value in self._settings.items():
            self.settings_changed.emit(key, value)

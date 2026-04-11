"""Keyboard shortcut management for the Markdown editor."""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


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


class ShortcutManager(QObject):
    """Manages keyboard shortcuts with persistence."""

    shortcut_changed = Signal(str, str)  # action, new_shortcut

    def __init__(self, shortcuts_file: Path | None = None, ephemeral: bool = False):
        super().__init__()
        self._ephemeral = ephemeral
        self._shortcuts_file = shortcuts_file
        self._shortcuts: dict[str, str] = DEFAULT_SHORTCUTS.copy()

        if not ephemeral and shortcuts_file is not None:
            self._load()

    def _load(self):
        """Load shortcuts from disk."""
        if self._shortcuts_file is None or not self._shortcuts_file.exists():
            return
        try:
            with open(self._shortcuts_file) as f:
                saved = json.load(f)
            self._shortcuts.update(saved)
        except (json.JSONDecodeError, OSError):
            logger.exception(f"Could not load shortcuts from {self._shortcuts_file}")

    def save(self):
        """Save shortcuts to disk (no-op if ephemeral)."""
        if self._ephemeral or self._shortcuts_file is None:
            return
        shortcuts_to_save = {
            k: v for k, v in self._shortcuts.items()
            if k not in DEFAULT_SHORTCUTS or v != DEFAULT_SHORTCUTS[k]
        }
        try:
            from markdown_editor.markdown6.temp_files import atomic_write
            atomic_write(self._shortcuts_file, json.dumps(shortcuts_to_save, indent=2))
        except OSError:
            logger.exception(f"Could not save shortcuts to {self._shortcuts_file}")

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

    def restore_defaults(self):
        """Restore defaults, delete file, and emit signals for all shortcuts."""
        if self._shortcuts_file is not None and self._shortcuts_file.exists():
            self._shortcuts_file.unlink()
        self._shortcuts = DEFAULT_SHORTCUTS.copy()
        for action, shortcut in self._shortcuts.items():
            self.shortcut_changed.emit(action, shortcut)

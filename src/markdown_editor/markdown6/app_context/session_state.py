"""Session state persistence for the Markdown editor.

Manages ephemeral application state that is remembered between sessions
but is not a user preference - recent files, last project, open tabs,
sidebar state, etc.

NON-QT-APPLICATION-SAFE: This module must remain loadable in non-Qt-application
environments (CLI exports use AppContext without a QApplication). QObject +
Signal from PySide6.QtCore are allowed. Do NOT add PySide6.QtWidgets or
QApplication-requiring code. See local/html-export-unify.md §4 decision A.
"""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


# Keys and their defaults - these are "what was open last time" state,
# not user preferences.
DEFAULT_SESSION_STATE = {
    "files.recent_files": [],
    "files.max_recent_files": 10,
    "project.last_path": None,
    "project.open_files": [],
    "project.active_tab": 0,
    "project.restore_tree_state": True,
    "project.expanded_dirs": [],
    "sidebar.collapsed": False,
    "sidebar.active_panel": 0,
}

# Keys that are user preferences about session behavior (shown in settings dialog)
# vs pure state. We keep them here because they're session-related, but they
# are conceptually "preferences about session restore."
SESSION_PREFERENCE_KEYS = {"files.max_recent_files", "project.restore_tree_state"}


class SessionState(QObject):
    """Manages application session state with persistence."""

    state_changed = Signal(str, object)  # key, new_value

    def __init__(self, state_file: Path | None = None, ephemeral: bool = False):
        super().__init__()
        self._ephemeral = ephemeral
        self._state_file = state_file
        self._state: dict[str, Any] = DEFAULT_SESSION_STATE.copy()

        if not ephemeral and state_file is not None:
            self._load()

    def _load(self):
        """Load session state from disk."""
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            with open(self._state_file) as f:
                saved = json.load(f)
            self._state.update(saved)
        except (json.JSONDecodeError, OSError):
            logger.exception(f"Could not load session state from {self._state_file}")

    def save(self):
        """Save session state to disk (no-op if ephemeral)."""
        if self._ephemeral or self._state_file is None:
            return
        state_to_save = {
            k: v for k, v in self._state.items()
            if k not in DEFAULT_SESSION_STATE or v != DEFAULT_SESSION_STATE[k]
        }
        try:
            from markdown_editor.markdown6.temp_files import atomic_write
            atomic_write(self._state_file, json.dumps(state_to_save, indent=2))
        except OSError:
            logger.exception(f"Could not save session state to {self._state_file}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a session state value."""
        return self._state.get(key, default)

    def set(self, key: str, value: Any, save: bool = True):
        """Set a session state value."""
        old_value = self._state.get(key)
        self._state[key] = value
        if save:
            self.save()
        if old_value != value:
            self.state_changed.emit(key, value)

    @staticmethod
    def is_session_key(key: str) -> bool:
        """Check if a key belongs to session state."""
        return key in DEFAULT_SESSION_STATE

    def add_recent_file(self, file_path: Path):
        """Add a file to the recent files list."""
        recent = self.get("files.recent_files", [])
        path_str = str(file_path.resolve())

        if path_str in recent:
            recent.remove(path_str)

        recent.insert(0, path_str)

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

    def restore_defaults(self):
        """Restore defaults and delete state file."""
        if self._state_file is not None and self._state_file.exists():
            self._state_file.unlink()
        self._state = DEFAULT_SESSION_STATE.copy()

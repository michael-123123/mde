"""Application context — settings, shortcuts, and session state.

NON-QT-APPLICATION-SAFE: This module (and its subpackages) must remain
loadable in non-Qt-application environments. AppContext is used by
`html_renderer_core` which runs in CLI exports without a QApplication.
QObject + Signal from PySide6.QtCore are allowed (they work without an
event loop). Do NOT introduce dependencies on PySide6.QtWidgets,
QApplication, or anything requiring the GUI to be up. Violations silently
break `mde export`. See local/html-export-unify.md §4 decision A.
"""

import copy as _copy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QStandardPaths

from markdown_editor.markdown6.app_context.session_state import SessionState
from markdown_editor.markdown6.app_context.settings_manager import (
    DEFAULT_SETTINGS,
    SettingsManager,
)
from markdown_editor.markdown6.app_context.shortcut_manager import (
    DEFAULT_SHORTCUTS,
    ShortcutManager,
)

# Re-export subsystem classes so callers can import from app_context directly
__all__ = [
    "AppContext",
    "DEFAULT_SETTINGS",
    "DEFAULT_SHORTCUTS",
    "MARKDOWN_EXTENSIONS",
    "MARKDOWN_GLOBS",
    "SessionState",
    "SettingsManager",
    "ShortcutManager",
    "get_app_context",
    "get_project_markdown_files",
    "init_app_context",
    "is_hidden_path",
]


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
        show_hidden = get_app_context().get("files.show_hidden", False)

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


class AppContext(QObject):
    """Application context: facade over settings, shortcuts, and session state."""

    def __init__(self, config_dir: Path | None = None, ephemeral: bool = False):
        """Initialize the application context.

        Args:
            config_dir: Directory to store config files. Platform-appropriate default.
            ephemeral: If True, use defaults in memory only - don't load or save.
        """
        super().__init__()
        self._ephemeral = ephemeral

        if config_dir is None:
            config_dir = _default_config_dir()
        self.config_dir = config_dir

        if not ephemeral:
            self.config_dir.mkdir(parents=True, exist_ok=True)

        # Delegate settings management
        self._settings_manager = SettingsManager(
            settings_file=self.config_dir / "settings.json",
            ephemeral=ephemeral,
        )
        # Expose signals directly
        self.settings_changed = self._settings_manager.settings_changed
        self.theme_changed = self._settings_manager.theme_changed

        # Delegate shortcut management
        self._shortcut_manager = ShortcutManager(
            shortcuts_file=self.config_dir / "shortcuts.json",
            ephemeral=ephemeral,
        )
        self.shortcut_changed = self._shortcut_manager.shortcut_changed

        # Delegate session state management
        self._session_state = SessionState(
            state_file=self.config_dir / "session.json",
            ephemeral=ephemeral,
        )

        # Plugin registry — populated by MarkdownEditor after startup
        # plugin load completes. Consumed by Settings → Plugins tab.
        self._plugins: list = []

        # Lazy notification center; created on first access. In-memory
        # only (no persistence across restarts) per Phase 3 plan.
        self._notifications = None

    @property
    def notifications(self):
        """Return the per-context :class:`NotificationCenter`.

        Created lazily so the import cost is only paid by code paths
        that actually use it.
        """
        if self._notifications is None:
            from markdown_editor.markdown6.notifications import (
                NotificationCenter,
            )
            self._notifications = NotificationCenter()
        return self._notifications

    # --- Plugins ---

    def set_plugins(self, plugins: list) -> None:
        """Called by the editor after load_all() completes."""
        self._plugins = list(plugins)

    def get_plugins(self) -> list:
        """Return the list of discovered plugins (may be empty)."""
        return list(self._plugins)

    def plugin_settings(self, plugin_id: str) -> "PluginSettings":
        """Return a dict-like façade scoped to ``plugin_id``.

        Storage is the main settings file with namespaced keys
        ``plugins.<plugin_id>.<key>``. Plugin ids must be non-empty
        and must not contain ``.`` (which would let one plugin write
        into another plugin's namespace).
        """
        from markdown_editor.markdown6.plugins.scoped_settings import (
            PluginSettings,
        )
        return PluginSettings(self, plugin_id)

    # --- Settings delegation ---

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting or session state value."""
        if SessionState.is_session_key(key):
            return self._session_state.get(key, default)
        return self._settings_manager.get(key, default)

    def set(self, key: str, value: Any, save: bool = True):
        """Set a setting or session state value."""
        if SessionState.is_session_key(key):
            self._session_state.set(key, value, save=save)
            # Also emit settings_changed so widgets listening for any key update
            self.settings_changed.emit(key, value)
            return
        self._settings_manager.set(key, value, save=save)

    def reset_settings(self):
        """Reset all settings to defaults."""
        self._settings_manager.reset()

    # --- Shortcut delegation ---

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

    # --- Session state delegation ---

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

    # --- Restore all ---

    def restore_all_defaults(self):
        """Restore all defaults by deleting config files."""
        self._settings_manager.restore_defaults()
        self._shortcut_manager.restore_defaults()
        self._session_state.restore_defaults()

    # --- Ephemeral copy (for export paths, decision E) ---

    def ephemeral_copy(self) -> "AppContext":
        """Return an ephemeral AppContext with the same state as `self`.

        The returned instance:
          - Is independent — mutations on it do NOT affect `self`.
          - Starts with copies of `self`'s settings, shortcuts, and
            session-state dicts.
          - Is ephemeral — calling `.set(...)` on it never writes to disk.
          - Has its own signal connections (nothing wired to the original).

        Intended for export paths that need to override a few settings
        (e.g. `editor.scroll_past_end=False` for HTML export) without
        polluting the live AppContext. See local/html-export-unify.md §4
        decision E.

        Named `ephemeral_copy` (not `copy` or `clone`) to make the
        ephemerality unambiguous — callers should not persist or share
        the returned instance.

        Uses `copy.deepcopy` on the inner state dicts so nested mutable
        containers (e.g. `files.recent_files: list`) cannot leak back to
        the original. A shallow `dict(...)` copy would share those list
        references and silently break the independence contract.
        """
        clone = AppContext(ephemeral=True)
        clone._settings_manager._settings = _copy.deepcopy(self._settings_manager._settings)
        clone._shortcut_manager._shortcuts = _copy.deepcopy(self._shortcut_manager._shortcuts)
        clone._session_state._state = _copy.deepcopy(self._session_state._state)
        return clone


# Global instance
_app_context: AppContext | None = None


def init_app_context(config_dir: Path | None = None, ephemeral: bool = False) -> AppContext:
    """Initialize the global AppContext instance.

    Call this before get_app_context() to customize behavior.

    Args:
        config_dir: Directory to store settings. Defaults to ~/.config/markdown-editor
        ephemeral: If True, use default settings in memory only - don't load or save.

    Returns:
        The initialized AppContext instance.
    """
    global _app_context
    _app_context = AppContext(config_dir=config_dir, ephemeral=ephemeral)
    return _app_context


def get_app_context() -> AppContext:
    """Get the global AppContext instance."""
    global _app_context
    if _app_context is None:
        _app_context = AppContext()
    return _app_context

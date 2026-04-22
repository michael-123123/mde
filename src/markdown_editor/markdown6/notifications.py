"""In-memory notification center for non-modal events.

Plugin runtime errors, future background-job completions, and other
non-critical notifications all post here. The bell icon in the editor's
status bar reads from this center; clicking the bell opens a drawer
showing the history.

Storage is **in-memory only** — notifications survive tab close but are
not persisted to disk. That's the v1 scope agreed in the plan; if a
"persist last N notifications across restarts" need emerges later,
add a JSON-roundtrip method here without changing the public surface.

Inline external-change notices (the per-tab ``ExternalChangeBar``) are
deliberately separate — they're modal-ish to the document and shouldn't
get lost in a global drawer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from PySide6.QtCore import QObject, Signal


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Notification:
    title: str
    message: str = ""
    severity: Severity = Severity.INFO
    source: str = ""    # "plugin:<id>", "system", "task", etc.
    timestamp: datetime = field(default_factory=datetime.now)
    read: bool = False


_DEFAULT_MAX_HISTORY = 200


class NotificationCenter(QObject):
    """Append-only notification log with read/unread tracking."""

    notification_added = Signal(Notification)
    unread_count_changed = Signal(int)

    def __init__(self, *, max_history: int = _DEFAULT_MAX_HISTORY) -> None:
        super().__init__()
        self._items: list[Notification] = []
        self.max_history = max_history

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def post(self, notification: Notification) -> None:
        old_unread = self.unread_count()
        self._items.append(notification)
        self._trim_history()
        self.notification_added.emit(notification)
        new_unread = self.unread_count()
        if new_unread != old_unread:
            self.unread_count_changed.emit(new_unread)

    def post_info(self, title: str, message: str = "", *, source: str = "") -> None:
        self.post(Notification(
            title=title, message=message,
            severity=Severity.INFO, source=source,
        ))

    def post_warning(self, title: str, message: str = "", *, source: str = "") -> None:
        self.post(Notification(
            title=title, message=message,
            severity=Severity.WARNING, source=source,
        ))

    def post_error(self, title: str, message: str = "", *, source: str = "") -> None:
        self.post(Notification(
            title=title, message=message,
            severity=Severity.ERROR, source=source,
        ))

    def mark_all_read(self) -> None:
        if self.unread_count() == 0:
            return
        for n in self._items:
            n.read = True
        self.unread_count_changed.emit(0)

    def clear(self) -> None:
        had_unread = self.unread_count() > 0
        self._items.clear()
        if had_unread:
            self.unread_count_changed.emit(0)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all(self) -> list[Notification]:
        return list(self._items)

    def unread_count(self) -> int:
        return sum(1 for n in self._items if not n.read)

    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        if len(self._items) > self.max_history:
            del self._items[: len(self._items) - self.max_history]


def _post_plugin_error(plugin_name: str, title: str, message: str) -> None:
    """Helper used by plugin error catches throughout the editor.

    Looks up the AppContext singleton lazily — works during editor
    runtime AND in tests where an ephemeral context is set up by the
    autouse fixture. Tolerates the case where AppContext isn't
    initialized at all (degrades to a no-op so plugin error catches
    can't break the editor by trying to notify).
    """
    try:
        from markdown_editor.markdown6.app_context import get_app_context
        ctx = get_app_context()
    except Exception:    # noqa: BLE001 — degrade gracefully
        return
    source = f"plugin:{plugin_name}" if plugin_name else "plugin"
    ctx.notifications.post_error(title, message, source=source)

"""Plugin-facing handle to the currently active document.

Plugins receive a :class:`DocumentHandle` (rather than the raw
:class:`DocumentTab` or :class:`QPlainTextEdit`) so that:

* We can refactor ``DocumentTab``/``EnhancedEditor`` internals without
  breaking plugins that only use the documented API.
* Every mutator routes through :class:`QTextCursor` with
  ``beginEditBlock`` / ``endEditBlock`` so a single logical plugin
  operation appears as a single ``Ctrl+Z`` step to the user.
* :meth:`atomic_edit` guarantees that on exception the document is
  byte-identical to the pre-block state, honouring the "no partly
  modified state" rule.

The handle requires a "tab-like" object with three attributes:
``editor`` (a ``QPlainTextEdit``), ``file_path`` (``Path | None``),
and ``unsaved_changes`` (``bool``). The real :class:`DocumentTab`
naturally provides all three; tests pass a ``SimpleNamespace``.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from PySide6.QtGui import QTextCursor


class DocumentHandle:
    def __init__(self, tab: Any) -> None:
        self._tab = tab
        self._editor = tab.editor

    # --- Reads ---------------------------------------------------------------

    @property
    def text(self) -> str:
        return self._editor.toPlainText()

    # --- Escape hatches (Qt access; explicitly opt-in / not stable) ---------

    @property
    def editor(self):
        """Underlying ``QPlainTextEdit`` — escape hatch, not stable.

        Plugins that need fine-grained Qt control (custom selection
        manipulation, signal connections, etc.) reach into this. The
        documented Qt-free API (text, replace_all, atomic_edit, etc.)
        should cover most use cases; this is for the cases it doesn't.
        """
        return self._editor

    @property
    def preview(self):
        """Underlying preview widget (typically ``QWebEngineView``) or
        ``None`` if the wrapping tab doesn't have one. Escape hatch."""
        return getattr(self._tab, "preview", None)

    @property
    def file_path(self) -> Path | None:
        return getattr(self._tab, "file_path", None)

    @property
    def has_selection(self) -> bool:
        return bool(self._editor.textCursor().hasSelection())

    @property
    def is_dirty(self) -> bool:
        return bool(getattr(self._tab, "unsaved_changes", False))

    # --- Mutators ------------------------------------------------------------

    def replace_all(self, new_text: str) -> None:
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.removeSelectedText()
            cursor.insertText(new_text)
        finally:
            cursor.endEditBlock()

    def replace_range(self, start: int, end: int, text: str) -> None:
        length = len(self.text)
        if start < 0 or end < start or end > length:
            raise ValueError(
                f"replace_range: [{start}, {end}) out of bounds for "
                f"document length {length}"
            )
        cursor = QTextCursor(self._editor.document())
        cursor.beginEditBlock()
        try:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(text)
        finally:
            cursor.endEditBlock()

    def insert_at_cursor(self, text: str) -> None:
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertText(text)
        finally:
            cursor.endEditBlock()

    def wrap_selection(self, before: str, after: str) -> None:
        cursor = self._editor.textCursor()
        selected = cursor.selectedText()
        cursor.beginEditBlock()
        try:
            cursor.insertText(before + selected + after)
        finally:
            cursor.endEditBlock()

    def move_cursor(self, offset: int) -> None:
        cursor = self._editor.textCursor()
        new_pos = max(0, min(cursor.position() + offset, len(self.text)))
        cursor.setPosition(new_pos)
        self._editor.setTextCursor(cursor)

    # --- Atomic edits --------------------------------------------------------

    @contextmanager
    def atomic_edit(self) -> Iterator[None]:
        """Group edits into one undo step; restore on exception.

        On clean exit, all edits made inside the ``with`` block are
        grouped into a single ``Ctrl+Z`` step. On exception, the
        document text is restored exactly to its pre-block state and
        the ``unsaved_changes`` flag is reset to what it was before
        the block started. The exception is then re-raised.
        """
        snapshot = self._editor.toPlainText()
        snapshot_dirty = bool(getattr(self._tab, "unsaved_changes", False))

        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        try:
            yield
        except BaseException:
            cursor.endEditBlock()
            if self._editor.toPlainText() != snapshot:
                # Restore via the cursor (not ``setPlainText``). Qt's
                # ``QPlainTextEdit.setPlainText`` emits
                # ``modificationChanged(True)`` but silently drops the
                # subsequent True→False transition, which leaves any UI
                # subscribed to that signal (tab-title ``*`` marker,
                # window title) out of sync with the document's actual
                # modified state. The cursor-based path emits both
                # edges correctly.
                restore = QTextCursor(self._editor.document())
                restore.beginEditBlock()
                try:
                    restore.select(QTextCursor.SelectionType.Document)
                    restore.removeSelectedText()
                    restore.insertText(snapshot)
                finally:
                    restore.endEditBlock()
            # Drive the dirty flag via the document's modification state.
            # On a real ``DocumentTab`` this propagates through the
            # ``modificationChanged`` signal to the derived
            # ``unsaved_changes`` property and refreshes the tab title.
            # SimpleNamespace test stubs keep whatever ``unsaved_changes``
            # value the test set up — no write needed (and would fail
            # against a read-only property on a real tab).
            self._editor.document().setModified(snapshot_dirty)
            raise
        else:
            cursor.endEditBlock()

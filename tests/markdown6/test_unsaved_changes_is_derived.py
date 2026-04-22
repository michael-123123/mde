"""``DocumentTab.unsaved_changes`` is a read-only ``@property`` derived
from ``self.editor.document().isModified()``.

The previous design kept ``unsaved_changes`` as a mutable attribute
synced by convention: every site that reset content had to also call
``document().setModified(False)`` so the modificationChanged signal
would propagate to the attribute. That's discipline-based sync — a
missed call site would leave the flag and the document's actual
modification state inconsistent with no compiler / type help.

Making it a derived property eliminates the sync problem structurally:
there's only one source of truth, ``document().isModified()``, and the
attribute simply returns it. Direct assignment raises ``AttributeError``
so stragglers that try to write the old way surface immediately.

See ``local/tech-debt/dirty-flag-one-way-ratchet.md`` Option C.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_unsaved_changes_tracks_document_isModified(qtbot) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None

    # Fresh tab: document is unmodified, property returns False.
    assert tab.editor.document().isModified() is False
    assert tab.unsaved_changes is False

    # Flip the document's modified flag; the property follows.
    tab.editor.document().setModified(True)
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    tab.editor.document().setModified(False)
    QApplication.processEvents()
    assert tab.unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_unsaved_changes_is_read_only(qtbot) -> None:
    """Direct assignment must raise — the property has no setter."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None

    with pytest.raises(AttributeError):
        tab.unsaved_changes = True


@pytest.mark.timeout(15, method="thread")
def test_undo_to_pristine_clears_unsaved_changes_via_property(qtbot) -> None:
    """Regression coverage for the original one-way-ratchet bug, now
    expressed in terms of the derived property rather than an attribute
    write."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab.unsaved_changes is False

    tab.editor.insertPlainText("hello")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    while tab.editor.document().isUndoAvailable():
        tab.editor.undo()
    QApplication.processEvents()
    assert tab.editor.toPlainText() == ""
    assert tab.unsaved_changes is False

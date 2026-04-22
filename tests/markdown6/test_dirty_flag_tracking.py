"""``DocumentTab.unsaved_changes`` must track the document's modification
state bidirectionally.

Bug (pre-fix): ``_on_text_changed`` is subscribed to the unidirectional
``QPlainTextEdit.textChanged`` signal. It flips ``unsaved_changes`` to
``True`` on any edit but never flips it back when the user undoes every
edit and returns to the original (unmodified) state. Any test name with
``undo`` in it below fails before the fix and passes after.

Post-fix design: ``unsaved_changes`` mirrors
``QTextDocument.isModified()``, driven by the ``modificationChanged(bool)``
signal. Baselining happens at construction, after file load, and after
save.

See ``local/tech-debt/dirty-flag-one-way-ratchet.md`` for the write-up.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_fresh_tab_is_not_dirty(qtbot) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None
    assert tab.unsaved_changes is False
    assert tab.editor.document().isModified() is False


@pytest.mark.timeout(15, method="thread")
def test_edit_marks_dirty(qtbot) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()

    tab.editor.insertPlainText("hello")
    QApplication.processEvents()
    assert tab.unsaved_changes is True


@pytest.mark.timeout(15, method="thread")
def test_undo_to_pristine_clears_dirty(qtbot) -> None:
    """Edit → undo-to-empty → tab should be clean. Core Bug B repro."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()

    tab.editor.insertPlainText("hello")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    while tab.editor.document().isUndoAvailable():
        tab.editor.undo()
    QApplication.processEvents()

    assert tab.editor.toPlainText() == ""
    assert tab.unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_open_file_creates_clean_tab(qtbot, tmp_path) -> None:
    """Opening a file yields a non-dirty tab."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    path = tmp_path / "test.md"
    path.write_text("initial content", encoding="utf-8")

    editor.open_file(str(path))
    tab = editor.current_tab()
    assert tab is not None
    assert tab.unsaved_changes is False
    assert tab.editor.document().isModified() is False


@pytest.mark.timeout(15, method="thread")
def test_edit_then_undo_after_open_clears_dirty(qtbot, tmp_path) -> None:
    """Open a file, edit it, undo every edit: tab should be clean again."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    path = tmp_path / "test.md"
    path.write_text("initial content", encoding="utf-8")

    editor.open_file(str(path))
    tab = editor.current_tab()
    assert tab.unsaved_changes is False

    tab.editor.insertPlainText(" appended")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    while tab.editor.document().isUndoAvailable():
        tab.editor.undo()
    QApplication.processEvents()

    assert tab.editor.toPlainText() == "initial content"
    assert tab.unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_save_clears_dirty(qtbot, tmp_path) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    path = tmp_path / "test.md"
    path.write_text("initial", encoding="utf-8")
    editor.open_file(str(path))
    tab = editor.current_tab()

    tab.editor.insertPlainText(" more")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    assert editor.save_file() is True
    assert tab.unsaved_changes is False
    assert tab.editor.document().isModified() is False


@pytest.mark.timeout(15, method="thread")
def test_edit_then_undo_after_save_clears_dirty(qtbot, tmp_path) -> None:
    """After save, editing once and undoing that single edit should bring
    the tab back to the post-save baseline (buffer + clean flag).

    Note: ``save_file`` does not clear the undo stack — if the user undoes
    past the save point the document is modified again (in the reverse
    direction) which is correct behavior. The scenario this test guards
    is the common one: user makes one more edit after saving, changes
    their mind, hits Ctrl+Z, and the editor should stop nagging them.
    """
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    path = tmp_path / "test.md"
    path.write_text("initial", encoding="utf-8")
    editor.open_file(str(path))
    tab = editor.current_tab()

    # edit + save so we have a post-save baseline that differs from the
    # on-disk initial content
    tab.editor.insertPlainText(" x")
    editor.save_file()
    saved_content = tab.editor.toPlainText()
    assert tab.unsaved_changes is False

    # one more edit, then undo just that one edit
    tab.editor.insertPlainText(" y")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    tab.editor.undo()
    QApplication.processEvents()

    assert tab.editor.toPlainText() == saved_content
    assert tab.unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_reload_file_clears_dirty(qtbot, tmp_path) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    path = tmp_path / "test.md"
    path.write_text("initial", encoding="utf-8")
    editor.open_file(str(path))
    tab = editor.current_tab()

    tab.editor.insertPlainText(" dirty")
    QApplication.processEvents()
    assert tab.unsaved_changes is True

    tab.reload_file()
    QApplication.processEvents()

    assert tab.editor.toPlainText() == "initial"
    assert tab.unsaved_changes is False
    assert tab.editor.document().isModified() is False

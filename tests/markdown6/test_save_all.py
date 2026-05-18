"""Tests for ``MarkdownEditor.save_all`` (File → Save All).

The method writes every dirty tab. Tabs with a ``file_path`` are written
inline; untitled tabs are routed through the Save-As dialog so the user
gets one prompt per untitled tab. A cancelled dialog skips that tab but
does not abort the rest.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QFileDialog

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


def _make_dirty_tab(editor: MarkdownEditor, path, text: str) -> None:
    """Open ``path`` in a new tab and modify it so it's dirty on disk."""
    editor.open_file(str(path))
    tab = editor.current_tab()
    assert tab is not None
    cursor = tab.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    tab.editor.setTextCursor(cursor)
    tab.editor.insertPlainText(text)
    QApplication.processEvents()
    assert tab.unsaved_changes is True


@pytest.mark.timeout(15, method="thread")
def test_save_all_writes_only_dirty_tabs(qtbot, tmp_path) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f3 = tmp_path / "c.md"
    f1.write_text("aaa", encoding="utf-8")
    f2.write_text("bbb", encoding="utf-8")
    f3.write_text("ccc", encoding="utf-8")

    _make_dirty_tab(editor, f1, " EDIT1")
    _make_dirty_tab(editor, f2, " EDIT2")
    editor.open_file(str(f3))  # clean

    saved = editor.save_all()

    assert saved == 2
    assert f1.read_text(encoding="utf-8") == "aaa EDIT1"
    assert f2.read_text(encoding="utf-8") == "bbb EDIT2"
    assert f3.read_text(encoding="utf-8") == "ccc"
    for i in range(editor.tab_widget.count()):
        assert editor.tab_widget.widget(i).unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_save_all_with_nothing_dirty_is_a_noop(qtbot, tmp_path) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    f1 = tmp_path / "clean.md"
    f1.write_text("untouched", encoding="utf-8")
    editor.open_file(str(f1))

    saved = editor.save_all()

    assert saved == 0
    assert f1.read_text(encoding="utf-8") == "untouched"


@pytest.mark.timeout(15, method="thread")
def test_save_all_prompts_save_as_for_untitled_tab(qtbot, tmp_path, monkeypatch) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    editor.new_tab()
    untitled = editor.current_tab()
    assert untitled is not None
    untitled.editor.insertPlainText("fresh content")
    QApplication.processEvents()

    dest = tmp_path / "named.md"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: (str(dest), "Markdown Files (*.md)"),
    )

    saved = editor.save_all()

    assert saved >= 1
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "fresh content"
    assert untitled.file_path == dest
    assert untitled.unsaved_changes is False


@pytest.mark.timeout(15, method="thread")
def test_save_all_continues_when_user_cancels_an_untitled(qtbot, tmp_path, monkeypatch) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    f1 = tmp_path / "named.md"
    f1.write_text("orig", encoding="utf-8")
    _make_dirty_tab(editor, f1, " EDITED")

    editor.new_tab()
    untitled = editor.current_tab()
    assert untitled is not None
    untitled.editor.insertPlainText("never saved")
    QApplication.processEvents()

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: ("", ""),
    )

    saved = editor.save_all()

    assert saved == 1
    assert f1.read_text(encoding="utf-8") == "orig EDITED"
    assert untitled.unsaved_changes is True
    assert untitled.file_path is None


@pytest.mark.timeout(15, method="thread")
def test_save_all_restores_original_active_tab(qtbot, tmp_path, monkeypatch) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    f1 = tmp_path / "first.md"
    f1.write_text("first", encoding="utf-8")
    _make_dirty_tab(editor, f1, " edit")
    first_index = editor.tab_widget.currentIndex()

    editor.new_tab()
    untitled = editor.current_tab()
    assert untitled is not None
    untitled.editor.insertPlainText("scratch")
    QApplication.processEvents()

    editor.tab_widget.setCurrentIndex(first_index)
    assert editor.tab_widget.currentIndex() == first_index

    dest = tmp_path / "scratch.md"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: (str(dest), "Markdown Files (*.md)"),
    )

    editor.save_all()

    assert editor.tab_widget.currentIndex() == first_index

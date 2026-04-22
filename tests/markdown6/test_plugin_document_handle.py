"""Tests for the plugin-facing DocumentHandle."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.plugins.document_handle import DocumentHandle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(qtbot, text: str = "", dirty: bool = False) -> tuple[DocumentHandle, QPlainTextEdit, SimpleNamespace]:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=dirty)
    return DocumentHandle(tab), editor, tab


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_text_property(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "hello\nworld")
    assert doc.text == "hello\nworld"


def test_has_selection_false_by_default(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "abc")
    assert doc.has_selection is False


def test_has_selection_true_when_selected(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "abcdef")
    cur = editor.textCursor()
    cur.setPosition(0)
    cur.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cur)
    assert doc.has_selection is True


def test_is_dirty_reflects_tab_flag(qtbot) -> None:
    doc, _, tab = _make_handle(qtbot, "x", dirty=False)
    assert doc.is_dirty is False
    tab.unsaved_changes = True
    assert doc.is_dirty is True


# ---------------------------------------------------------------------------
# replace_all
# ---------------------------------------------------------------------------


def test_replace_all_replaces_text(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "before")
    doc.replace_all("after")
    assert editor.toPlainText() == "after"


def test_replace_all_is_single_undo_step(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "original")
    doc.replace_all("modified")
    assert editor.toPlainText() == "modified"
    editor.undo()
    assert editor.toPlainText() == "original"


def test_replace_all_empty_string(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "anything")
    doc.replace_all("")
    assert editor.toPlainText() == ""


# ---------------------------------------------------------------------------
# replace_range
# ---------------------------------------------------------------------------


def test_replace_range_replaces_substring(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "hello world")
    doc.replace_range(6, 11, "Python")
    assert editor.toPlainText() == "hello Python"


def test_replace_range_insertion_when_start_equals_end(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "abcdef")
    doc.replace_range(3, 3, "XYZ")
    assert editor.toPlainText() == "abcXYZdef"


def test_replace_range_out_of_bounds_raises(qtbot) -> None:
    doc, _, _ = _make_handle(qtbot, "abc")
    with pytest.raises(ValueError):
        doc.replace_range(-1, 2, "x")
    with pytest.raises(ValueError):
        doc.replace_range(0, 99, "x")
    with pytest.raises(ValueError):
        doc.replace_range(2, 1, "x")   # end < start


# ---------------------------------------------------------------------------
# insert_at_cursor
# ---------------------------------------------------------------------------


def test_insert_at_cursor_at_start(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "world")
    cur = editor.textCursor()
    cur.setPosition(0)
    editor.setTextCursor(cur)
    doc.insert_at_cursor("hello ")
    assert editor.toPlainText() == "hello world"


def test_insert_at_cursor_replaces_selection(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "foo bar baz")
    cur = editor.textCursor()
    cur.setPosition(4)
    cur.setPosition(7, QTextCursor.MoveMode.KeepAnchor)   # select "bar"
    editor.setTextCursor(cur)
    doc.insert_at_cursor("QUX")
    assert editor.toPlainText() == "foo QUX baz"


# ---------------------------------------------------------------------------
# wrap_selection
# ---------------------------------------------------------------------------


def test_wrap_selection_around_selected(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "emphasize me")
    cur = editor.textCursor()
    cur.setPosition(0)
    cur.setPosition(9, QTextCursor.MoveMode.KeepAnchor)   # "emphasize"
    editor.setTextCursor(cur)
    doc.wrap_selection("**", "**")
    assert editor.toPlainText() == "**emphasize** me"


def test_wrap_selection_without_selection_inserts_empty_wrap(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "abc")
    cur = editor.textCursor()
    cur.setPosition(1)   # between a and b
    editor.setTextCursor(cur)
    doc.wrap_selection("[", "]")
    assert editor.toPlainText() == "a[]bc"


# ---------------------------------------------------------------------------
# move_cursor
# ---------------------------------------------------------------------------


def test_move_cursor_forward_and_back(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "hello")
    cur = editor.textCursor()
    cur.setPosition(0)
    editor.setTextCursor(cur)
    doc.move_cursor(3)
    assert editor.textCursor().position() == 3
    doc.move_cursor(-2)
    assert editor.textCursor().position() == 1


def test_move_cursor_clamps_to_document_bounds(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "abc")
    doc.move_cursor(-999)
    assert editor.textCursor().position() == 0
    doc.move_cursor(999)
    assert editor.textCursor().position() == 3


# ---------------------------------------------------------------------------
# atomic_edit
# ---------------------------------------------------------------------------


def test_atomic_edit_commits_on_clean_exit(qtbot) -> None:
    doc, editor, _ = _make_handle(qtbot, "start")
    with doc.atomic_edit():
        doc.replace_all("new1")
        doc.replace_all("new2")
    assert editor.toPlainText() == "new2"


def test_atomic_edit_single_undo_on_clean_exit(qtbot) -> None:
    """Multi-step edits inside atomic_edit must collapse to one Ctrl+Z."""
    doc, editor, _ = _make_handle(qtbot, "start")
    with doc.atomic_edit():
        doc.replace_all("stage1")
        doc.replace_all("stage2")
    editor.undo()
    assert editor.toPlainText() == "start"


def test_atomic_edit_rolls_back_on_exception(qtbot) -> None:
    doc, editor, tab = _make_handle(qtbot, "pristine")
    with pytest.raises(RuntimeError, match="boom"):
        with doc.atomic_edit():
            doc.replace_all("halfway")
            raise RuntimeError("boom")
    assert editor.toPlainText() == "pristine"


def test_atomic_edit_rollback_preserves_dirty_flag(qtbot) -> None:
    """If the doc was clean pre-block and the plugin errors, it stays clean."""
    doc, editor, tab = _make_handle(qtbot, "clean", dirty=False)
    with pytest.raises(ValueError):
        with doc.atomic_edit():
            doc.replace_all("dirtied")
            raise ValueError
    assert editor.toPlainText() == "clean"
    assert tab.unsaved_changes is False


def test_atomic_edit_rollback_preserves_previously_dirty_flag(qtbot) -> None:
    """If the doc was already dirty pre-block, it remains dirty after rollback."""
    doc, editor, tab = _make_handle(qtbot, "stuff", dirty=True)
    with pytest.raises(RuntimeError):
        with doc.atomic_edit():
            doc.replace_all("intermediate")
            raise RuntimeError
    assert editor.toPlainText() == "stuff"
    assert tab.unsaved_changes is True


def test_atomic_edit_exception_propagates(qtbot) -> None:
    doc, _, _ = _make_handle(qtbot, "x")

    class Custom(Exception):
        pass

    with pytest.raises(Custom):
        with doc.atomic_edit():
            raise Custom

    # No edits actually happened → text unchanged either way
    assert doc.text == "x"


def test_atomic_edit_nested_is_ok(qtbot) -> None:
    """Nested atomic_edit is allowed; outer context owns the commit/rollback."""
    doc, editor, _ = _make_handle(qtbot, "orig")
    with doc.atomic_edit():
        doc.replace_all("level1")
        with doc.atomic_edit():
            doc.replace_all("level2")
    assert editor.toPlainText() == "level2"

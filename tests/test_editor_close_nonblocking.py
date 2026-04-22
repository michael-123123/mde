"""Regression tests: ``MarkdownEditor.close()`` never blocks under test.

Before this branch, closing the editor with a dirty tab hung
indefinitely on a ``QMessageBox.question`` ("Save / Discard / Cancel")
modal that the test environment cannot dismiss. The fix is the
autouse autodismiss fixture in ``tests/conftest.py`` which replaces
``QMessageBox.{question,warning,critical,information}`` with
non-blocking stubs for the duration of the test session.

These two tests exercise both the clean and the dirty close paths -
they must both complete in well under a second.

See ``local/tech-debt/headless-close-dirty-tab-hang.md`` for the
diagnosis and fix write-up.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_close_clean_tab(qtbot) -> None:
    """Control: close with a non-dirty tab. No prompt path, no modal."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    editor.new_tab()
    # deliberately do NOT mutate tab.editor - leaves tab clean
    editor.close()
    QApplication.processEvents()


@pytest.mark.timeout(15, method="thread")
def test_close_dirty_tab_auto_discards(qtbot) -> None:
    """Close with a dirty tab proceeds because the autodismiss fixture
    returns ``Discard`` from the "unsaved changes" ``QMessageBox.question``.

    Without the fixture this hangs forever - see the ``tests/conftest.py``
    module docstring.
    """
    editor = MarkdownEditor()
    qtbot.addWidget(editor)

    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None
    tab.editor.setPlainText("any content — marks the doc modified")

    editor.close()
    QApplication.processEvents()

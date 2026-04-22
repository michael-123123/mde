"""``DocumentTab.render_timer`` must not outlive the tab.

Regression for a cross-test logging interaction: a DocumentTab created
in test N armed its 300ms debounced ``render_timer`` via
``textChanged``. If the tab was torn down before the timer elapsed and
no one stopped it, the timer survived into test N+1 and fired during
``pytest-qt``'s ``_process_events()`` in ``pytest_runtest_setup``. The
resulting ``logger.info(...)`` inside ``render_markdown`` hit pytest's
``LogCaptureHandler`` in the narrow window where its StringIO had
already been closed for test N but not yet reopened for test N+1,
producing ``ValueError: I/O operation on closed file.``

Fix: connect ``DocumentTab.destroyed`` to ``render_timer.stop`` so a
destroyed tab can never fire a render.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_destroyed_tab_stops_render_timer(qtbot) -> None:
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()
    assert tab is not None

    tab.editor.insertPlainText("hello")
    QApplication.processEvents()
    assert tab.render_timer.isActive(), (
        "precondition: an edit should arm the debounced render_timer"
    )

    timer = tab.render_timer
    tab.destroyed.emit()
    assert not timer.isActive(), (
        "a destroyed tab must not leave a live render_timer behind"
    )

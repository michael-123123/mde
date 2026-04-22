"""Preview keyboard scrolling syncs back to the editor (Gap 1).

Before the fix, the preview pane swallowed keyboard scroll input
(arrow keys, PageUp/Down, Home/End, Space) - it scrolled itself but
never told the editor. Only the mouse wheel was forwarded to the
editor via ``_PreviewWheelFilter``.

Fix: install an analogous ``_PreviewKeyFilter`` that intercepts scroll
keys on the preview and applies the equivalent scrollbar move to the
**editor** instead. The editor then syncs the preview back through
the existing ``_on_editor_scroll`` pipeline, so the two panes stay in
lockstep regardless of which pane the user is driving.

See ``local/tech-debt/scroll-sync-gaps.md`` for the full write-up.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from markdown_editor.markdown6.components.document_tab import _PreviewKeyFilter


class _FakeTab(QObject):
    """Minimal QObject stand-in for ``DocumentTab`` - enough shape for
    ``_PreviewKeyFilter`` to read ``editor``, ``_sync_scrolling``, and
    be parented to us. Avoids dragging the full ``MarkdownEditor`` (and
    ``QWebEngineView``) into tests that are about the filter's
    ``eventFilter`` logic.
    """

    def __init__(self, editor, preview):
        super().__init__()
        self.editor = editor
        self.preview = preview
        self._sync_scrolling = True


def _key(key, modifiers=Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


@pytest.fixture
def tab_with_long_content(qtbot):
    """Shown ``QPlainTextEdit`` with enough content that its scrollbar
    has range, wrapped in a ``_FakeTab``.
    """
    editor = QPlainTextEdit()
    editor.setPlainText("\n".join(f"line {i}" for i in range(500)))
    editor.resize(400, 200)
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    QApplication.processEvents()
    assert editor.verticalScrollBar().maximum() > 0, (
        "test precondition: editor must be tall enough to scroll"
    )
    tab = _FakeTab(editor=editor, preview=QObject())
    return tab


@pytest.mark.timeout(15, method="thread")
def test_down_scrolls_editor_one_line(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(0)

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_Down))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == vbar.singleStep()


@pytest.mark.timeout(15, method="thread")
def test_up_scrolls_editor_one_line_up(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(vbar.singleStep() * 5)
    start = vbar.value()

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_Up))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == start - vbar.singleStep()


@pytest.mark.timeout(15, method="thread")
def test_page_down_scrolls_one_page(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(0)

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_PageDown))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == vbar.pageStep()


@pytest.mark.timeout(15, method="thread")
def test_page_up_scrolls_one_page_up(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(vbar.pageStep() * 3)
    start = vbar.value()

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_PageUp))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == start - vbar.pageStep()


@pytest.mark.timeout(15, method="thread")
def test_space_behaves_like_page_down(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(0)

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_Space))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == vbar.pageStep()


@pytest.mark.timeout(15, method="thread")
def test_shift_space_behaves_like_page_up(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(vbar.pageStep() * 3)
    start = vbar.value()

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(
        tab.preview,
        _key(Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier),
    )
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == start - vbar.pageStep()


@pytest.mark.timeout(15, method="thread")
def test_home_scrolls_to_top(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(vbar.maximum() // 2)

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_Home))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == 0


@pytest.mark.timeout(15, method="thread")
def test_end_scrolls_to_bottom(tab_with_long_content) -> None:
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(0)

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_End))
    QApplication.processEvents()

    assert handled is True
    assert vbar.value() == vbar.maximum()


@pytest.mark.timeout(15, method="thread")
@pytest.mark.parametrize(
    "key",
    [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_A, Qt.Key.Key_Tab],
)
def test_non_scroll_keys_pass_through(tab_with_long_content, key) -> None:
    """Keys that aren't vertical scroll operations must not be consumed -
    the preview (or whatever is focused) should still receive them.
    """
    tab = tab_with_long_content
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(100)
    before = vbar.value()

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(key))
    QApplication.processEvents()

    assert handled is False
    assert vbar.value() == before


@pytest.mark.timeout(15, method="thread")
def test_sync_disabled_skips_filter(tab_with_long_content) -> None:
    """When ``_sync_scrolling`` is off (view.sync_scrolling setting
    disabled), the filter must not intercept - users who disabled sync
    shouldn't have preview keys silently rerouted.
    """
    tab = tab_with_long_content
    tab._sync_scrolling = False
    vbar = tab.editor.verticalScrollBar()
    vbar.setValue(100)
    before = vbar.value()

    filter_ = _PreviewKeyFilter(tab)
    handled = filter_.eventFilter(tab.preview, _key(Qt.Key.Key_Down))
    QApplication.processEvents()

    assert handled is False
    assert vbar.value() == before


@pytest.mark.timeout(15, method="thread")
def test_key_filter_attached_on_full_tab(qtbot) -> None:
    """Smoke test: constructing a real ``DocumentTab`` wires up a key
    filter, matching the wheel-filter wiring pattern.
    """
    from markdown_editor.markdown6.components.document_tab import (
        _PreviewKeyFilter as KeyFilterCls,
    )
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.new_tab()
    tab = editor.current_tab()

    if tab._use_webengine:
        assert hasattr(tab, "_key_filter")
        assert isinstance(tab._key_filter, KeyFilterCls)
    else:
        # QTextBrowser fallback: filter is installed directly on the
        # viewport without a named attribute; there's no clean public
        # probe, so we just confirm no exception was raised during
        # construction. The filter-class unit tests cover the logic.
        pass

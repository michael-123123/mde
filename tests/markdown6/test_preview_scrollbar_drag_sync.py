"""Dragging the preview's scrollbar must sync the editor.

Bug: Chromium's internal scrollbar emits neither ``Wheel`` nor
``KeyPress`` events when dragged - both existing event filters
(``_PreviewWheelFilter``, ``_PreviewKeyFilter``) miss it. The only
Qt-level surface is ``QWebEnginePage.scrollPositionChanged``, which
nothing listens to. So preview scrollbar drag → editor: silent.

Fix: connect ``scrollPositionChanged`` to a handler that queries the
preview's top-most ``data-source-line`` via JS and applies the result
to the editor's vertical scrollbar.

The forward direction (editor → ``scrollToSourceLine`` → preview) also
moves the preview's scroll position, which would re-fire
``scrollPositionChanged`` and ping-pong back. To avoid the loop we
debounce: when ``_on_editor_scroll`` runs it timestamps
``_last_editor_scroll_ms``; the reverse handler ignores any
``scrollPositionChanged`` within ``_REVERSE_SYNC_DEBOUNCE_MS`` of that
timestamp (treated as the echo of our own programmatic scroll).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, QPointF
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from markdown_editor.markdown6.components.document_tab import (
    DocumentTab,
    _REVERSE_SYNC_DEBOUNCE_MS,
)


class _FakePage:
    """Minimal stand-in for ``QWebEnginePage`` exposing only the call
    surface the reverse-sync handler touches: ``runJavaScript(js, cb)``.

    Records the most recent ``(js, cb)`` so tests can introspect what
    the handler asked the preview to evaluate.
    """

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def runJavaScript(self, js, callback=None):
        self.calls.append((js, callback))


class _FakePreview:
    def __init__(self, page, visible=True):
        self._page = page
        self._visible = visible

    def page(self):
        return self._page

    def isVisible(self):
        return self._visible


class _FakeTab(QObject):
    """Just enough of ``DocumentTab`` for the reverse-sync method to
    run. The two ``DocumentTab`` methods under test are bound as
    instance attributes so the real production logic exercises against
    these fakes without standing up QWebEngineView.
    """

    def __init__(self, editor, preview, *, sync_scrolling=True):
        super().__init__()
        self.editor = editor
        self.preview = preview
        self._sync_scrolling = sync_scrolling
        self._use_webengine = True
        self._last_editor_scroll_ms = 0
        # Bind the real methods so ``self._scroll_editor_to_line_from_preview``
        # lookups inside ``_on_preview_scroll_position_changed`` resolve.
        self._scroll_editor_to_line_from_preview = (
            DocumentTab._scroll_editor_to_line_from_preview.__get__(self)
        )


@pytest.fixture
def fake_tab(qtbot):
    """``_FakeTab`` with a visible, scrollable editor and a fake page."""
    editor = QPlainTextEdit()
    editor.setPlainText("\n".join(f"line {i}" for i in range(500)))
    editor.resize(400, 200)
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    QApplication.processEvents()
    assert editor.verticalScrollBar().maximum() > 0, (
        "test precondition: editor must be scrollable"
    )
    page = _FakePage()
    preview = _FakePreview(page)
    return _FakeTab(editor=editor, preview=preview)


def _now_ms_patch(monkeypatch, value):
    """Pin the handler's monotonic clock to ``value`` ms."""
    from markdown_editor.markdown6.components import document_tab as dt
    monkeypatch.setattr(dt, "_monotonic_ms", lambda: value)


# ────────────────────── debounce: skip cases ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_reverse_sync_skips_within_debounce(fake_tab, monkeypatch):
    """If the editor scrolled <DEBOUNCE ms ago, the preview's scroll
    change is the echo of our own ``scrollToSourceLine`` - the handler
    must NOT call into JS, otherwise we feedback-loop.
    """
    _now_ms_patch(monkeypatch, 1000)
    fake_tab._last_editor_scroll_ms = 900  # 100 ms ago < 250

    DocumentTab._on_preview_scroll_position_changed(fake_tab, QPointF(0, 0))

    assert fake_tab.preview.page().calls == [], (
        "handler must not query JS during the debounce window"
    )


@pytest.mark.timeout(15, method="thread")
def test_reverse_sync_skips_when_disabled(fake_tab, monkeypatch):
    """``_sync_scrolling`` off (settings) - never fire."""
    _now_ms_patch(monkeypatch, 10_000)
    fake_tab._sync_scrolling = False
    fake_tab._last_editor_scroll_ms = 0  # stale, would otherwise fire

    DocumentTab._on_preview_scroll_position_changed(fake_tab, QPointF(0, 0))

    assert fake_tab.preview.page().calls == []


# ────────────────────── debounce: fire cases ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_reverse_sync_fires_outside_debounce(fake_tab, monkeypatch):
    """If the editor hasn't scrolled in ≥DEBOUNCE ms, the handler must
    query JS for the top source line.
    """
    _now_ms_patch(monkeypatch, 10_000)
    fake_tab._last_editor_scroll_ms = 10_000 - _REVERSE_SYNC_DEBOUNCE_MS

    DocumentTab._on_preview_scroll_position_changed(fake_tab, QPointF(0, 0))

    assert len(fake_tab.preview.page().calls) == 1
    js, _cb = fake_tab.preview.page().calls[0]
    assert "sourceLineFromScroll" in js


@pytest.mark.timeout(15, method="thread")
def test_reverse_sync_fires_on_first_drag(fake_tab, monkeypatch):
    """Fresh tab, editor never scrolled (``_last_editor_scroll_ms = 0``)
    - first user drag of the preview scrollbar must reach the editor.
    """
    _now_ms_patch(monkeypatch, 5_000)
    # default _last_editor_scroll_ms is 0

    DocumentTab._on_preview_scroll_position_changed(fake_tab, QPointF(0, 0))

    assert len(fake_tab.preview.page().calls) == 1


# ────────────────────── apply line to editor ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_scroll_editor_to_line_moves_scrollbar(fake_tab):
    """The JS callback returns a line number; the editor's vertical
    scrollbar.setValue(line) places that block at the top of the
    viewport (``QPlainTextEdit``'s scrollbar is block-aligned).
    """
    DocumentTab._scroll_editor_to_line_from_preview(fake_tab, 42)
    assert fake_tab.editor.verticalScrollBar().value() == 42


@pytest.mark.timeout(15, method="thread")
def test_scroll_editor_to_line_ignores_none(fake_tab):
    """If JS returns ``None`` (no anchors yet / page mid-load), do
    nothing - don't reset the editor to 0."""
    fake_tab.editor.verticalScrollBar().setValue(50)
    DocumentTab._scroll_editor_to_line_from_preview(fake_tab, None)
    assert fake_tab.editor.verticalScrollBar().value() == 50


# ────────────────────── editor-scroll timestamp ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_on_editor_scroll_updates_timestamp(fake_tab, monkeypatch):
    """``_on_editor_scroll`` must stamp ``_last_editor_scroll_ms`` BEFORE
    or AT the moment it issues the JS scroll, so a same-tick
    ``scrollPositionChanged`` echo sees the fresh timestamp and
    debounces. We patch the clock + page so no real WebEngine is touched.
    """
    _now_ms_patch(monkeypatch, 7_777)
    # _on_editor_scroll runs the editor → preview pipeline; with
    # _use_webengine True and preview visible, it calls runJavaScript.
    # We just need it not to crash on our fake.
    fake_tab.editor.get_first_visible_line = MagicMock(return_value=12)

    DocumentTab._on_editor_scroll(fake_tab)

    assert fake_tab._last_editor_scroll_ms == 7_777


# ────────────────────── wiring: real DocumentTab ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_scrollpositionchanged_is_connected_on_real_tab(qtbot, monkeypatch):
    """Smoke test: constructing a real ``DocumentTab`` connects the
    page's ``scrollPositionChanged`` signal to the reverse-sync handler.

    We can't introspect Qt's connection table directly (no Python API),
    so we drive it end-to-end: emit the signal on the real page with a
    stale ``_last_editor_scroll_ms`` and assert the handler reached
    ``runJavaScript`` on the page.
    """
    from markdown_editor.markdown6.components import document_tab as dt
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitExposed(editor)
    editor.new_tab()
    tab = editor.current_tab()
    if not tab._use_webengine:
        pytest.skip("WebEngine not available; reverse-sync path is QWebEngine-only")

    # Make the debounce check pass (treat as no recent editor scroll).
    monkeypatch.setattr(dt, "_monotonic_ms", lambda: 10**9)
    tab._last_editor_scroll_ms = 0

    captured: list[str] = []
    real_run_js = tab._custom_page.runJavaScript

    def spy(js, *args, **kwargs):
        captured.append(js)
        return real_run_js(js, *args, **kwargs)

    monkeypatch.setattr(tab._custom_page, "runJavaScript", spy)
    tab._custom_page.scrollPositionChanged.emit(QPointF(0, 0))
    assert any("sourceLineFromScroll" in js for js in captured), (
        "emitting scrollPositionChanged must reach the reverse-sync handler "
        "which queries sourceLineFromScroll via runJavaScript"
    )

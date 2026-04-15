"""Tests for copy and select-all in the preview pane.

Bug: Ctrl+C and Ctrl+A always operated on the editor, even when the
preview pane had focus, because _copy/_select_all unconditionally
delegated to tab.editor.

Fix: Check preview_has_focus() and delegate to the preview when it owns
keyboard focus.
"""

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.app_context import get_app_context

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


class FakeMainWindow:
    """Minimal stand-in for MarkdownEditor."""

    def __init__(self):
        import markdown
        from markdown_editor.markdown6.extensions.math import MathExtension

        self.ctx = get_app_context()
        self.md = markdown.Markdown(extensions=["extra", MathExtension()])

    def update_tab_title(self, tab):
        pass

    def update_window_title(self):
        pass

    def get_html_template(self, content, **kwargs):
        return f"<html><body>{content}</body></html>"


def _make_tab(qtbot):
    from markdown_editor.markdown6.components.document_tab import DocumentTab
    fake_mw = FakeMainWindow()
    tab = DocumentTab(fake_mw)
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


class TestPreviewHasFocus:
    """Test that preview_has_focus() detects focus correctly."""

    def test_focus_on_editor_returns_false(self, qtbot):
        tab = _make_tab(qtbot)
        tab.editor.setFocus()
        QApplication.processEvents()
        assert not tab.preview_has_focus()

    @pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
    def test_focus_on_webengine_preview_returns_true(self, qtbot):
        tab = _make_tab(qtbot)
        tab.preview.setFocus()
        QApplication.processEvents()
        assert tab.preview_has_focus()

    @pytest.mark.skipif(HAS_WEBENGINE, reason="Only for QTextBrowser fallback")
    def test_focus_on_textbrowser_preview_returns_true(self, qtbot):
        tab = _make_tab(qtbot)
        tab.preview.setFocus()
        QApplication.processEvents()
        assert tab.preview_has_focus()


class TestPreviewCopy:
    """Test that copy works from the preview pane."""

    @pytest.mark.skipif(HAS_WEBENGINE, reason="Only for QTextBrowser fallback")
    def test_copy_from_textbrowser_preview(self, qtbot):
        """When QTextBrowser preview has focus, copy should copy from it."""
        tab = _make_tab(qtbot)

        tab.preview.setHtml("<html><body><p>Hello preview world</p></body></html>")
        QApplication.processEvents()

        tab.preview.setFocus()
        QApplication.processEvents()
        tab.preview.selectAll()
        QApplication.processEvents()

        QApplication.clipboard().clear()
        tab.preview_copy()
        QApplication.processEvents()

        clipboard_text = QApplication.clipboard().text()
        assert "Hello preview world" in clipboard_text

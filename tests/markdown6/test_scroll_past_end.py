"""Tests for scroll-past-end feature."""

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.app_context import get_app_context


class TestScrollPastEndSetting:
    """Test the scroll_past_end setting default and persistence."""

    def test_default_on(self):
        assert get_app_context().get("editor.scroll_past_end") is True

    def test_toggle_off(self):
        ctx = get_app_context()
        ctx.set("editor.scroll_past_end", False)
        assert ctx.get("editor.scroll_past_end") is False


class TestScrollPastEndEditor:
    """Test that the editor allows scrolling past the end of the document."""

    @pytest.fixture
    def editor(self, qtbot):
        from markdown_editor.markdown6.enhanced_editor import EnhancedEditor

        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.resize(600, 400)
        ed.show()
        qtbot.waitExposed(ed)
        ed.setPlainText("\n".join(f"Line {i}" for i in range(100)))
        QApplication.processEvents()
        return ed

    def test_center_on_scroll_enabled(self, editor):
        """centerOnScroll should be True when scroll-past-end is on."""
        assert editor.centerOnScroll() is True

    def test_scrollbar_extended_beyond_normal_range(self, editor):
        """Scrollbar max should exceed what's needed to show the last line
        at the bottom of the viewport."""
        vbar = editor.verticalScrollBar()
        doc_lines = editor.document().blockCount()
        visible_lines = max(1, editor.viewport().height() // editor.fontMetrics().lineSpacing())
        normal_max = doc_lines - visible_lines
        assert vbar.maximum() > normal_max, (
            f"scrollbar max {vbar.maximum()} should exceed normal max {normal_max}"
        )

    def test_can_scroll_to_max_without_crash(self, editor):
        """Scrolling to the maximum value should not crash."""
        vbar = editor.verticalScrollBar()
        vbar.setValue(vbar.maximum())
        QApplication.processEvents()

    def test_ensure_cursor_visible_does_not_scroll_when_visible(self, editor):
        """ensureCursorVisible should not move the view when the cursor
        is already on screen (i.e. no centering side-effect)."""
        # Scroll to a middle position
        vbar = editor.verticalScrollBar()
        vbar.setValue(20)
        QApplication.processEvents()

        # Place cursor at a visible line
        cursor = editor.textCursor()
        block = editor.document().findBlockByNumber(25)
        cursor.setPosition(block.position())
        editor.setTextCursor(cursor)
        QApplication.processEvents()

        scroll_before = vbar.value()
        editor.ensureCursorVisible()
        QApplication.processEvents()

        assert vbar.value() == scroll_before, (
            "ensureCursorVisible should not scroll when cursor is already visible"
        )

    def test_disabled_uses_normal_scroll(self, editor):
        """With scroll-past-end off, centerOnScroll should be False."""
        get_app_context().set("editor.scroll_past_end", False)
        assert editor.centerOnScroll() is False

    def test_toggle_on_off(self, editor):
        """Toggling the setting should change centerOnScroll."""
        assert editor.centerOnScroll() is True
        get_app_context().set("editor.scroll_past_end", False)
        assert editor.centerOnScroll() is False
        get_app_context().set("editor.scroll_past_end", True)
        assert editor.centerOnScroll() is True

    def test_short_document_no_crash(self, qtbot):
        """A document shorter than the viewport should not crash."""
        from markdown_editor.markdown6.enhanced_editor import EnhancedEditor

        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.resize(600, 400)
        ed.show()
        qtbot.waitExposed(ed)
        ed.setPlainText("Just one line")
        QApplication.processEvents()
        assert ed.verticalScrollBar().maximum() >= 0


class _TemplateHelper:
    """Minimal stand-in for MarkdownEditor — just enough for get_html_template."""

    def __init__(self):
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor
        self.ctx = get_app_context()
        self.get_html_template = MarkdownEditor.get_html_template.__get__(self)


class TestScrollPastEndPreview:
    """Test that the preview HTML includes scroll-past-end padding."""

    @pytest.fixture
    def tmpl(self):
        return _TemplateHelper()

    def test_webengine_html_has_spacer(self, tmpl):
        html = tmpl.get_html_template("<p>test</p>")
        assert "height: 80vh" in html

    def test_webengine_html_no_spacer_when_disabled(self, tmpl):
        get_app_context().set("editor.scroll_past_end", False)
        html = tmpl.get_html_template("<p>test</p>")
        assert "height: 80vh" not in html

    def test_qtextbrowser_html_has_spacer(self, tmpl):
        html = tmpl.get_html_template("<p>test</p>", for_qtextbrowser=True)
        assert "height: 80vh" in html

    def test_qtextbrowser_html_no_spacer_when_disabled(self, tmpl):
        get_app_context().set("editor.scroll_past_end", False)
        html = tmpl.get_html_template("<p>test</p>", for_qtextbrowser=True)
        assert "height: 80vh" not in html


class TestScrollPastEndSync:
    """Test that both editor and preview have padding in lockstep."""

    @pytest.fixture
    def editor(self, qtbot):
        from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        return ed

    @pytest.fixture
    def tmpl(self):
        return _TemplateHelper()

    def test_both_sides_enabled_by_default(self, editor, tmpl):
        """Editor extended scroll AND preview spacer present by default."""
        assert editor.centerOnScroll() is True
        html = tmpl.get_html_template("<p>x</p>")
        assert "height: 80vh" in html

    def test_both_sides_disabled_together(self, editor, tmpl):
        """Disabling removes scroll-past-end from both sides."""
        get_app_context().set("editor.scroll_past_end", False)
        assert editor.centerOnScroll() is False
        html = tmpl.get_html_template("<p>x</p>")
        assert "height: 80vh" not in html

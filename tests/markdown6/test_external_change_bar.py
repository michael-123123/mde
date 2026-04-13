"""Tests for the ExternalChangeBar non-modal notification widget."""

import pytest

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.markdown_editor import ExternalChangeBar


@pytest.fixture
def bar(qtbot):
    b = ExternalChangeBar(get_app_context())
    qtbot.addWidget(b)
    return b


class TestExternalChangeBar:

    def test_hidden_by_default(self, bar):
        assert not bar.isVisible()

    def test_show_change_makes_visible(self, bar):
        bar.show_change("test.md")
        assert bar.isVisible()

    def test_show_change_sets_message(self, bar):
        bar.show_change("notes.md")
        assert "notes.md" in bar.message_label.text()
        assert "modified externally" in bar.message_label.text()

    def test_dismiss_hides(self, bar):
        bar.show_change("test.md")
        bar.dismiss_btn.click()
        assert not bar.isVisible()

    def test_reload_hides(self, bar):
        bar.show_change("test.md")
        bar.reload_btn.click()
        assert not bar.isVisible()

    def test_reload_emits_signal(self, bar, qtbot):
        bar.show_change("test.md")
        with qtbot.waitSignal(bar.reload_requested, timeout=500):
            bar.reload_btn.click()

    def test_dismiss_emits_signal(self, bar, qtbot):
        bar.show_change("test.md")
        with qtbot.waitSignal(bar.dismissed, timeout=500):
            bar.dismiss_btn.click()

    def test_coalesces_multiple_changes(self, bar):
        """Calling show_change multiple times doesn't stack or duplicate."""
        bar.show_change("test.md")
        bar.show_change("test.md")
        bar.show_change("test.md")
        assert bar.isVisible()
        # Only one bar, message reflects the file
        assert "test.md" in bar.message_label.text()

    def test_show_change_after_dismiss(self, bar):
        """Bar can be re-shown after being dismissed."""
        bar.show_change("test.md")
        bar.dismiss_btn.click()
        assert not bar.isVisible()
        bar.show_change("test.md")
        assert bar.isVisible()

    def test_theme_applies_stylesheet(self, bar):
        """Theme application sets a non-empty stylesheet."""
        bar._apply_theme()
        assert bar.styleSheet() != ""

    def test_size_policy_is_maximum(self, bar):
        from PySide6.QtWidgets import QSizePolicy
        assert bar.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum

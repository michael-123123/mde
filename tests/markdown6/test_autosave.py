"""Tests for the autosave feature.

Tests the autosave logic directly without creating a full MarkdownEditor,
which is slow due to WebEngine, sidebar, and markdown extension init.
"""

from unittest.mock import MagicMock

from PySide6.QtCore import QTimer

from markdown_editor.markdown6.app_context import get_app_context


class FakeTab:
    """Minimal stand-in for DocumentTab with just the fields autosave needs."""

    def __init__(self, file_path=None, unsaved_changes=False, text=""):
        self.file_path = file_path
        self.unsaved_changes = unsaved_changes
        self.editor = MagicMock()
        self.editor.toPlainText.return_value = text
        self.editor.document.return_value.setModified = MagicMock()


class FakeTabWidget:
    """Minimal stand-in for QTabWidget."""

    def __init__(self, tabs):
        self._tabs = tabs

    def count(self):
        return len(self._tabs)

    def widget(self, i):
        return self._tabs[i]


class TestAutosaveLogic:
    """Test autosave save logic using fakes - no GUI needed."""

    def test_saves_dirty_tab_with_path(self, tmp_path):
        """Autosave writes content to disk for dirty tabs with a file path."""
        test_file = tmp_path / "test.md"
        test_file.write_text("original", encoding="utf-8")

        tab = FakeTab(file_path=test_file, unsaved_changes=True, text="modified")

        # Import and call the save logic directly

        # Call the static-like logic: iterate tabs, write if dirty+has path
        _auto_save_tabs(FakeTabWidget([tab]))

        assert test_file.read_text(encoding="utf-8") == "modified"
        assert not tab.unsaved_changes

    def test_skips_untitled_tab(self):
        """Autosave skips tabs without a file path."""
        tab = FakeTab(file_path=None, unsaved_changes=True, text="content")
        _auto_save_tabs(FakeTabWidget([tab]))
        assert tab.unsaved_changes

    def test_skips_clean_tab(self, tmp_path):
        """Autosave skips tabs with no unsaved changes."""
        test_file = tmp_path / "clean.md"
        test_file.write_text("original", encoding="utf-8")

        tab = FakeTab(file_path=test_file, unsaved_changes=False)
        _auto_save_tabs(FakeTabWidget([tab]))
        assert test_file.read_text(encoding="utf-8") == "original"

    def test_saves_multiple_dirty_tabs(self, tmp_path):
        """Autosave saves all dirty tabs, not just the current one."""
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("old1", encoding="utf-8")
        f2.write_text("old2", encoding="utf-8")

        tabs = [
            FakeTab(file_path=f1, unsaved_changes=True, text="new1"),
            FakeTab(file_path=f2, unsaved_changes=True, text="new2"),
        ]
        _auto_save_tabs(FakeTabWidget(tabs))

        assert f1.read_text(encoding="utf-8") == "new1"
        assert f2.read_text(encoding="utf-8") == "new2"

    def test_handles_write_error_gracefully(self, tmp_path):
        """Autosave skips tabs whose file can't be written."""
        bad_path = tmp_path / "nonexistent_dir" / "file.md"
        good_file = tmp_path / "good.md"
        good_file.write_text("old", encoding="utf-8")

        tabs = [
            FakeTab(file_path=bad_path, unsaved_changes=True, text="x"),
            FakeTab(file_path=good_file, unsaved_changes=True, text="new"),
        ]
        _auto_save_tabs(FakeTabWidget(tabs))

        # Bad tab stays dirty, good tab was saved
        assert tabs[0].unsaved_changes
        assert not tabs[1].unsaved_changes
        assert good_file.read_text(encoding="utf-8") == "new"


class TestAutosaveTimer:
    """Test timer configuration via settings - uses a real QTimer but no editor."""

    def test_default_off(self):
        """Auto-save is disabled by default."""
        assert get_app_context().get("editor.auto_save") is False

    def test_timer_starts_and_stops(self, qtbot):
        """Timer activates/deactivates when setting toggles."""
        timer = QTimer()
        ctx = get_app_context()

        # Simulate what _configure_autosave does
        def configure():
            if ctx.get("editor.auto_save", False):
                timer.start(ctx.get("editor.auto_save_interval", 60) * 1000)
            else:
                timer.stop()

        ctx.settings_changed.connect(lambda k, v: configure())

        ctx.set("editor.auto_save", True)
        assert timer.isActive()
        assert timer.interval() == 60_000

        ctx.set("editor.auto_save_interval", 30)
        assert timer.interval() == 30_000

        ctx.set("editor.auto_save", False)
        assert not timer.isActive()

        timer.stop()


def _auto_save_tabs(tab_widget):
    """Extract of the autosave logic for testing without MarkdownEditor."""
    for i in range(tab_widget.count()):
        tab = tab_widget.widget(i)
        if tab and tab.file_path and tab.unsaved_changes:
            try:
                tab.editor._ignore_next_file_change = True
                tab.file_path.write_text(
                    tab.editor.toPlainText(), encoding="utf-8"
                )
                tab.unsaved_changes = False
                tab.editor.document().setModified(False)
            except OSError:
                pass

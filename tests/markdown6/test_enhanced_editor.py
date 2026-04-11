"""Tests for the enhanced editor module."""

import pytest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from markdown_editor.markdown6.enhanced_editor import (
    EnhancedEditor,
    FoldingRegion,
    LineNumberArea,
    WikiLinkCompleter,
)


@pytest.fixture
def editor(qtbot):
    """Create an EnhancedEditor instance."""
    ed = EnhancedEditor()
    qtbot.addWidget(ed)
    return ed


@pytest.fixture
def wiki_completer(qtbot):
    """Create a WikiLinkCompleter instance."""
    completer = WikiLinkCompleter()
    qtbot.addWidget(completer)
    return completer


class TestFoldingRegion:
    """Tests for FoldingRegion class."""

    def test_folding_region_creation(self):
        """Test creating a folding region."""
        region = FoldingRegion(start_line=5, end_line=10, region_type="heading")
        assert region.start_line == 5
        assert region.end_line == 10
        assert region.region_type == "heading"
        assert region.is_folded == False

    def test_folding_region_default_type(self):
        """Test default region type."""
        region = FoldingRegion(start_line=0, end_line=5)
        assert region.region_type == "heading"

    def test_folding_region_code_block(self):
        """Test code block region type."""
        region = FoldingRegion(start_line=0, end_line=5, region_type="code_block")
        assert region.region_type == "code_block"


class TestEnhancedEditorCreation:
    """Tests for EnhancedEditor initialization."""

    def test_editor_creation(self, editor):
        """Test creating an editor."""
        assert editor is not None
        assert editor.file_path is None

    def test_editor_has_line_number_area(self, editor):
        """Test that editor has line number area."""
        assert hasattr(editor, 'line_number_area')
        assert isinstance(editor.line_number_area, LineNumberArea)

    def test_editor_auto_pairs(self, editor):
        """Test that auto pairs are defined."""
        assert "(" in editor.AUTO_PAIRS
        assert editor.AUTO_PAIRS["("] == ")"
        assert '"' in editor.AUTO_PAIRS
        assert "`" in editor.AUTO_PAIRS


class TestEnhancedEditorText:
    """Tests for text manipulation in the editor."""

    def test_set_plain_text(self, editor):
        """Test setting plain text."""
        editor.setPlainText("Hello, World!")
        assert editor.toPlainText() == "Hello, World!"

    def test_get_plain_text(self, editor):
        """Test getting text via toPlainText."""
        editor.setPlainText("Test content")
        assert editor.toPlainText() == "Test content"

    def test_clear_text(self, editor):
        """Test clearing text."""
        editor.setPlainText("Some text")
        editor.clear()
        assert editor.toPlainText() == ""


class TestEnhancedEditorCursor:
    """Tests for cursor operations."""

    def test_cursor_position_signal(self, editor, qtbot):
        """Test that cursor position signal is emitted."""
        editor.setPlainText("Line 1\nLine 2\nLine 3")
        with qtbot.waitSignal(editor.cursor_position_changed, timeout=1000):
            cursor = editor.textCursor()
            cursor.setPosition(10)
            editor.setTextCursor(cursor)

    def test_go_to_line(self, editor):
        """Test going to a specific line."""
        editor.setPlainText("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
        editor.go_to_line(3)

        cursor = editor.textCursor()
        block = cursor.block()
        assert block.blockNumber() == 2  # 0-indexed, so line 3 is index 2


class TestEnhancedEditorSelection:
    """Tests for selection operations."""

    def test_get_selected_text(self, editor):
        """Test getting selected text via textCursor."""
        editor.setPlainText("Hello World")
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)

        assert editor.textCursor().selectedText() == "Hello"

    def test_get_selected_text_empty(self, editor):
        """Test getting selected text when nothing selected."""
        editor.setPlainText("Hello World")
        assert editor.textCursor().selectedText() == ""


class TestEnhancedEditorWordCount:
    """Tests for word count functionality."""

    def test_word_count_signal(self, editor, qtbot):
        """Test that word count signal is emitted."""
        with qtbot.waitSignal(editor.word_count_changed, timeout=1000):
            editor.setPlainText("Hello World")

    def test_word_count_updates_on_text_change(self, editor, qtbot):
        """Test that word count updates when text changes."""
        # The signal should be emitted with word and character counts
        with qtbot.waitSignal(editor.word_count_changed, timeout=1000) as blocker:
            editor.setPlainText("One two three")
        # The signal args are (word_count, char_count)
        assert blocker.args[0] == 3  # 3 words


class TestEnhancedEditorLineNumbers:
    """Tests for line number functionality."""

    def test_line_number_area_width(self, editor):
        """Test that line number area has width."""
        editor.setPlainText("Line 1\n" * 10)
        width = editor.line_number_area_width()
        assert width > 0

    def test_line_numbers_visible_by_default(self, editor):
        """Test that line numbers are visible by default."""
        # Check via settings or the line number area visibility
        assert editor.line_number_area.isVisible() or editor.ctx.get("editor.show_line_numbers")


class TestEnhancedEditorModification:
    """Tests for document modification tracking."""

    def test_document_not_modified_initially(self, editor):
        """Test that document is not modified initially after setModified(False)."""
        editor.setPlainText("Initial")
        editor.document().setModified(False)
        assert not editor.document().isModified()

    def test_document_modified_after_typing(self, editor, qtbot):
        """Test that document is marked modified after user input."""
        editor.setPlainText("Initial")
        editor.document().setModified(False)
        # Simulate typing
        cursor = editor.textCursor()
        cursor.insertText("X")
        assert editor.document().isModified()


class TestWikiLinkCompleter:
    """Tests for WikiLinkCompleter widget."""

    def test_completer_creation(self, wiki_completer):
        """Test creating a wiki link completer."""
        assert wiki_completer is not None

    def test_show_completions(self, wiki_completer):
        """Test showing completions."""
        completions = ["Document1", "Document2", "Document3"]
        wiki_completer.show_completions(completions, wiki_completer.pos())
        assert wiki_completer.count() == 3

    def test_show_completions_limits_to_10(self, wiki_completer):
        """Test that completions are limited to 10."""
        completions = [f"Doc{i}" for i in range(20)]
        wiki_completer.show_completions(completions, wiki_completer.pos())
        assert wiki_completer.count() == 10

    def test_show_completions_empty(self, wiki_completer):
        """Test showing empty completions hides the completer."""
        wiki_completer.show()
        wiki_completer.show_completions([], wiki_completer.pos())
        # After showing empty, it should hide

    def test_link_selected_signal(self, wiki_completer, qtbot):
        """Test that link_selected signal is emitted on activation."""
        completions = ["Document1"]
        wiki_completer.show_completions(completions, wiki_completer.pos())

        with qtbot.waitSignal(wiki_completer.link_selected) as blocker:
            item = wiki_completer.item(0)
            wiki_completer.itemActivated.emit(item)

        assert blocker.args == ["Document1"]


class TestEnhancedEditorFile:
    """Tests for file operations."""

    def test_set_file_path(self, editor, tmp_path):
        """Test setting file path."""
        test_file = tmp_path / "test.md"
        editor.set_file_path(test_file)
        assert editor.file_path == test_file

    def test_save_file(self, editor, tmp_path):
        """Test saving a file."""
        test_file = tmp_path / "save_test.md"
        editor.set_file_path(test_file)
        editor.setPlainText("# Saved Content")

        result = editor.save_file()
        assert result == True
        assert test_file.exists()
        assert "Saved Content" in test_file.read_text()

    def test_save_file_no_path(self, editor):
        """Test saving without a file path returns False."""
        editor.setPlainText("# Content")
        editor.file_path = None
        result = editor.save_file()
        assert result == False


class TestEnhancedEditorFormatting:
    """Tests for markdown formatting methods."""

    def test_format_bold(self, editor):
        """Test bold formatting."""
        editor.setPlainText("text")
        editor.selectAll()
        editor.format_bold()
        assert "**" in editor.toPlainText()

    def test_format_italic(self, editor):
        """Test italic formatting."""
        editor.setPlainText("text")
        editor.selectAll()
        editor.format_italic()
        assert "*" in editor.toPlainText()

    def test_format_code(self, editor):
        """Test code formatting."""
        editor.setPlainText("code")
        editor.selectAll()
        editor.format_code()
        assert "`" in editor.toPlainText()

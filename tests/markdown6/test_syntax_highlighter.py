"""Tests for the syntax highlighter module."""

import pytest
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.syntax_highlighter import MarkdownHighlighter


@pytest.fixture
def document(qtbot):
    """Create a QTextDocument for testing."""
    doc = QTextDocument()
    return doc


@pytest.fixture
def highlighter(document):
    """Create a MarkdownHighlighter instance."""
    return MarkdownHighlighter(document, dark_mode=False)


@pytest.fixture
def dark_highlighter(document):
    """Create a dark mode MarkdownHighlighter instance."""
    return MarkdownHighlighter(document, dark_mode=True)


class TestHighlighterCreation:
    """Tests for highlighter creation."""

    def test_highlighter_creation_light(self, highlighter):
        """Test creating a light mode highlighter."""
        assert highlighter is not None
        assert highlighter.dark_mode is False

    def test_highlighter_creation_dark(self, dark_highlighter):
        """Test creating a dark mode highlighter."""
        assert dark_highlighter is not None
        assert dark_highlighter.dark_mode is True

    def test_highlighter_has_formats(self, highlighter):
        """Test that highlighter has formats defined."""
        assert hasattr(highlighter, 'formats')
        assert "heading" in highlighter.formats
        assert "bold" in highlighter.formats
        assert "italic" in highlighter.formats
        assert "code" in highlighter.formats
        assert "link" in highlighter.formats


class TestHighlighterFormats:
    """Tests for text format definitions."""

    def test_heading_format_is_bold(self, highlighter):
        """Test that heading format is bold."""
        fmt = highlighter.formats["heading"]
        assert fmt.fontWeight() == QFont.Weight.Bold

    def test_bold_format_is_bold(self, highlighter):
        """Test that bold format is bold."""
        fmt = highlighter.formats["bold"]
        assert fmt.fontWeight() == QFont.Weight.Bold

    def test_italic_format_is_italic(self, highlighter):
        """Test that italic format is italic."""
        fmt = highlighter.formats["italic"]
        assert fmt.fontItalic() is True

    def test_code_format_is_monospace(self, highlighter):
        """Test that code format uses monospace font."""
        fmt = highlighter.formats["code"]
        # Font family should be set to monospace
        families = fmt.fontFamilies()
        assert any("mono" in f.lower() for f in families)


class TestDarkModeToggle:
    """Tests for dark mode toggling."""

    def test_set_dark_mode_true(self, highlighter):
        """Test switching to dark mode."""
        highlighter.set_dark_mode(True)
        assert highlighter.dark_mode is True

    def test_set_dark_mode_false(self, dark_highlighter):
        """Test switching to light mode."""
        dark_highlighter.set_dark_mode(False)
        assert dark_highlighter.dark_mode is False

    def test_dark_mode_changes_colors(self, highlighter):
        """Test that dark mode changes colors."""
        light_heading_color = highlighter.formats["heading"].foreground().color().name()
        highlighter.set_dark_mode(True)
        dark_heading_color = highlighter.formats["heading"].foreground().color().name()
        assert light_heading_color != dark_heading_color


class TestHighlightingRules:
    """Tests for highlighting rules."""

    def test_has_rules(self, highlighter):
        """Test that highlighter has rules defined."""
        assert hasattr(highlighter, 'rules')
        assert len(highlighter.rules) > 0

    def test_rules_are_tuples(self, highlighter):
        """Test that rules are properly formatted."""
        for rule in highlighter.rules:
            # Each rule should be a tuple of (pattern, format)
            assert len(rule) >= 2


class TestHighlighterWithEditor:
    """Tests for highlighter with a text editor."""

    def test_highlighter_attached_to_document(self, qtbot):
        """Test that highlighter is properly attached to document."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        highlighter = MarkdownHighlighter(editor.document())
        assert highlighter.document() == editor.document()

    def test_highlighting_headings(self, qtbot):
        """Test highlighting of headings."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("# Heading 1\n## Heading 2")
        # If no exception, highlighting worked

    def test_highlighting_bold(self, qtbot):
        """Test highlighting of bold text."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("This is **bold** text")
        # If no exception, highlighting worked

    def test_highlighting_italic(self, qtbot):
        """Test highlighting of italic text."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("This is *italic* text")
        # If no exception, highlighting worked

    def test_highlighting_code(self, qtbot):
        """Test highlighting of inline code."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("This is `code` text")
        # If no exception, highlighting worked

    def test_highlighting_code_block(self, qtbot):
        """Test highlighting of code blocks."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("```python\nprint('hello')\n```")
        # If no exception, highlighting worked

    def test_highlighting_links(self, qtbot):
        """Test highlighting of links."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("[link text](http://example.com)")
        # If no exception, highlighting worked

    def test_highlighting_wiki_links(self, qtbot):
        """Test highlighting of wiki links."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("See [[Other Document]] for more")
        # If no exception, highlighting worked

    def test_highlighting_lists(self, qtbot):
        """Test highlighting of lists."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("- Item 1\n- Item 2\n1. Numbered")
        # If no exception, highlighting worked

    def test_highlighting_blockquote(self, qtbot):
        """Test highlighting of blockquotes."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("> This is a quote")
        # If no exception, highlighting worked

    def test_highlighting_horizontal_rule(self, qtbot):
        """Test highlighting of horizontal rules."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        editor.setPlainText("---\n***\n___")
        # If no exception, highlighting worked


class TestHighlighterPerformance:
    """Tests for highlighter performance."""

    def test_large_document(self, qtbot):
        """Test highlighting a large document doesn't hang."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        MarkdownHighlighter(editor.document())

        # Create a moderately large document
        large_text = "# Heading\n\n" + "This is **bold** and *italic* text. " * 100 + "\n" * 50
        editor.setPlainText(large_text)
        # If no exception or hang, test passes

    def test_rehighlight(self, qtbot):
        """Test that rehighlight works."""
        editor = QPlainTextEdit()
        qtbot.addWidget(editor)
        highlighter = MarkdownHighlighter(editor.document())

        editor.setPlainText("# Test")
        highlighter.rehighlight()
        # If no exception, rehighlight worked

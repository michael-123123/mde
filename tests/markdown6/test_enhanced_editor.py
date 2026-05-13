"""Tests for the enhanced editor module."""


import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor

from markdown_editor.markdown6.enhanced_editor import (
    EnhancedEditor,
    FoldingRegion,
    LineNumberArea,
    WikiLinkCompleter,
)


def _press(editor: EnhancedEditor, char: str, key: Qt.Key = Qt.Key.Key_unknown):
    """Send a QKeyEvent to the editor exactly the way Qt would."""
    ev = QKeyEvent(
        QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, char,
    )
    editor.keyPressEvent(ev)


def _type(editor: EnhancedEditor, text: str):
    """Type a sequence of characters one keystroke at a time."""
    for ch in text:
        _press(editor, ch)


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
        assert region.is_folded is False

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
        assert result is True
        assert test_file.exists()
        assert "Saved Content" in test_file.read_text()

    def test_save_file_no_path(self, editor):
        """Test saving without a file path returns False."""
        editor.setPlainText("# Content")
        editor.file_path = None
        result = editor.save_file()
        assert result is False


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


class TestFencedCodeAutoComplete:
    """Behavior around typing ``` (fenced code block opener).

    Empirically verified (see local/tmp/repro_backticks.py):
      - 1st backtick: auto-pair inserts ``, cursor between -> `|`
      - 2nd backtick: skip-close jumps over the existing close, cursor at end -> ``|
      - 3rd backtick: cursor is at end-of-buffer, skip-close fails -> auto-pair
        adds another `` pair -> ```|`  (BUG: stray trailing backtick)
      - Enter at this point: just a normal newline; trailing ` ends up alone
        on the next line.

    Fixes:
      - Suppress auto-pair on the 3rd backtick when the cursor is at end of
        line and the line ends with ``.
      - On Enter, if the current line matches ^```\\w*$, scaffold a fenced
        block: insert \\n``` after the cursor so the user lands on an empty
        middle line with a closing fence below.
    """

    # ── Sub-fix 1: third backtick doesn't add an unwanted closing ──

    def test_two_backticks_state(self, editor):
        """Sanity: after 2 backticks, buffer is `` with cursor at end."""
        _type(editor, "``")
        assert editor.toPlainText() == "``"
        assert editor.textCursor().position() == 2

    def test_three_backticks_no_trailing_close(self, editor):
        """After typing ```, buffer should be ``` with cursor at end -
        NOT ```` with cursor in the middle.
        """
        _type(editor, "```")
        assert editor.toPlainText() == "```"
        assert editor.textCursor().position() == 3

    # ── Sub-fix 2: Enter scaffolds a fenced block ──

    def test_enter_after_triple_backtick_scaffolds_fence(self, editor):
        """Enter on a line that is exactly ``` should scaffold the fence."""
        _type(editor, "```")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # Expected: opening ```, newline, empty cursor line, newline, closing ```.
        assert editor.toPlainText() == "```\n\n```"
        # Cursor lands on the empty middle line.
        cursor = editor.textCursor()
        line_text = cursor.block().text()
        assert line_text == ""

    def test_enter_after_triple_backtick_with_language_scaffolds_fence(self, editor):
        """Same as above but with a language tag after the opener."""
        _type(editor, "```python")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        assert editor.toPlainText() == "```python\n\n```"
        line_text = editor.textCursor().block().text()
        assert line_text == ""

    def test_enter_outside_fence_opener_does_not_scaffold(self, editor):
        """Enter on a regular line should NOT scaffold a fence."""
        editor.setPlainText("just some text")
        # Move cursor to end of the line.
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # Plain newline, no closing fence inserted.
        assert "```" not in editor.toPlainText()

    def test_enter_on_closing_fence_does_not_scaffold(self, editor):
        """Regression: a line that is bare ``` could be an opener OR a closer.
        After typing ``` and pressing Enter, the scaffold creates:

            ```
            |
            ```

        If the user then moves the cursor to the closing ``` line and hits
        Enter, my fix used to scaffold ANOTHER fence below it, producing:

            ```
            (empty)
            ```
            (empty)
            ```

        Track fence-marker parity: walk up from the current line, count
        ``` lines. Even count -> current line is an opener (scaffold).
        Odd count -> current line is a closer (don't scaffold).
        """
        editor.setPlainText("```\n\n```")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # No third fence: count of ``` substrings stays at 2.
        assert editor.toPlainText().count("```") == 2

    def test_enter_after_backticks_with_space_does_not_scaffold(self, editor):
        """``` followed by SPACE and more text isn't a valid fence opener.

        A valid fence opener is ``` or ```LANG (no space between the
        backticks and the language tag, no other content). Anything else
        should NOT scaffold.
        """
        editor.setPlainText("``` some prose with backticks")
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # No closing fence scaffolded - that ``` was inline, not an opener.
        assert "```" in editor.toPlainText()
        assert editor.toPlainText().count("```") == 1


def _set_buffer_and_place_cursor(editor: EnhancedEditor, text: str, marker: str = "|"):
    """Set the editor buffer to *text* with the cursor at the offset of
    *marker*. The marker itself is stripped from the buffer.

    Lets each test specify a fixture string like ``\"```\\n|\\n```\"``
    and have the cursor placed precisely.
    """
    pos = text.index(marker)
    cleaned = text[:pos] + text[pos + len(marker):]
    editor.setPlainText(cleaned)
    cursor = editor.textCursor()
    cursor.setPosition(pos)
    editor.setTextCursor(cursor)


class TestVerbatimRegionDetector:
    """``EnhancedEditor._cursor_in_verbatim_region()`` recognises every
    V1–V10 verbatim region (inline code, fenced code block, indented
    code block, inline math, display math, HTML pre/script/style, HTML
    comment), plus an unclosed fence via the parity hybrid.
    """

    def test_outside_returns_false_empty_buffer(self, editor):
        assert editor._cursor_in_verbatim_region() is False

    def test_outside_returns_false_paragraph(self, editor):
        _set_buffer_and_place_cursor(editor, "Hello | world")
        assert editor._cursor_in_verbatim_region() is False

    def test_inside_inline_code_span(self, editor):
        _set_buffer_and_place_cursor(editor, "text `co|de` here")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_fenced_block(self, editor):
        _set_buffer_and_place_cursor(editor, "```\n|\n```")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_tilde_fence(self, editor):
        _set_buffer_and_place_cursor(editor, "~~~\n|\n~~~")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_unclosed_fence_hybrid(self, editor):
        # No closing fence yet - the masker won't see this as verbatim, but
        # the parity hybrid should still flag it.
        _set_buffer_and_place_cursor(editor, "```python\n|")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_indented_code_block(self, editor):
        _set_buffer_and_place_cursor(editor, "para\n\n    cod|e here")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_inline_math(self, editor):
        _set_buffer_and_place_cursor(editor, "before $x| + 1$ after")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_display_math(self, editor):
        _set_buffer_and_place_cursor(editor, "$$\n|\n$$")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_html_pre(self, editor):
        _set_buffer_and_place_cursor(editor, "<pre>|</pre>")
        assert editor._cursor_in_verbatim_region() is True

    def test_inside_html_comment(self, editor):
        _set_buffer_and_place_cursor(editor, "<!--|-->")
        assert editor._cursor_in_verbatim_region() is True


class TestAutoPairsSuppressedInVerbatim:
    """Behaviors #1-#5 from the autocomplete inventory: every entry in
    AUTO_PAIRS should be suppressed when the cursor is inside a verbatim
    region. Parameterised across a fenced block, inline code span, and
    unclosed fence (the three most common contexts).
    """

    # All entries in EnhancedEditor.AUTO_PAIRS.
    AUTO_PAIR_CHARS = ['(', '[', '{', '"', "'", '`', '*', '_']

    FIXTURES = [
        ("```\n|\n```", "fenced backtick"),
        ("~~~\n|\n~~~", "fenced tilde"),
        ("```python\n|", "unclosed fence"),
        ("text `co|de` more", "inline code span"),
        ("intro $a|+b$ done", "inline math"),
    ]

    def test_fence_scaffold_not_inside_existing_fence(self, editor):
        """Regression: a line that happens to look like a fence opener but
        lives INSIDE an existing fence (e.g. the user typed ``` as content
        on a body line) must not scaffold a new fence."""
        # Outer fence with a stray ``` typed on the body line.
        editor.setPlainText("```\n```\n\n```")
        # Place cursor at the end of line 2 (the inner ``` body line).
        cursor = editor.textCursor()
        cursor.setPosition(7)   # end of line 2 (3 chars + \n + 3 chars)
        editor.setTextCursor(cursor)
        # Sanity check: detector agrees we're inside a verbatim region.
        assert editor._cursor_in_verbatim_region() is True
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # No scaffold fired: count of ``` substrings still 3 (the original).
        assert editor.toPlainText().count("```") == 3

    def test_fence_scaffold_not_inside_existing_tilde_fence(self, editor):
        """Regression: typing ``` inside an existing ~~~ fence must not
        scaffold. The earlier local parity check only counted ``` markers
        and would miss this; the verbatim-region detector counts both
        delimiter kinds, so it catches it.
        """
        editor.setPlainText("~~~\n```\n\n~~~")
        cursor = editor.textCursor()
        cursor.setPosition(7)   # end of the inner ``` line
        editor.setTextCursor(cursor)
        assert editor._cursor_in_verbatim_region() is True
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # No ``` scaffold added.
        assert editor.toPlainText().count("```") == 1

    @pytest.mark.parametrize("ch", AUTO_PAIR_CHARS)
    @pytest.mark.parametrize("fixture,label", FIXTURES)
    def test_auto_pair_suppressed(self, editor, ch, fixture, label):
        """Type ``ch`` inside a verbatim region. Only the single char
        should land in the buffer - no paired close, no skip-over jump,
        no wiki completer popup."""
        _set_buffer_and_place_cursor(editor, fixture)
        before = editor.toPlainText()
        before_pos = editor.textCursor().position()
        _press(editor, ch)
        after = editor.toPlainText()
        # Exactly one new char appears, at the cursor position.
        assert after == before[:before_pos] + ch + before[before_pos:], (
            f"{label}: expected only {ch!r} inserted; got buffer change "
            f"{before!r} -> {after!r}"
        )
        # Cursor moved by exactly 1.
        assert editor.textCursor().position() == before_pos + 1


class TestEnterIndentListSuppressedInVerbatim:
    """Behaviours #7-#9. List continuation and empty-list-marker strip
    are ALWAYS suppressed inside verbatim. Auto-indent (which preserves
    leading whitespace) is KEPT by default - typing indented code inside
    a fence should keep its indent on Enter. A setting
    (``editor.auto_indent_in_verbatim``) can disable that too.
    """

    def test_list_continuation_suppressed_in_fence(self, editor):
        """``- item`` inside a fenced block should NOT auto-add ``- ``
        on the new line - it's code, not a list."""
        _set_buffer_and_place_cursor(editor, "```\n- item|\n```")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # The next line is empty (not '- '). The buffer becomes
        # "```\n- item\n|\n```" with no marker continuation.
        assert "- item\n- " not in editor.toPlainText()
        # Cursor is on a line that's empty (or contains only leading
        # whitespace from auto-indent, which is fine).
        cursor_line = editor.textCursor().block().text()
        assert cursor_line.lstrip(" \t") == ""

    def test_empty_list_strip_suppressed_in_fence(self, editor):
        """An empty list marker ``- |`` inside a fence: Enter should NOT
        invoke the "strip the empty marker" logic - it should treat the
        line as plain text."""
        _set_buffer_and_place_cursor(editor, "```\n- |\n```")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # The '- ' on the original line must still be there.
        assert "- " in editor.toPlainText()

    def test_auto_indent_preserved_in_fence_by_default(self, editor):
        """With default settings, indent IS preserved inside a fence."""
        _set_buffer_and_place_cursor(editor, "```\n    code|\n```")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        # New line starts with 4 spaces.
        cursor = editor.textCursor()
        new_line = cursor.block().text()
        assert new_line.startswith("    "), (
            f"expected 4-space indent on new line; got {new_line!r}"
        )

    def test_auto_indent_suppressed_when_setting_off(self, editor):
        """With ``editor.auto_indent_in_verbatim=False``, indent is NOT
        preserved inside a fence - new line starts at column 0."""
        editor.ctx.set("editor.auto_indent_in_verbatim", False)
        _set_buffer_and_place_cursor(editor, "```\n    code|\n```")
        _press(editor, "\n", key=Qt.Key.Key_Return)
        new_line = editor.textCursor().block().text()
        assert new_line == "", (
            f"expected empty new line (no indent) with setting off; got {new_line!r}"
        )

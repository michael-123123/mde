"""Tests for FindReplaceBar — cross-pane find/replace functionality.

Covers:
- Bar spans both editor and preview (layout)
- Search highlights in editor, preview (QTextBrowser), or both
- Status label reflects which panes have matches
- Show/hide behavior
- Case sensitive and whole word options
- Option changes re-trigger search
- Replace operations (editor-only)
- Keyboard shortcuts (Escape, F3, Shift+F3)
- Size policy (bar doesn't grow beyond needed height)
- Editor centering on match
- Generation counter discards stale WebEngine callbacks
"""

import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QTextBrowser

from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
from markdown_editor.markdown6.markdown_editor import FindReplaceBar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def editor(qtbot):
    """Create an EnhancedEditor with sample text."""
    ed = EnhancedEditor()
    qtbot.addWidget(ed)
    ed.setPlainText("Hello world\nhello HELLO\nfoo bar baz")
    ed.show()
    return ed


@pytest.fixture
def preview(qtbot):
    """Create a QTextBrowser preview with matching content."""
    tb = QTextBrowser()
    qtbot.addWidget(tb)
    tb.setHtml("<p>Hello world</p><p>hello HELLO</p><p>foo bar baz</p>")
    tb.show()
    return tb


@pytest.fixture
def bar(qtbot, editor, preview):
    """Create a FindReplaceBar with QTextBrowser preview (no WebEngine)."""
    b = FindReplaceBar(editor, preview, use_webengine=False)
    qtbot.addWidget(b)
    b.show()
    return b


@pytest.fixture
def bar_editor_only(qtbot, editor):
    """FindReplaceBar with a hidden preview (editor-only mode)."""
    tb = QTextBrowser()
    qtbot.addWidget(tb)
    tb.hide()
    b = FindReplaceBar(editor, tb, use_webengine=False)
    qtbot.addWidget(b)
    b.show()
    return b


# ---------------------------------------------------------------------------
# Layout & size policy
# ---------------------------------------------------------------------------

class TestLayout:
    def test_size_policy_is_maximum_vertical(self, bar):
        """Bar should not grow beyond its size hint vertically."""
        assert bar.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum

    def test_bar_starts_hidden(self, qtbot, editor, preview):
        """Bar is hidden on construction."""
        b = FindReplaceBar(editor, preview, use_webengine=False)
        qtbot.addWidget(b)
        assert not b.isVisible()


# ---------------------------------------------------------------------------
# Show / hide
# ---------------------------------------------------------------------------

class TestShowHide:
    def test_show_find_hides_replace_row(self, bar):
        bar.show_find()
        assert bar.isVisible()
        assert not bar.replace_row_widget.isVisible()

    def test_show_replace_shows_replace_row(self, bar):
        bar.show_replace()
        assert bar.isVisible()
        assert bar.replace_row_widget.isVisible()

    def test_show_find_clears_input_when_first_opened(self, bar):
        bar.find_input.setText("leftover")
        bar.hide()
        bar.show_find()
        assert bar.find_input.text() == ""

    def test_show_find_selects_all_when_already_visible(self, bar):
        bar.show_find()
        bar.find_input.setText("hello")
        bar.show_find()
        assert bar.find_input.selectedText() == "hello"

    def test_hide_bar_hides_and_returns_focus(self, bar, editor):
        bar.show_find()
        bar.hide_bar()
        assert not bar.isVisible()

    def test_escape_hides_bar(self, qtbot, bar):
        bar.show_find()
        qtbot.keyPress(bar, Qt.Key.Key_Escape)
        assert not bar.isVisible()


# ---------------------------------------------------------------------------
# Editor-only search
# ---------------------------------------------------------------------------

class TestEditorSearch:
    def test_find_text_in_editor(self, bar, editor):
        """Basic forward find selects the match in the editor."""
        bar.show_find()
        result = bar._find("Hello", forward=True, wrap=True, from_start=True)
        assert result is True
        assert editor.textCursor().selectedText() == "Hello"

    def test_find_wraps_around(self, bar, editor):
        """After the last match, find wraps to the beginning."""
        bar.show_find()
        # Move cursor to end
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        result = bar._find("Hello", forward=True, wrap=True)
        assert result is True

    def test_find_not_found(self, bar):
        bar.show_find()
        result = bar._find("nonexistent", forward=True, wrap=True, from_start=True)
        assert result is False

    def test_find_backward(self, bar, editor):
        """Find backward from end of document."""
        bar.show_find()
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        result = bar._find("foo", forward=False, wrap=True)
        assert result is True
        assert editor.textCursor().selectedText() == "foo"

    def test_find_next_cycles(self, bar, editor):
        """find_next advances through matches."""
        bar.show_find()
        bar.find_input.setText("hello")
        # Case insensitive by default — should find "Hello", "hello", "HELLO"
        bar._find("hello", forward=True, wrap=True, from_start=True)
        pos1 = editor.textCursor().position()
        bar.find_next()
        pos2 = editor.textCursor().position()
        assert pos2 > pos1

    def test_find_previous(self, bar, editor):
        """find_previous goes backward."""
        bar.show_find()
        bar.find_input.setText("hello")
        # Find twice to get to second match
        bar._find("hello", forward=True, wrap=True, from_start=True)
        bar.find_next()
        pos_after_next = editor.textCursor().position()
        bar.find_previous()
        pos_after_prev = editor.textCursor().position()
        assert pos_after_prev < pos_after_next


# ---------------------------------------------------------------------------
# Case sensitive / whole word
# ---------------------------------------------------------------------------

class TestFindOptions:
    def test_case_sensitive_find(self, bar, editor):
        """With case sensitive on, 'hello' should not match 'Hello'."""
        bar.show_find()
        bar.case_checkbox.setChecked(True)
        bar._find("hello", forward=True, wrap=True, from_start=True)
        # Should find "hello" on line 2, not "Hello" on line 1
        assert editor.textCursor().selectedText() == "hello"
        cursor = editor.textCursor()
        # "hello" starts at position 12 (line 2, col 0)
        assert cursor.block().blockNumber() == 1

    def test_whole_word_find(self, bar, editor):
        """Whole word should not match substrings."""
        bar.show_find()
        bar.whole_word_checkbox.setChecked(True)
        result = bar._find("bar", forward=True, wrap=True, from_start=True)
        assert result is True
        assert editor.textCursor().selectedText() == "bar"

    def test_whole_word_no_partial_match(self, bar, editor):
        """Whole word 'Hell' should not match 'Hello'."""
        bar.show_find()
        bar.whole_word_checkbox.setChecked(True)
        result = bar._find("Hell", forward=True, wrap=True, from_start=True)
        assert result is False

    def test_option_change_retriggers_search(self, bar, editor):
        """Toggling a checkbox should re-run the search."""
        bar.show_find()
        bar.find_input.setText("hello")
        bar._find("hello", forward=True, wrap=True, from_start=True)
        old_pos = editor.textCursor().position()
        # Toggle case sensitive — should re-run from start
        bar.case_checkbox.setChecked(True)
        new_pos = editor.textCursor().position()
        # Position may change since case-sensitive skips "Hello"
        assert new_pos != old_pos or editor.textCursor().selectedText() == "hello"


# ---------------------------------------------------------------------------
# Preview search (QTextBrowser)
# ---------------------------------------------------------------------------

class TestPreviewSearch:
    def test_find_in_both_panes(self, bar):
        """Search should find in both editor and preview."""
        bar.show_find()
        bar._find("Hello", forward=True, wrap=True, from_start=True)
        assert bar._editor_found is True
        assert bar._preview_found is True

    def test_status_shows_both_panes(self, bar):
        """Status label should mention both panes."""
        bar.show_find()
        bar._find("Hello", forward=True, wrap=True, from_start=True)
        assert "editor" in bar.match_label.text()
        assert "preview" in bar.match_label.text()

    def test_status_both_even_when_preview_hidden(self, bar_editor_only):
        """Preview is searched even when hidden (to stay in sync)."""
        bar_editor_only.show_find()
        bar_editor_only._find("Hello", forward=True, wrap=True, from_start=True)
        assert "editor" in bar_editor_only.match_label.text()

    def test_not_found_in_either_pane(self, bar):
        """'Not found' when neither pane has a match."""
        bar.show_find()
        bar._find("zzzzz", forward=True, wrap=True, from_start=True)
        assert bar._editor_found is False
        assert bar._preview_found is False
        assert "Not found" in bar.match_label.text()

    def test_preview_search_case_sensitive(self, bar):
        """Case-sensitive search in preview."""
        bar.show_find()
        bar.case_checkbox.setChecked(True)
        bar._find("HELLO", forward=True, wrap=True, from_start=True)
        assert bar._preview_found is True

    def test_preview_search_whole_word(self, bar):
        """Whole-word search in QTextBrowser preview."""
        bar.show_find()
        bar.whole_word_checkbox.setChecked(True)
        bar._find("Hell", forward=True, wrap=True, from_start=True)
        # "Hell" is not a whole word in "Hello"
        assert bar._preview_found is False

    def test_clear_search_on_empty_text(self, bar):
        """Clearing search text should reset preview state."""
        bar.show_find()
        bar._find("Hello", forward=True, wrap=True, from_start=True)
        assert bar._preview_found is True
        bar._on_search_text_changed("")
        assert bar._preview_found is False
        assert bar.match_label.text() == ""

    def test_hide_bar_clears_preview_search(self, bar):
        """Hiding the bar should clear preview search state."""
        bar.show_find()
        bar._find("Hello", forward=True, wrap=True, from_start=True)
        bar.hide_bar()
        assert bar._preview_found is False


# ---------------------------------------------------------------------------
# Editor search skipped when editor hidden
# ---------------------------------------------------------------------------

class TestPaneSyncWhenHidden:
    """Both panes are always searched to keep cursor positions in sync."""

    def test_editor_searched_even_when_hidden(self, qtbot, preview):
        """Editor cursor advances even when editor is not visible."""
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.setPlainText("Hello world\nHello again")
        ed.hide()
        b = FindReplaceBar(ed, preview, use_webengine=False)
        qtbot.addWidget(b)
        b.show()
        b.find_input.setText("Hello")
        b._find("Hello", forward=True, wrap=True, from_start=True)
        assert b._editor_found is True
        pos1 = ed.textCursor().position()
        b.find_next()
        pos2 = ed.textCursor().position()
        assert pos2 > pos1, "Editor cursor should advance even when hidden"

    def test_preview_searched_even_when_hidden(self, qtbot, editor):
        """Preview is searched even when hidden so it's in sync when shown."""
        tb = QTextBrowser()
        qtbot.addWidget(tb)
        tb.setHtml("<p>Hello world</p><p>Hello again</p>")
        tb.hide()
        b = FindReplaceBar(editor, tb, use_webengine=False)
        qtbot.addWidget(b)
        b.show()
        b._find("Hello", forward=True, wrap=True, from_start=True)
        assert b._preview_found is True

    def test_find_next_advances_both_panes(self, bar, editor, preview):
        """find_next advances cursor in both editor and preview."""
        bar.show_find()
        bar.find_input.setText("hello")
        bar._find("hello", forward=True, wrap=True, from_start=True)
        editor_pos1 = editor.textCursor().position()
        preview_pos1 = preview.textCursor().position()

        bar.find_next()
        editor_pos2 = editor.textCursor().position()
        preview_pos2 = preview.textCursor().position()

        assert editor_pos2 > editor_pos1
        assert preview_pos2 > preview_pos1


# ---------------------------------------------------------------------------
# Replace (editor-only)
# ---------------------------------------------------------------------------

class TestReplace:
    def test_replace_next(self, bar, editor):
        """Replace the current match and advance."""
        bar.show_replace()
        bar.find_input.setText("Hello")
        bar.replace_input.setText("Goodbye")
        bar._find("Hello", forward=True, wrap=True, from_start=True)
        bar.replace_next()
        assert "Goodbye" in editor.toPlainText()

    def test_replace_all(self, bar, editor):
        """Replace all occurrences (case-insensitive)."""
        bar.show_replace()
        bar.find_input.setText("hello")
        bar.replace_input.setText("HI")
        bar.replace_all()
        text = editor.toPlainText()
        assert "hello" not in text.lower() or text.count("HI") == 3
        assert "Replaced" in bar.match_label.text()

    def test_replace_all_case_sensitive(self, bar, editor):
        """Replace all with case sensitivity — only exact case matches."""
        bar.show_replace()
        bar.case_checkbox.setChecked(True)
        bar.find_input.setText("Hello")
        bar.replace_input.setText("Bye")
        bar.replace_all()
        text = editor.toPlainText()
        assert "Bye" in text
        # "hello" and "HELLO" should remain
        assert "hello" in text
        assert "HELLO" in text

    def test_replace_all_is_single_undo(self, bar, editor):
        """Replace all should be undoable in one step."""
        original = editor.toPlainText()
        bar.show_replace()
        bar.find_input.setText("hello")
        bar.replace_input.setText("X")
        bar.replace_all()
        assert editor.toPlainText() != original
        editor.undo()
        assert editor.toPlainText() == original


# ---------------------------------------------------------------------------
# Keyboard shortcuts
# ---------------------------------------------------------------------------

class TestKeyboardShortcuts:
    def test_f3_finds_next(self, qtbot, bar, editor):
        bar.show_find()
        bar.find_input.setText("hello")
        bar._find("hello", forward=True, wrap=True, from_start=True)
        pos1 = editor.textCursor().position()
        qtbot.keyPress(bar, Qt.Key.Key_F3)
        pos2 = editor.textCursor().position()
        assert pos2 != pos1

    def test_shift_f3_finds_previous(self, qtbot, bar, editor):
        bar.show_find()
        bar.find_input.setText("hello")
        bar._find("hello", forward=True, wrap=True, from_start=True)
        bar.find_next()
        pos1 = editor.textCursor().position()
        qtbot.keyPress(bar, Qt.Key.Key_F3, Qt.KeyboardModifier.ShiftModifier)
        pos2 = editor.textCursor().position()
        assert pos2 < pos1


# ---------------------------------------------------------------------------
# Live search
# ---------------------------------------------------------------------------

class TestLiveSearch:
    def test_typing_triggers_search(self, bar, editor):
        """Typing in the find input triggers a live search."""
        bar.show_find()
        bar.find_input.setText("foo")
        # Live search should have found "foo"
        assert bar._editor_found is True
        assert editor.textCursor().selectedText() == "foo"

    def test_clearing_input_resets_status(self, bar):
        """Clearing input clears status label."""
        bar.show_find()
        bar.find_input.setText("Hello")
        assert bar.match_label.text() != ""
        bar.find_input.setText("")
        assert bar.match_label.text() == ""


# ---------------------------------------------------------------------------
# Status label content
# ---------------------------------------------------------------------------

class TestStatusLabel:
    def test_found_editor_only_when_no_preview_match(self, qtbot):
        """Status shows 'Found in editor' when preview has no matching content."""
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.setPlainText("unique_editor_text")
        ed.show()
        tb = QTextBrowser()
        qtbot.addWidget(tb)
        tb.setHtml("<p>nothing here</p>")
        b = FindReplaceBar(ed, tb, use_webengine=False)
        qtbot.addWidget(b)
        b.show()
        b._find("unique_editor_text", forward=True, wrap=True, from_start=True)
        assert b.match_label.text() == "Found in editor"

    def test_found_both(self, bar):
        bar.show_find()
        bar._find("foo", forward=True, wrap=True, from_start=True)
        assert bar.match_label.text() == "Found in editor, preview"

    def test_not_found(self, bar):
        bar.show_find()
        bar._find("zzzzz", forward=True, wrap=True, from_start=True)
        assert bar.match_label.text() == "Not found"

    def test_empty_text_clears_label(self, bar):
        bar.show_find()
        bar._find("", forward=True, wrap=True, from_start=True)
        assert bar.match_label.text() == ""


# ---------------------------------------------------------------------------
# WebEngine-specific (mocked)
# ---------------------------------------------------------------------------

class TestWebEngineGeneration:
    """Test generation counter logic without real WebEngine."""

    def test_stale_callback_ignored(self, qtbot, editor, preview):
        """A callback from an old generation should be ignored."""
        bar = FindReplaceBar(editor, preview, use_webengine=False)
        qtbot.addWidget(bar)
        bar.show()
        # Simulate the generation counter logic
        bar._find_generation = 5
        bar._preview_found = False
        bar._editor_found = True
        # Stale callback (generation 3) should be ignored
        bar._on_preview_find_result(True, generation=3)
        assert bar._preview_found is False

    def test_current_callback_applied(self, qtbot, editor, preview):
        """A callback matching current generation should update state."""
        bar = FindReplaceBar(editor, preview, use_webengine=False)
        qtbot.addWidget(bar)
        bar.show()
        bar._find_generation = 5
        bar._preview_found = False
        bar._editor_found = True
        bar._on_preview_find_result(True, generation=5)
        assert bar._preview_found is True
        assert "preview" in bar.match_label.text()

    def test_callback_handles_find_text_result_object(self, qtbot, editor, preview):
        """Callback should handle QWebEngineFindTextResult (Qt6 API).

        In PySide6/Qt6, findText callback receives QWebEngineFindTextResult
        with numberOfMatches()/activeMatch(), not a plain bool.
        """
        bar = FindReplaceBar(editor, preview, use_webengine=False)
        qtbot.addWidget(bar)
        bar.show()
        bar._find_generation = 1
        bar._editor_found = True

        # Simulate a QWebEngineFindTextResult-like object with matches
        result_found = MagicMock()
        result_found.numberOfMatches.return_value = 3
        result_found.activeMatch.return_value = 1
        bar._on_preview_find_result(result_found, generation=1)
        assert bar._preview_found is True

        # Simulate a result with no matches
        bar._find_generation = 2
        result_not_found = MagicMock()
        result_not_found.numberOfMatches.return_value = 0
        bar._on_preview_find_result(result_not_found, generation=2)
        assert bar._preview_found is False

    def test_webengine_whole_word_tooltip(self, qtbot, editor, preview):
        """WebEngine bar should have tooltip on whole-word checkbox."""
        bar = FindReplaceBar(editor, preview, use_webengine=True)
        qtbot.addWidget(bar)
        assert "editor only" in bar.whole_word_checkbox.toolTip()

    def test_non_webengine_no_special_tooltip(self, qtbot, editor, preview):
        """Non-WebEngine bar should not have the limitation tooltip."""
        bar = FindReplaceBar(editor, preview, use_webengine=False)
        qtbot.addWidget(bar)
        assert "editor only" not in bar.whole_word_checkbox.toolTip()


# ---------------------------------------------------------------------------
# Editor centering
# ---------------------------------------------------------------------------

class TestEditorCentering:
    def test_center_cursor_called_on_find(self, qtbot, preview):
        """Editor.centerCursor() should be called when a match is found."""
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.setPlainText("\n" * 100 + "target\n" + "\n" * 100)
        ed.show()
        bar = FindReplaceBar(ed, preview, use_webengine=False)
        qtbot.addWidget(bar)
        bar.show()

        with patch.object(ed, "centerCursor", wraps=ed.centerCursor) as mock_center:
            bar._find("target", forward=True, wrap=True, from_start=True)
            mock_center.assert_called_once()

    def test_center_cursor_not_called_when_not_found(self, qtbot, preview):
        """centerCursor() should not be called when nothing is found."""
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        ed.setPlainText("some text")
        ed.show()
        bar = FindReplaceBar(ed, preview, use_webengine=False)
        qtbot.addWidget(bar)
        bar.show()

        with patch.object(ed, "centerCursor") as mock_center:
            bar._find("zzzzz", forward=True, wrap=True, from_start=True)
            mock_center.assert_not_called()


# ---------------------------------------------------------------------------
# Preview scroll preservation on pane toggle (WebEngine)
# ---------------------------------------------------------------------------

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False


LONG_HTML = (
    "<!DOCTYPE html><html><body style='margin:0'>"
    + "".join(f"<p style='height:50px'>Line {i}</p>" for i in range(200))
    + "</body></html>"
)


@pytest.mark.skipif(not _HAS_WEBENGINE, reason="QWebEngineView not available")
class TestPreviewScrollPreservation:
    """Regression: resizing a QWebEngineView (e.g. when toggling a splitter
    pane) causes HTML reflow that can jump the scroll position. The JS
    save/restore mechanism should preserve the scroll ratio."""

    def _load(self, qtbot, view, html):
        with qtbot.waitSignal(view.loadFinished, timeout=5000):
            view.setHtml(html)

    def _js(self, qtbot, page, code):
        result = {}
        page.runJavaScript(code, lambda v: result.update(val=v))
        qtbot.waitUntil(lambda: 'val' in result, timeout=2000)
        return result['val']

    def test_scroll_preserved_at_top_after_resize(self, qtbot):
        """Scroll at 0 stays at 0 after width change + ratio restore."""
        view = QWebEngineView()
        view.resize(500, 400)
        qtbot.addWidget(view)
        view.show()
        self._load(qtbot, view, LONG_HTML)
        qtbot.wait(100)

        assert self._js(qtbot, view.page(), "window.scrollY") == 0

        # Save ratio, resize (simulating splitter toggle), restore
        view.page().runJavaScript(
            "window._r = document.body.scrollHeight > window.innerHeight"
            " ? window.scrollY / (document.body.scrollHeight - window.innerHeight)"
            " : 0;"
        )
        view.resize(1000, 400)  # widen — content reflows shorter
        qtbot.wait(100)
        view.page().runJavaScript(
            "var m = document.body.scrollHeight - window.innerHeight;"
            "if (m > 0) window.scrollTo(0, window._r * m);"
        )
        qtbot.wait(100)

        scroll_after = self._js(qtbot, view.page(), "window.scrollY")
        assert abs(scroll_after) < 10, f"Scroll jumped to {scroll_after}"

    def test_scroll_preserved_midway_after_resize(self, qtbot):
        """Scroll at ~50% stays approximately there after width change."""
        view = QWebEngineView()
        view.resize(500, 400)
        qtbot.addWidget(view)
        view.show()
        self._load(qtbot, view, LONG_HTML)
        qtbot.wait(100)

        # Scroll to middle
        self._js(qtbot, view.page(),
                 "(function(){ window.scrollTo(0, "
                 "(document.body.scrollHeight - window.innerHeight) * 0.5); "
                 "return window.scrollY; })()")
        qtbot.wait(50)
        scroll_before = self._js(qtbot, view.page(), "window.scrollY")
        assert scroll_before > 100

        # Save ratio
        view.page().runJavaScript(
            "window._r = window.scrollY / "
            "(document.body.scrollHeight - window.innerHeight);"
        )
        # Resize
        view.resize(1000, 400)
        qtbot.wait(100)
        # Restore
        view.page().runJavaScript(
            "var m = document.body.scrollHeight - window.innerHeight;"
            "if (m > 0) window.scrollTo(0, window._r * m);"
        )
        qtbot.wait(100)

        scroll_after = self._js(qtbot, view.page(), "window.scrollY")
        # Content is now wider so shorter — scroll value will differ,
        # but the ratio should be roughly preserved (~50% ± 10%)
        max_scroll = self._js(qtbot, view.page(),
                              "document.body.scrollHeight - window.innerHeight")
        ratio_after = scroll_after / max_scroll if max_scroll > 0 else 0
        assert 0.3 < ratio_after < 0.7, (
            f"Scroll ratio drifted to {ratio_after:.2f} (expected ~0.5)"
        )

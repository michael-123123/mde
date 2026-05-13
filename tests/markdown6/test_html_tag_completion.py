"""Tests for the HTML tag-completion helper.

The helper is a pure function: given the buffer text BEFORE the user's
``>`` keystroke is applied, and the cursor position there, return the
tag name to close with ``</tag>``, or ``None`` to skip completion.

These tests pin the rules independent of any Qt/editor wiring.
"""

from markdown_editor.markdown6.enhanced_editor import (
    _compute_html_tag_completion,
)


class TestSimpleOpenTagCompletes:
    """The happy path: well-formed open tag returns the tag name."""

    def test_div(self):
        assert _compute_html_tag_completion("<div", 4) == "div"

    def test_span(self):
        assert _compute_html_tag_completion("<span", 5) == "span"

    def test_tag_with_attributes(self):
        assert _compute_html_tag_completion('<a href="x"', 11) == "a"

    def test_tag_with_dash_in_name(self):
        """Custom-element names may contain dashes (``my-button``)."""
        assert _compute_html_tag_completion("<my-component", 13) == "my-component"

    def test_tag_with_namespace_colon(self):
        """XML-style ``ns:tag`` shows up in some markdown (e.g. SVG)."""
        assert _compute_html_tag_completion("<svg:rect", 9) == "svg:rect"


class TestSelfClosingSkipped:
    """No completion for self-closing tags (rule: trimmed content ends in '/')."""

    def test_br_no_space(self):
        assert _compute_html_tag_completion("<br/", 4) is None

    def test_br_with_space(self):
        assert _compute_html_tag_completion("<br /", 5) is None

    def test_with_attrs_and_self_close(self):
        assert _compute_html_tag_completion('<img src="x" /', 14) is None

    def test_self_close_after_multiple_spaces(self):
        assert _compute_html_tag_completion("<hr    /", 8) is None


class TestNotATagSkipped:
    """No completion for non-element constructs."""

    def test_closing_tag(self):
        """Typing ``</div`` and then ``>`` should NOT add a closer."""
        assert _compute_html_tag_completion("</div", 5) is None

    def test_comment_opener(self):
        assert _compute_html_tag_completion("<!--", 4) is None

    def test_doctype(self):
        assert _compute_html_tag_completion("<!DOCTYPE html", 14) is None

    def test_processing_instruction(self):
        assert _compute_html_tag_completion("<?xml", 5) is None

    def test_only_left_angle(self):
        assert _compute_html_tag_completion("<", 1) is None

    def test_name_starts_with_digit(self):
        assert _compute_html_tag_completion("<5tag", 5) is None

    def test_no_left_angle_at_all(self):
        assert _compute_html_tag_completion("hello", 5) is None


class TestPriorTagsDoNotInterfere:
    """The ``<`` we react to must be the OPEN one to our left -
    a prior fully-closed tag must not capture us."""

    def test_after_closed_tag(self):
        text = "<p>hello</p><span"
        assert _compute_html_tag_completion(text, len(text)) == "span"

    def test_after_self_closing_tag(self):
        text = "<br/><a"
        assert _compute_html_tag_completion(text, len(text)) == "a"

    def test_cursor_after_existing_close_angle_skips(self):
        """Cursor sits after ``<div>`` - i.e. the ``>`` is already
        present somewhere before us. Don't double-fire."""
        # last '<' at 0, but there's a '>' between it and cursor.
        assert _compute_html_tag_completion("<div>", 5) is None


class TestAlreadyClosedSkipped:
    """Don't insert ``</tag>`` if the buffer already has one right after
    the cursor - avoids double-closing when the user is re-typing."""

    def test_closer_immediately_after_cursor(self):
        # Buffer state: "<div" + cursor + "</div>" - user is filling in
        # the open angle's '>'. Don't add a second </div>.
        text = "<div</div>"
        assert _compute_html_tag_completion(text, 4) is None

    def test_closer_after_whitespace(self):
        """Whitespace between cursor and the closer shouldn't matter."""
        text = "<div </div>"
        assert _compute_html_tag_completion(text, 4) is None

    def test_different_closer_does_NOT_skip(self):
        """A nearby closer for a *different* tag is irrelevant."""
        text = "<div</span>"
        assert _compute_html_tag_completion(text, 4) == "div"

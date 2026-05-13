"""Tests for the Pandoc/Obsidian-style ``==text==`` highlight extension."""

import markdown
import pytest

from markdown_editor.markdown6.extensions import MarkExtension


@pytest.fixture
def md():
    return markdown.Markdown(extensions=[MarkExtension()])


class TestMarkExtension:
    def test_simple_highlight(self, md):
        assert "<mark>highlighted</mark>" in md.convert("==highlighted==")

    def test_highlight_inside_sentence(self, md):
        out = md.convert("This is ==marked== text.")
        assert "<mark>marked</mark>" in out

    def test_multiple_highlights_in_line(self, md):
        out = md.convert("==one== and ==two==")
        assert out.count("<mark>") == 2

    def test_no_highlight_for_single_equals(self, md):
        """``=text=`` is not a highlight - the pattern needs paired ``==``."""
        out = md.convert("=not highlighted=")
        assert "<mark>" not in out

    def test_no_highlight_for_unbalanced(self, md):
        """``==text=`` (missing the second ``=`` of the closer) is not
        a highlight."""
        out = md.convert("==not closed properly=")
        assert "<mark>" not in out

    def test_handles_special_chars_inside(self, md):
        out = md.convert("==hi *world* friend==")
        # The italic inside gets rendered.
        assert "<mark>" in out
        assert "<em>world</em>" in out

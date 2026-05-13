"""Tests for the Discord/Obsidian-style ``||text||`` spoiler extension."""

import markdown
import pytest

from markdown_editor.markdown6.extensions import SpoilerExtension


@pytest.fixture
def md():
    return markdown.Markdown(extensions=[SpoilerExtension()])


class TestSpoilerExtension:
    def test_simple_spoiler(self, md):
        out = md.convert("||hidden||")
        assert '<span class="spoiler">hidden</span>' in out

    def test_spoiler_inside_sentence(self, md):
        out = md.convert("The villain is ||Mr. X||!")
        assert '<span class="spoiler">Mr. X</span>' in out

    def test_multiple_spoilers_in_line(self, md):
        out = md.convert("||first|| then ||second||")
        assert out.count('class="spoiler"') == 2

    def test_no_spoiler_for_single_pipe(self, md):
        """``|text|`` is NOT a spoiler - the pattern needs ``||``."""
        out = md.convert("|not spoiler|")
        assert 'class="spoiler"' not in out

    def test_no_spoiler_for_unbalanced(self, md):
        """``||text|`` (missing the second ``|`` of the closer) is not
        a spoiler."""
        out = md.convert("||not closed properly|")
        assert 'class="spoiler"' not in out

    def test_no_spoiler_for_empty(self, md):
        """``||||`` (empty content) doesn't trigger - the regex requires
        at least one char of content."""
        out = md.convert("||||")
        assert 'class="spoiler"' not in out

    def test_table_cell_separator_unaffected(self, md):
        """GFM tables use single ``|`` as separator. A line like
        ``| a | b |`` must not be mis-parsed as a spoiler containing
        ``a `` and ``b``."""
        out = md.convert("| a | b |")
        assert 'class="spoiler"' not in out

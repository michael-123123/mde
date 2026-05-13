"""Tests for the Discord/Obsidian-style ``||text||`` spoiler extension."""

import markdown
import pytest

from markdown_editor.markdown6.extensions import (
    SpoilerExtension,
    get_spoiler_css,
)


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


class TestSpoilerCSS:
    def test_returns_css_string(self):
        css = get_spoiler_css(dark_mode=False)
        assert isinstance(css, str)
        assert "span.spoiler" in css

    def test_blurs_text_by_default(self):
        """The base rule must blur the text - users see *something* is
        there (size, position) but can't read it until they reveal."""
        css = get_spoiler_css()
        assert "filter: blur(" in css

    def test_revealed_class_clears_blur(self):
        """`.revealed` (toggled by the click handler) removes the blur."""
        css = get_spoiler_css()
        assert "span.spoiler.revealed" in css
        # Find the revealed block and check it clears the filter.
        revealed_block = css.split("span.spoiler.revealed")[1].split("}")[0]
        assert "filter: none" in revealed_block


class TestSpoilerJS:
    def test_returns_script_tag(self):
        from markdown_editor.markdown6.extensions import get_spoiler_js
        js = get_spoiler_js()
        assert "<script>" in js
        assert "</script>" in js

    def test_toggles_revealed_class_on_click(self):
        from markdown_editor.markdown6.extensions import get_spoiler_js
        js = get_spoiler_js()
        # The click handler must toggle the `revealed` class.
        assert "classList.toggle" in js
        assert "revealed" in js
        assert "addEventListener('click'" in js or 'addEventListener("click"' in js

    def test_keyboard_accessible(self):
        """Enter / Space should also toggle - keyboard accessibility."""
        from markdown_editor.markdown6.extensions import get_spoiler_js
        js = get_spoiler_js()
        assert "Enter" in js
        assert "addEventListener('keydown'" in js or 'addEventListener("keydown"' in js



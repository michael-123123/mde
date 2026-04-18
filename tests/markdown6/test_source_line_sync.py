"""Tests for source-line-based scroll synchronization."""

import markdown
import pytest

from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
from markdown_editor.markdown6.extensions import (
    BreaklessListExtension, CalloutExtension, MathExtension,
    SourceLineExtension, SourceLinePostprocessor, SourceLinePreprocessor,
    TaskListExtension)

# ---------------------------------------------------------------------------
# Preprocessor tests
# ---------------------------------------------------------------------------

class TestSourceLinePreprocessor:
    """Tests for the SourceLinePreprocessor that injects <!-- SL:N --> markers."""

    @pytest.fixture
    def preprocessor(self):
        md = markdown.Markdown()
        pre = SourceLinePreprocessor(md)
        return pre

    def test_heading_gets_marker(self, preprocessor):
        lines = ["# Heading"]
        result = preprocessor.run(lines)
        assert result == ["<!-- SL:0 -->", "# Heading"]

    def test_paragraph_after_blank_gets_marker(self, preprocessor):
        lines = ["# Heading", "", "Some text here"]
        result = preprocessor.run(lines)
        assert "<!-- SL:0 -->" in result
        assert "<!-- SL:2 -->" in result

    def test_consecutive_nonblank_lines_no_extra_markers(self, preprocessor):
        lines = ["first line", "second line", "third line"]
        result = preprocessor.run(lines)
        # Only the first line (prev_blank starts True) should get a marker
        assert result.count("<!-- SL:0 -->") == 1
        assert "<!-- SL:1 -->" not in result
        assert "<!-- SL:2 -->" not in result

    def test_fenced_code_block_interior_not_marked(self, preprocessor):
        lines = [
            "```python",
            "def foo():",
            "    pass",
            "",
            "x = 1",
            "```",
        ]
        result = preprocessor.run(lines)
        # The fence opening gets a marker (prev_blank=True at start)
        assert "<!-- SL:0 -->" in result
        # Interior lines should NOT get markers (blank line inside fence)
        assert "<!-- SL:4 -->" not in result
        # The content inside the fence should be untouched
        assert "def foo():" in result
        assert "    pass" in result

    def test_multiple_blocks(self, preprocessor):
        lines = [
            "# Title",
            "",
            "Paragraph one.",
            "",
            "Paragraph two.",
        ]
        result = preprocessor.run(lines)
        assert "<!-- SL:0 -->" in result  # heading
        assert "<!-- SL:2 -->" in result  # para one
        assert "<!-- SL:4 -->" in result  # para two

    def test_heading_after_nonblank_still_marked(self, preprocessor):
        """Headings always get markers even without a preceding blank."""
        lines = ["some text", "# Heading"]
        result = preprocessor.run(lines)
        assert "<!-- SL:1 -->" in result

    def test_empty_input(self, preprocessor):
        assert preprocessor.run([]) == []

    def test_only_blank_lines(self, preprocessor):
        result = preprocessor.run(["", "", ""])
        assert result == ["", "", ""]


# ---------------------------------------------------------------------------
# Postprocessor tests
# ---------------------------------------------------------------------------

class TestSourceLinePostprocessor:
    """Tests for converting SL markers to data-source-line attributes."""

    @pytest.fixture
    def postprocessor(self):
        md = markdown.Markdown()
        post = SourceLinePostprocessor(md)
        return post

    def test_heading_gets_attribute(self, postprocessor):
        html = '<!-- SL:5 -->\n<h1>Title</h1>'
        result = postprocessor.run(html)
        assert 'data-source-line="5"' in result
        assert '<h1 data-source-line="5">' in result
        assert '<!-- SL:' not in result

    def test_paragraph_gets_attribute(self, postprocessor):
        html = '<!-- SL:3 -->\n<p>Hello</p>'
        result = postprocessor.run(html)
        assert '<p data-source-line="3">' in result

    def test_div_gets_attribute(self, postprocessor):
        html = '<!-- SL:10 -->\n<div class="callout">content</div>'
        result = postprocessor.run(html)
        assert '<div data-source-line="10" class="callout">' in result

    def test_pre_gets_attribute(self, postprocessor):
        html = '<!-- SL:7 -->\n<pre><code>x = 1</code></pre>'
        result = postprocessor.run(html)
        assert '<pre data-source-line="7">' in result

    def test_unmatched_markers_removed(self, postprocessor):
        html = '<!-- SL:99 -->\nSome raw text without block elements'
        result = postprocessor.run(html)
        assert '<!-- SL:' not in result

    def test_existing_attributes_preserved(self, postprocessor):
        html = '<!-- SL:2 -->\n<h1 id="foo">Title</h1>'
        result = postprocessor.run(html)
        assert 'data-source-line="2"' in result
        assert 'id="foo"' in result

    def test_hr_gets_attribute(self, postprocessor):
        html = '<!-- SL:4 -->\n<hr />'
        result = postprocessor.run(html)
        assert '<hr data-source-line="4" />' in result

    def test_ul_gets_attribute(self, postprocessor):
        html = '<!-- SL:6 -->\n<ul>\n<li>item</li>\n</ul>'
        result = postprocessor.run(html)
        assert '<ul data-source-line="6">' in result

    def test_multiple_markers(self, postprocessor):
        html = '<!-- SL:0 -->\n<h1>A</h1>\n<!-- SL:3 -->\n<p>B</p>'
        result = postprocessor.run(html)
        assert '<h1 data-source-line="0">' in result
        assert '<p data-source-line="3">' in result


# ---------------------------------------------------------------------------
# End-to-end pipeline tests
# ---------------------------------------------------------------------------

class TestSourceLineEndToEnd:
    """Test the full markdown→HTML pipeline with source-line injection."""

    @pytest.fixture
    def md(self):
        return markdown.Markdown(extensions=[SourceLineExtension()])

    @pytest.fixture
    def md_full(self):
        """Markdown instance with multiple extensions like the real app."""
        return markdown.Markdown(extensions=[
            "extra",
            BreaklessListExtension(),
            CalloutExtension(),
            MathExtension(),
            TaskListExtension(),
            SourceLineExtension(),
        ])

    def test_headings_get_source_lines(self, md):
        text = "# Title\n\nSome paragraph\n\n## Section"
        result = md.convert(text)
        assert 'data-source-line="0"' in result
        assert 'data-source-line="2"' in result
        assert 'data-source-line="4"' in result

    def test_no_stray_markers_in_output(self, md):
        text = "# Title\n\nParagraph\n\n```\ncode\n```\n\nMore text"
        result = md.convert(text)
        assert '<!-- SL:' not in result

    def test_code_block_content_not_corrupted(self, md):
        text = "```\nprint('hello')\n```"
        result = md.convert(text)
        assert "print(&#x27;hello&#x27;)" in result or "print('hello')" in result
        assert '<!-- SL:' not in result

    def test_with_callout_extension(self, md_full):
        text = "# Title\n\n> [!NOTE]\n> This is a note\n\nParagraph after"
        result = md_full.convert(text)
        assert 'data-source-line="0"' in result  # heading
        assert '<!-- SL:' not in result

    def test_mixed_content(self, md):
        text = (
            "# Heading 1\n"
            "\n"
            "First paragraph.\n"
            "\n"
            "- item 1\n"
            "- item 2\n"
            "\n"
            "## Heading 2\n"
            "\n"
            "Second paragraph.\n"
        )
        result = md.convert(text)
        # Heading 1 at line 0
        assert 'data-source-line="0"' in result
        # Paragraph at line 2
        assert 'data-source-line="2"' in result
        # List at line 4
        assert 'data-source-line="4"' in result
        # Heading 2 at line 7
        assert 'data-source-line="7"' in result
        # Second paragraph at line 9
        assert 'data-source-line="9"' in result

    def test_empty_document(self, md):
        result = md.convert("")
        assert '<!-- SL:' not in result

    def test_single_line(self, md):
        result = md.convert("Hello world")
        assert 'data-source-line="0"' in result


# ---------------------------------------------------------------------------
# EnhancedEditor.get_first_visible_line() tests
# ---------------------------------------------------------------------------

class TestGetFirstVisibleLine:

    @pytest.fixture
    def editor(self, qtbot):
        ed = EnhancedEditor()
        qtbot.addWidget(ed)
        return ed

    def test_returns_zero_at_top(self, editor):
        editor.setPlainText("line 1\nline 2\nline 3")
        assert editor.get_first_visible_line() == 0

    def test_returns_int(self, editor):
        editor.setPlainText("a\nb\nc\nd\ne")
        result = editor.get_first_visible_line()
        assert isinstance(result, int)

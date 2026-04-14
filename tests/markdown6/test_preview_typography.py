"""Tests for preview typography settings."""

import pytest

from markdown_editor.markdown6.app_context import get_app_context


class _Ctx:
    """Minimal stand-in for MarkdownEditor — just enough for get_html_template."""

    def __init__(self):
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor
        self.ctx = get_app_context()
        # Bind the real get_html_template to this object
        self.get_html_template = MarkdownEditor.get_html_template.__get__(self)


class TestTypographyDefaults:
    """Verify that default typography settings produce the same CSS as
    the previously hardcoded values."""

    def test_font_families_default_to_empty(self):
        """Empty string means 'use the built-in CSS font stack'."""
        s = get_app_context()
        assert s.get("preview.body_font_family") == ""
        assert s.get("preview.code_font_family") == ""
        assert s.get("preview.heading_font_family") == ""

    def test_heading_sizes_match_hardcoded(self):
        s = get_app_context()
        assert s.get("preview.h1_size") == 2.0
        assert s.get("preview.h1_size_unit") == "em"
        assert s.get("preview.h2_size") == 1.5
        assert s.get("preview.h2_size_unit") == "em"
        assert s.get("preview.h3_size") == 1.25
        assert s.get("preview.h3_size_unit") == "em"

    def test_code_size_matches_hardcoded(self):
        s = get_app_context()
        assert s.get("preview.code_size") == 85
        assert s.get("preview.code_size_unit") == "%"

    def test_line_height_default(self):
        assert get_app_context().get("preview.line_height") == 1.5


class TestTypographyInHtml:
    """Verify that typography settings are injected into the preview HTML."""

    @pytest.fixture
    def tmpl(self):
        return _Ctx()

    def test_default_html_uses_hardcoded_font_stacks(self, tmpl):
        """With empty font settings, the HTML should contain the original
        hardcoded CSS font stacks."""
        html = tmpl.get_html_template("<p>test</p>")
        assert "-apple-system" in html
        assert "SFMono-Regular" in html
        assert "font-size: 2.0em" in html  # h1
        assert "font-size: 1.5em" in html  # h2
        assert "font-size: 85%" in html    # code

    def test_custom_body_font_produces_css_with_fallback(self, tmpl):
        """Setting a body font should produce '"FontName", sans-serif'."""
        get_app_context().set("preview.body_font_family", "Georgia")
        html = tmpl.get_html_template("<p>test</p>")
        assert '"Georgia", sans-serif' in html
        # The old hardcoded stack should NOT appear
        assert "-apple-system" not in html

    def test_custom_code_font_produces_css_with_fallback(self, tmpl):
        get_app_context().set("preview.code_font_family", "Fira Code")
        html = tmpl.get_html_template("<p>test</p>")
        assert '"Fira Code", monospace' in html
        assert "SFMono-Regular" not in html

    def test_custom_heading_font_injected(self, tmpl):
        get_app_context().set("preview.heading_font_family", "Impact")
        html = tmpl.get_html_template("<p>test</p>")
        assert '"Impact", sans-serif' in html

    def test_empty_heading_font_no_font_family_in_headings(self, tmpl):
        """When heading font is empty, heading CSS should not have
        a separate font-family declaration."""
        get_app_context().set("preview.heading_font_family", "")
        html = tmpl.get_html_template("<p>test</p>")
        # Find the h1 rule and check it doesn't have font-family
        h1_section = html.split("h1 {")[1].split("}")[0]
        assert "font-family" not in h1_section

    def test_heading_size_px_unit(self, tmpl):
        get_app_context().set("preview.h1_size", 32)
        get_app_context().set("preview.h1_size_unit", "px")
        html = tmpl.get_html_template("<p>test</p>")
        assert "font-size: 32px" in html

    def test_code_size_px_unit(self, tmpl):
        get_app_context().set("preview.code_size", 14)
        get_app_context().set("preview.code_size_unit", "px")
        html = tmpl.get_html_template("<p>test</p>")
        assert "font-size: 14px" in html

    def test_line_height_injected(self, tmpl):
        get_app_context().set("preview.line_height", 2.0)
        html = tmpl.get_html_template("<p>test</p>")
        assert "line-height: 2.0" in html

    def test_qtextbrowser_uses_settings_too(self, tmpl):
        get_app_context().set("preview.body_font_family", "Courier")
        html = tmpl.get_html_template("<p>test</p>", for_qtextbrowser=True)
        assert '"Courier", sans-serif' in html

    def test_fresh_defaults_match_original_css(self, tmpl):
        """Critical: with all defaults, the generated CSS must be
        byte-for-byte identical to the original hardcoded version for
        body, h1-h3, code, and pre font-family and font-size."""
        html = tmpl.get_html_template("<p>test</p>")
        # These exact strings were in the original hardcoded CSS
        assert 'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif' in html
        assert 'font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' in html
        assert "font-size: 2.0em" in html
        assert "font-size: 1.5em" in html
        assert "font-size: 1.25em" in html
        assert "font-size: 85%" in html

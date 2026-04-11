"""Tests for preview typography settings."""

import pytest

from markdown_editor.markdown6.settings import get_settings, DEFAULT_SETTINGS


class TestTypographyDefaults:
    """Verify that default typography settings produce the same CSS as
    the previously hardcoded values."""

    def test_font_families_default_to_empty(self):
        """Empty string means 'use the built-in CSS font stack'."""
        s = get_settings()
        assert s.get("preview.body_font_family") == ""
        assert s.get("preview.code_font_family") == ""
        assert s.get("preview.heading_font_family") == ""

    def test_heading_sizes_match_hardcoded(self):
        s = get_settings()
        assert s.get("preview.h1_size") == 2.0
        assert s.get("preview.h1_size_unit") == "em"
        assert s.get("preview.h2_size") == 1.5
        assert s.get("preview.h2_size_unit") == "em"
        assert s.get("preview.h3_size") == 1.25
        assert s.get("preview.h3_size_unit") == "em"

    def test_code_size_matches_hardcoded(self):
        s = get_settings()
        assert s.get("preview.code_size") == 85
        assert s.get("preview.code_size_unit") == "%"

    def test_line_height_default(self):
        assert get_settings().get("preview.line_height") == 1.5


class TestTypographyInHtml:
    """Verify that typography settings are injected into the preview HTML."""

    @pytest.fixture
    def main_window(self, qtbot):
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor

        window = MarkdownEditor()
        qtbot.addWidget(window)
        yield window
        window.close()

    def test_default_html_uses_hardcoded_font_stacks(self, main_window):
        """With empty font settings, the HTML should contain the original
        hardcoded CSS font stacks."""
        html = main_window.get_html_template("<p>test</p>")
        assert "-apple-system" in html
        assert "SFMono-Regular" in html
        assert "font-size: 2.0em" in html  # h1
        assert "font-size: 1.5em" in html  # h2
        assert "font-size: 85%" in html    # code

    def test_custom_body_font_produces_css_with_fallback(self, main_window):
        """Setting a body font should produce '"FontName", sans-serif'."""
        get_settings().set("preview.body_font_family", "Georgia")
        html = main_window.get_html_template("<p>test</p>")
        assert '"Georgia", sans-serif' in html
        # The old hardcoded stack should NOT appear
        assert "-apple-system" not in html

    def test_custom_code_font_produces_css_with_fallback(self, main_window):
        get_settings().set("preview.code_font_family", "Fira Code")
        html = main_window.get_html_template("<p>test</p>")
        assert '"Fira Code", monospace' in html
        assert "SFMono-Regular" not in html

    def test_custom_heading_font_injected(self, main_window):
        get_settings().set("preview.heading_font_family", "Impact")
        html = main_window.get_html_template("<p>test</p>")
        assert '"Impact", sans-serif' in html

    def test_empty_heading_font_no_font_family_in_headings(self, main_window):
        """When heading font is empty, heading CSS should not have
        a separate font-family declaration."""
        get_settings().set("preview.heading_font_family", "")
        html = main_window.get_html_template("<p>test</p>")
        # Find the h1 rule and check it doesn't have font-family
        h1_section = html.split("h1 {")[1].split("}")[0]
        assert "font-family" not in h1_section

    def test_heading_size_px_unit(self, main_window):
        get_settings().set("preview.h1_size", 32)
        get_settings().set("preview.h1_size_unit", "px")
        html = main_window.get_html_template("<p>test</p>")
        assert "font-size: 32px" in html

    def test_code_size_px_unit(self, main_window):
        get_settings().set("preview.code_size", 14)
        get_settings().set("preview.code_size_unit", "px")
        html = main_window.get_html_template("<p>test</p>")
        assert "font-size: 14px" in html

    def test_line_height_injected(self, main_window):
        get_settings().set("preview.line_height", 2.0)
        html = main_window.get_html_template("<p>test</p>")
        assert "line-height: 2.0" in html

    def test_qtextbrowser_uses_settings_too(self, main_window):
        get_settings().set("preview.body_font_family", "Courier")
        html = main_window.get_html_template("<p>test</p>", for_qtextbrowser=True)
        assert '"Courier", sans-serif' in html

    def test_fresh_defaults_match_original_css(self, main_window):
        """Critical: with all defaults, the generated CSS must be
        byte-for-byte identical to the original hardcoded version for
        body, h1-h3, code, and pre font-family and font-size."""
        html = main_window.get_html_template("<p>test</p>")
        # These exact strings were in the original hardcoded CSS
        assert 'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif' in html
        assert 'font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace' in html
        assert "font-size: 2.0em" in html
        assert "font-size: 1.5em" in html
        assert "font-size: 1.25em" in html
        assert "font-size: 85%" in html

"""Tests for mermaid and graphviz diagram rendering in the markdown pipeline.

Verifies that fenced code blocks with mermaid/dot/graphviz language tags
are converted to the appropriate HTML elements for rendering.
"""

import markdown
from unittest.mock import patch, MagicMock

from markdown_editor.markdown6.markdown_extensions import (
    MermaidExtension,
    MermaidPreprocessor,
    GraphvizExtension,
    GraphvizPreprocessor,
)


class TestMermaidServerSideRendering:
    """Test mermaid blocks when mmdc is available (server-side SVG rendering)."""

    def _make_md(self):
        return markdown.Markdown(extensions=[MermaidExtension()])

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>diagram</svg>", None))
    def test_basic_mermaid_rendered_to_svg(self, mock_render, mock_has, mock_cached):
        """With mmdc available and cached, mermaid blocks should render to SVG."""
        md = self._make_md()
        source = "# Title\n\n```mermaid\ngraph TD\n    A --> B\n```\n"
        result = md.convert(source)
        assert 'class="mermaid-diagram"' in result
        assert "<svg>diagram</svg>" in result
        assert "```mermaid" not in result
        mock_render.assert_called_once()
        call_args = mock_render.call_args[0][0]
        assert "graph TD" in call_args
        assert "A --> B" in call_args

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>flow</svg>", None))
    def test_flowchart_with_subgraphs(self, mock_render, mock_has, mock_cached):
        """Complex flowcharts with subgraphs should render."""
        md = self._make_md()
        source = (
            "```mermaid\n"
            "flowchart TD\n"
            "    subgraph Clients\n"
            "        SW[swappweb]\n"
            "        WS[website]\n"
            "    end\n"
            "    SW --> WS\n"
            "```\n"
        )
        result = md.convert(source)
        assert 'class="mermaid-diagram"' in result
        call_args = mock_render.call_args[0][0]
        assert "subgraph Clients" in call_args

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>seq</svg>", None))
    def test_sequence_diagram(self, mock_render, mock_has, mock_cached):
        md = self._make_md()
        source = (
            "```mermaid\n"
            "sequenceDiagram\n"
            "    Alice->>Bob: Hello\n"
            "    Bob-->>Alice: Hi\n"
            "```\n"
        )
        result = md.convert(source)
        assert 'class="mermaid-diagram"' in result

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>d</svg>", None))
    def test_multiple_mermaid_blocks(self, mock_render, mock_has, mock_cached):
        """Multiple mermaid blocks in one document should all render."""
        md = self._make_md()
        source = (
            "```mermaid\ngraph LR\n    A --> B\n```\n\n"
            "Some text between.\n\n"
            "```mermaid\ngraph TD\n    C --> D\n```\n"
        )
        result = md.convert(source)
        assert result.count('class="mermaid-diagram"') == 2
        assert mock_render.call_count == 2

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid")
    def test_render_error_shows_error_html(self, mock_render, mock_has, mock_cached):
        """Render errors should show error HTML."""
        mock_render.return_value = ('<div class="mermaid-error">Parse error</div>', "Parse error")
        md = self._make_md()
        source = "```mermaid\ninvalid diagram\n```\n"
        result = md.convert(source)
        assert "mermaid-error" in result
        assert "Parse error" in result

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>ok</svg>", None))
    def test_dark_mode_passed_to_renderer(self, mock_render, mock_has, mock_cached):
        """dark_mode attribute should be passed through to render_mermaid."""
        md = self._make_md()
        md.mermaid_dark_mode = True
        source = "```mermaid\ngraph TD\n    A --> B\n```\n"
        md.convert(source)
        assert mock_render.call_args[0][1] is True  # dark_mode arg

    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    def test_non_mermaid_code_block_untouched(self, mock_has):
        """A ```python block should NOT be converted to mermaid."""
        md = self._make_md()
        source = "```python\nprint('hello')\n```\n"
        result = md.convert(source)
        assert "mermaid" not in result


class TestMermaidClientSideFallback:
    """Test mermaid blocks when mmdc is NOT available (JS fallback)."""

    def _make_md(self):
        return markdown.Markdown(extensions=[MermaidExtension()])

    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=False)
    def test_fallback_produces_mermaid_div(self, mock_has):
        """Without mmdc, should produce a <div class="mermaid"> for JS rendering."""
        md = self._make_md()
        source = "```mermaid\ngraph TD\n    A --> B\n```\n"
        result = md.convert(source)
        assert '<div class="mermaid">' in result
        assert "graph TD" in result
        assert "A --> B" in result

    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=False)
    def test_fallback_multiple_blocks(self, mock_has):
        md = self._make_md()
        source = (
            "```mermaid\ngraph LR\n    A --> B\n```\n\n"
            "```mermaid\ngraph TD\n    C --> D\n```\n"
        )
        result = md.convert(source)
        assert result.count('class="mermaid"') == 2

    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=False)
    def test_mixed_with_text(self, mock_has):
        md = self._make_md()
        source = (
            "# Heading\n\nSome paragraph.\n\n"
            "```mermaid\ngraph TD\n    A --> B\n```\n\n"
            "More text after.\n"
        )
        result = md.convert(source)
        assert '<div class="mermaid">' in result
        assert "More text after" in result


class TestMermaidService:
    """Test the mermaid_service module directly."""

    @patch("shutil.which", return_value="/usr/bin/mmdc")
    def test_has_mermaid_true(self, mock_which):
        from markdown_editor.markdown6 import mermaid_service
        assert mermaid_service.has_mermaid() is True
        mock_which.assert_called_with("mmdc")

    @patch("shutil.which", return_value=None)
    def test_has_mermaid_false(self, mock_which):
        from markdown_editor.markdown6 import mermaid_service
        assert mermaid_service.has_mermaid() is False

    def test_format_error(self):
        from markdown_editor.markdown6.mermaid_service import _format_error
        result = _format_error("graph TD\n    A --> B", "some error")
        assert "mermaid-error" in result
        assert "some error" in result
        assert "graph TD" in result

    def test_format_error_escapes_html(self):
        from markdown_editor.markdown6.mermaid_service import _format_error
        result = _format_error("<script>alert(1)</script>", "err <b>bold</b>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&lt;b&gt;" in result

    def test_get_mermaid_css_light(self):
        from markdown_editor.markdown6.mermaid_service import get_mermaid_css
        css = get_mermaid_css(dark_mode=False)
        assert ".mermaid-diagram" in css
        assert ".mermaid-error" in css

    def test_get_mermaid_css_dark(self):
        from markdown_editor.markdown6.mermaid_service import get_mermaid_css
        css = get_mermaid_css(dark_mode=True)
        assert ".mermaid-diagram" in css
        assert "#f85149" in css  # dark mode error color

    def test_get_mermaid_js_fallback(self):
        from markdown_editor.markdown6.mermaid_service import get_mermaid_js
        js = get_mermaid_js()
        assert "mermaid" in js
        assert "cdn.jsdelivr.net" in js

    @patch("markdown_editor.markdown6.tool_paths.get_mmdc_path", return_value=None)
    def test_render_without_mmdc(self, mock_path):
        from markdown_editor.markdown6.mermaid_service import render_mermaid, clear_cache
        clear_cache()
        svg, error = render_mermaid("graph TD\n    A --> B")
        assert error is not None
        assert "mmdc not installed" in error
        assert "mermaid-error" in svg

    @patch("markdown_editor.markdown6.mermaid_service._render_mermaid_impl")
    def test_caching(self, mock_impl):
        """Second call with same source should use cache."""
        from markdown_editor.markdown6.mermaid_service import render_mermaid, clear_cache
        clear_cache()
        mock_impl.return_value = ("<svg>cached</svg>", None)
        result1 = render_mermaid("graph TD\n    A --> B")
        result2 = render_mermaid("graph TD\n    A --> B")
        assert result1 == result2
        assert mock_impl.call_count == 1  # Only called once, second was cached


class TestGraphvizPreprocessor:
    """Test that dot/graphviz code blocks are converted to diagram elements."""

    def _make_md(self):
        return markdown.Markdown(extensions=[GraphvizExtension()])

    @patch("markdown_editor.markdown6.graphviz_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.render_dot", return_value=("<svg>test</svg>", None))
    def test_dot_block_rendered_as_svg(self, mock_render, mock_has, mock_cached):
        """A ```dot block with graphviz available should render to SVG."""
        md = self._make_md()
        source = '```dot\ndigraph G {\n    A -> B\n}\n```\n'
        result = md.convert(source)
        assert 'class="graphviz-diagram"' in result
        assert "<svg>test</svg>" in result
        mock_render.assert_called_once()
        call_args = mock_render.call_args[0][0]
        assert "digraph G" in call_args

    @patch("markdown_editor.markdown6.graphviz_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.render_dot", return_value=("<svg>test</svg>", None))
    def test_graphviz_language_tag(self, mock_render, mock_has, mock_cached):
        """```graphviz should work the same as ```dot."""
        md = self._make_md()
        source = '```graphviz\ndigraph G {\n    A -> B\n}\n```\n'
        result = md.convert(source)
        assert 'class="graphviz-diagram"' in result

    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=False)
    def test_dot_block_without_graphviz_falls_back(self, mock_has):
        """Without graphviz installed, should produce a pending div."""
        md = self._make_md()
        source = '```dot\ndigraph G {\n    A -> B\n}\n```\n'
        result = md.convert(source)
        assert "graphviz-pending" in result
        assert "digraph G" in result

    @patch("markdown_editor.markdown6.graphviz_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.render_dot", return_value=("<svg>graph</svg>", None))
    def test_multiple_dot_blocks(self, mock_render, mock_has, mock_cached):
        """Multiple dot blocks should all render."""
        md = self._make_md()
        source = (
            '```dot\ndigraph A {\n    1 -> 2\n}\n```\n\n'
            '```dot\ndigraph B {\n    3 -> 4\n}\n```\n'
        )
        result = md.convert(source)
        assert result.count('class="graphviz-diagram"') == 2

    @patch("markdown_editor.markdown6.graphviz_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.render_dot")
    def test_dot_render_error(self, mock_render, mock_has, mock_cached):
        """Render errors should be passed through."""
        mock_render.return_value = ('<div class="error">Bad syntax</div>', "Bad syntax")
        md = self._make_md()
        source = '```dot\ninvalid dot\n```\n'
        result = md.convert(source)
        assert "error" in result.lower() or "Bad syntax" in result


class TestMermaidAndGraphvizTogether:
    """Test that both extensions work together in the same document."""

    def _make_md(self):
        return markdown.Markdown(extensions=[MermaidExtension(), GraphvizExtension()])

    @patch("markdown_editor.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("markdown_editor.markdown6.mermaid_service.render_mermaid", return_value=("<svg>merm</svg>", None))
    @patch("markdown_editor.markdown6.graphviz_service.is_cached", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=True)
    @patch("markdown_editor.markdown6.graphviz_service.render_dot", return_value=("<svg>dot</svg>", None))
    def test_mixed_document_server_side(self, mock_dot, mock_has_gv, mock_cached_gv, mock_merm, mock_has_mm, mock_cached_mm):
        """Both mermaid and dot blocks should render to SVG when tools available."""
        md = self._make_md()
        source = (
            "# Architecture\n\n"
            "```mermaid\ngraph TD\n    A --> B\n```\n\n"
            "## Details\n\n"
            "```dot\ndigraph G {\n    C -> D\n}\n```\n"
        )
        result = md.convert(source)
        assert 'class="mermaid-diagram"' in result
        assert 'class="graphviz-diagram"' in result
        assert "<svg>merm</svg>" in result
        assert "<svg>dot</svg>" in result

    @patch("markdown_editor.markdown6.mermaid_service.has_mermaid", return_value=False)
    @patch("markdown_editor.markdown6.graphviz_service.has_graphviz", return_value=False)
    def test_mixed_document_fallback(self, mock_has_gv, mock_has_mm):
        """Both should fall back to client-side when tools unavailable."""
        md = self._make_md()
        source = (
            "```mermaid\ngraph TD\n    A --> B\n```\n\n"
            "```dot\ndigraph G {\n    C -> D\n}\n```\n"
        )
        result = md.convert(source)
        assert '<div class="mermaid">' in result
        assert "graphviz-pending" in result

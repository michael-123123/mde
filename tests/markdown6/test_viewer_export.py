"""Tests for the viewer-quality HTML export pipeline."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from markdown_editor.markdown6.viewer_export import (
    create_markdown_pipeline,
    build_export_template,
    viewer_export_html,
    embed_local_images,
    copy_resources_for_project,
    _render_pending_diagrams_sync,
)
from markdown_editor.markdown6 import export_service


# ---------------------------------------------------------------------------
# create_markdown_pipeline
# ---------------------------------------------------------------------------

class TestCreateMarkdownPipeline:

    def test_returns_markdown_instance(self):
        import markdown
        md = create_markdown_pipeline()
        assert isinstance(md, markdown.Markdown)

    def test_has_no_source_line_extension(self):
        md = create_markdown_pipeline()
        pre_names = [name for name in md.preprocessors]
        assert "source_line_pre" not in pre_names

    def test_has_callout_extension(self):
        md = create_markdown_pipeline()
        assert "callout" in md.preprocessors

    def test_has_math_extension(self):
        md = create_markdown_pipeline()
        assert "math_pre" in md.preprocessors

    def test_converts_basic_markdown(self):
        md = create_markdown_pipeline()
        result = md.convert("# Hello\n\nWorld")
        assert "<h1" in result
        assert "Hello" in result


# ---------------------------------------------------------------------------
# build_export_template
# ---------------------------------------------------------------------------

class TestBuildExportTemplate:

    def test_produces_html_document(self):
        html = build_export_template("<p>Hello</p>")
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "<p>Hello</p>" in html

    def test_includes_title(self):
        html = build_export_template("<p>X</p>", title="My Doc")
        assert "<title>My Doc</title>" in html

    def test_no_scroll_sync_js(self):
        html = build_export_template("<p>X</p>")
        assert "scrollToSourceLine" not in html

    def test_no_ctrl_click_js(self):
        html = build_export_template("<p>X</p>")
        assert "ctrl-held" not in html
        assert "open-image://" not in html

    def test_no_data_source_line(self):
        html = build_export_template("<p>X</p>")
        assert "data-source-line" not in html
        assert "data-total-lines" not in html

    def test_has_pygments_css(self):
        html = build_export_template("<p>X</p>")
        assert ".highlight" in html

    def test_has_callout_css(self):
        html = build_export_template("<p>X</p>")
        assert ".callout" in html

    def test_has_task_list_css(self):
        html = build_export_template("<p>X</p>")
        assert ".task-list-item" in html

    def test_dark_mode_class(self):
        html = build_export_template("<p>X</p>", dark_mode=True)
        assert 'class="dark"' in html

    def test_light_mode_class(self):
        html = build_export_template("<p>X</p>", dark_mode=False)
        assert 'class="light"' in html

    def test_print_media_query(self):
        html = build_export_template("<p>X</p>")
        assert "@media print" in html

    def test_max_width_for_export(self):
        html = build_export_template("<p>X</p>")
        assert "max-width: 800px" in html

    def test_escapes_title(self):
        html = build_export_template("<p>X</p>", title="A <script> & B")
        assert "<script>" not in html.split("</title>")[0]
        assert "&amp;" in html


# ---------------------------------------------------------------------------
# viewer_export_html (end-to-end)
# ---------------------------------------------------------------------------

class TestViewerExportHtml:

    def test_basic_conversion(self):
        html = viewer_export_html("# Hello\n\nParagraph")
        assert "<!DOCTYPE html>" in html
        assert "Hello" in html
        assert "Paragraph" in html

    def test_callouts_rendered(self):
        content = "> [!NOTE]\n> This is a note"
        html = viewer_export_html(content)
        assert "callout" in html
        assert "This is a note" in html

    def test_task_lists_rendered(self):
        content = "- [x] Done\n- [ ] Todo"
        html = viewer_export_html(content)
        assert "task-list-item" in html

    def test_code_highlighting(self):
        content = "```python\nprint('hello')\n```"
        html = viewer_export_html(content)
        assert "highlight" in html

    def test_no_cdn_references(self):
        html = viewer_export_html("# Test")
        assert "cdn.jsdelivr.net" not in html

    def test_math_delimiters_present(self):
        """KaTeX bundle should include rendering setup."""
        html = viewer_export_html("$x^2$")
        assert "renderMathInElement" in html


# ---------------------------------------------------------------------------
# export_service backend parameter
# ---------------------------------------------------------------------------

class TestExportServiceBackend:

    def test_basic_backend(self):
        html = export_service.markdown_to_html("# Hello", backend="basic")
        assert "<!DOCTYPE html>" in html
        assert "Hello" in html
        # Basic backend doesn't have callout CSS
        assert ".callout" not in html

    def test_viewer_backend(self):
        html = export_service.markdown_to_html("# Hello", backend="viewer")
        assert "<!DOCTYPE html>" in html
        assert "Hello" in html
        assert ".callout" in html  # Viewer has rich CSS

    def test_viewer_is_default(self):
        html = export_service.markdown_to_html("# Hello")
        assert ".callout" in html

    def test_export_html_basic(self, tmp_path):
        out = tmp_path / "test.html"
        export_service.export_html("# Hello", out, backend="basic")
        content = out.read_text()
        assert "Hello" in content
        assert ".callout" not in content

    def test_export_html_viewer(self, tmp_path):
        out = tmp_path / "test.html"
        export_service.export_html("# Hello", out, backend="viewer")
        content = out.read_text()
        assert "Hello" in content
        assert ".callout" in content


# ---------------------------------------------------------------------------
# Image embedding
# ---------------------------------------------------------------------------

class TestEmbedLocalImages:

    def test_embeds_local_image(self, tmp_path):
        # Create a tiny 1x1 PNG
        import base64
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGNgYPgPAAEDAQAIicLsAAAABJRU5ErkJggg=="
        )
        img_path = tmp_path / "test.png"
        img_path.write_bytes(png_data)

        html = '<img src="test.png" alt="test">'
        result = embed_local_images(html, tmp_path)
        assert "data:image/png;base64," in result
        assert 'src="test.png"' not in result

    def test_skips_http_urls(self):
        html = '<img src="https://example.com/img.png">'
        result = embed_local_images(html, Path("/tmp"))
        assert result == html

    def test_skips_data_uris(self):
        html = '<img src="data:image/png;base64,abc">'
        result = embed_local_images(html, Path("/tmp"))
        assert result == html

    def test_skips_missing_files(self, tmp_path):
        html = '<img src="nonexistent.png">'
        result = embed_local_images(html, tmp_path)
        assert result == html


# ---------------------------------------------------------------------------
# Project resource copying
# ---------------------------------------------------------------------------

class TestCopyResourcesForProject:

    def test_copies_image_to_assets(self, tmp_path):
        import base64
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGNgYPgPAAEDAQAIicLsAAAABJRU5ErkJggg=="
        )
        (src_dir / "photo.png").write_bytes(png_data)

        html = '<img src="photo.png">'
        result = copy_resources_for_project(html, src_dir, out_dir)

        assert 'src="assets/photo.png"' in result
        assert (out_dir / "assets" / "photo.png").exists()

    def test_skips_http_urls(self, tmp_path):
        html = '<img src="https://example.com/img.png">'
        result = copy_resources_for_project(html, tmp_path, tmp_path)
        assert result == html

    def test_handles_duplicate_names(self, tmp_path):
        """Different files with the same name don't overwrite each other."""
        src_dir = tmp_path / "src"
        sub1 = src_dir / "a"
        sub2 = src_dir / "b"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        (sub1 / "img.png").write_bytes(b"data1")
        (sub2 / "img.png").write_bytes(b"data2")

        html = '<img src="a/img.png"><img src="b/img.png">'
        result = copy_resources_for_project(html, src_dir, out_dir)

        assert (out_dir / "assets").exists()
        # Both images should be present (possibly with renamed second)
        assets = list((out_dir / "assets").iterdir())
        assert len(assets) == 2


# ---------------------------------------------------------------------------
# Pending diagram rendering
# ---------------------------------------------------------------------------

class TestRenderPendingDiagramsSync:

    def test_replaces_mermaid_placeholder(self):
        html = (
            '<div class="mermaid-diagram" id="diagram-pending-0">'
            '<div class="diagram-loading">Rendering...</div></div>'
        )
        pending = [("mermaid", "graph LR; A-->B", False)]

        with patch("markdown_editor.markdown6.viewer_export.mermaid_service") as mock:
            mock.render_mermaid.return_value = ("<svg>OK</svg>", None)
            result = _render_pending_diagrams_sync(html, pending)

        assert "<svg>OK</svg>" in result
        assert "diagram-pending-0" not in result

    def test_no_pending_returns_unchanged(self):
        html = "<p>Hello</p>"
        result = _render_pending_diagrams_sync(html, [])
        assert result == html

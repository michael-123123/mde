"""Tests for the export service module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from markdown_editor.markdown6.export_service import (
    ExportError,
    _add_formatted_text,
    export_docx,
    export_html,
    export_pdf,
    has_pandoc,
    markdown_to_html,
)


class TestHasPandoc:
    """Tests for pandoc detection."""

    def test_has_pandoc_when_available(self):
        """Test has_pandoc returns True when pandoc exists."""
        with patch("shutil.which", return_value="/usr/bin/pandoc"):
            assert has_pandoc() is True

    def test_has_pandoc_when_unavailable(self):
        """Test has_pandoc returns False when pandoc doesn't exist."""
        with patch("shutil.which", return_value=None):
            assert has_pandoc() is False


class TestMarkdownToHtml:
    """Tests for markdown to HTML conversion."""

    def test_basic_conversion(self):
        """Test basic markdown to HTML conversion."""
        content = "# Hello World"
        html = markdown_to_html(content)
        # markdown library adds id attribute to headings
        assert "<h1" in html and "Hello World</h1>" in html
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html

    def test_title_in_html(self):
        """Test that title appears in HTML head."""
        html = markdown_to_html("content", title="My Document")
        assert "<title>My Document</title>" in html

    def test_default_title(self):
        """Test default title is 'Document'."""
        html = markdown_to_html("content")
        assert "<title>Document</title>" in html

    def test_bold_text(self):
        """Test bold text conversion."""
        html = markdown_to_html("**bold text**")
        assert "<strong>bold text</strong>" in html

    def test_italic_text(self):
        """Test italic text conversion."""
        html = markdown_to_html("*italic text*")
        assert "<em>italic text</em>" in html

    def test_code_text(self):
        """Test inline code conversion."""
        html = markdown_to_html("`code here`")
        assert "<code>code here</code>" in html

    def test_code_block(self):
        """Test code block conversion."""
        html = markdown_to_html("```python\nprint('hello')\n```")
        assert "<code>" in html or "<pre>" in html

    def test_table_conversion(self):
        """Test markdown table conversion."""
        table = """| A | B |
| --- | --- |
| 1 | 2 |"""
        html = markdown_to_html(table)
        # Partial match tolerates `data-source-line` attributes added by
        # the unified renderer's SourceLineExtension (decision D3).
        assert "<table" in html
        assert "<th>" in html
        assert "<td>" in html

    def test_link_conversion(self):
        """Test link conversion."""
        html = markdown_to_html("[link](http://example.com)")
        assert 'href="http://example.com"' in html

    def test_styling_included(self):
        """Test that CSS styling is included."""
        html = markdown_to_html("content")
        assert "<style>" in html
        assert "font-family" in html


class TestExportHtml:
    """Tests for HTML file export."""

    def test_export_creates_file(self, tmp_path):
        """Test that export_html creates the HTML file."""
        output_path = tmp_path / "output.html"
        export_html("# Test", output_path, title="Test Doc")
        assert output_path.exists()

    def test_export_content(self, tmp_path):
        """Test that exported HTML contains the content."""
        output_path = tmp_path / "output.html"
        export_html("# My Heading", output_path)
        content = output_path.read_text()
        # markdown library adds id attribute to headings
        assert "<h1" in content and "My Heading</h1>" in content

    def test_export_with_string_path(self, tmp_path):
        """Test export with string path instead of Path."""
        output_path = str(tmp_path / "output.html")
        export_html("# Test", output_path)
        assert Path(output_path).exists()

    def test_export_encoding_utf8(self, tmp_path):
        """Test that export uses UTF-8 encoding."""
        output_path = tmp_path / "output.html"
        export_html("# Test with ñ and 中文", output_path)
        content = output_path.read_text(encoding="utf-8")
        assert "ñ" in content
        assert "中文" in content


class TestExportPdf:
    """Tests for PDF export."""

    def test_export_pdf_without_pandoc(self, tmp_path):
        """Test PDF export without pandoc uses weasyprint."""
        output_path = tmp_path / "output.pdf"

        # Mock weasyprint import
        mock_html = MagicMock()
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = mock_html

        with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
            with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=False):
                # Import inside to get the patched version
                from markdown_editor.markdown6 import export_service as es

                # Re-patch the weasyprint import inside the function
                with patch.object(es, "_export_pdf_weasyprint") as mock_export:
                    es.export_pdf("# Test", output_path)
                    mock_export.assert_called_once()

    def test_export_pdf_with_pandoc_flag(self, tmp_path):
        """Test PDF export with pandoc flag uses pandoc when available."""
        output_path = tmp_path / "output.pdf"

        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=True):
            with patch("markdown_editor.markdown6.export_service._export_pdf_pandoc") as mock_pandoc:
                export_pdf("# Test", output_path, use_pandoc=True)
                mock_pandoc.assert_called_once()

    def test_export_pdf_falls_back_when_no_pandoc(self, tmp_path):
        """Test PDF export falls back when pandoc unavailable."""
        output_path = tmp_path / "output.pdf"

        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=False):
            with patch("markdown_editor.markdown6.export_service._export_pdf_weasyprint") as mock_weasy:
                export_pdf("# Test", output_path, use_pandoc=True)
                mock_weasy.assert_called_once()


class TestExportDocx:
    """Tests for DOCX export."""

    def test_export_docx_without_pandoc(self, tmp_path):
        """Test DOCX export without pandoc uses python-docx."""
        output_path = tmp_path / "output.docx"

        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=False):
            with patch("markdown_editor.markdown6.export_service._export_docx_python") as mock_python:
                export_docx("# Test", output_path)
                mock_python.assert_called_once()

    def test_export_docx_with_pandoc_flag(self, tmp_path):
        """Test DOCX export with pandoc flag uses pandoc when available."""
        output_path = tmp_path / "output.docx"

        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=True):
            with patch("markdown_editor.markdown6.export_service._export_docx_pandoc") as mock_pandoc:
                export_docx("# Test", output_path, use_pandoc=True)
                mock_pandoc.assert_called_once()


class TestExportPandoc:
    """Tests for pandoc-based export."""

    def test_pandoc_pdf_error_handling(self, tmp_path):
        """Test that pandoc errors are raised as ExportError."""
        from markdown_editor.markdown6.export_service import _export_pdf_pandoc

        output_path = tmp_path / "output.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Pandoc error message"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(ExportError) as exc_info:
                _export_pdf_pandoc("# Test", output_path)
            assert "Pandoc error" in str(exc_info.value)

    def test_pandoc_docx_error_handling(self, tmp_path):
        """Test that pandoc DOCX errors are raised as ExportError."""
        from markdown_editor.markdown6.export_service import (
            _export_docx_pandoc,
        )

        output_path = tmp_path / "output.docx"
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Pandoc error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(ExportError):
                _export_docx_pandoc("# Test", output_path)

    def test_pandoc_cleans_up_temp_file(self, tmp_path):
        """Test that temp file is cleaned up after pandoc export."""
        from markdown_editor.markdown6.export_service import _export_pdf_pandoc

        output_path = tmp_path / "output.pdf"
        mock_result = MagicMock()
        mock_result.returncode = 0

        temp_files_created = []

        def capture_run(cmd, **kwargs):
            # Capture the temp file path from the command
            temp_files_created.append(cmd[1])
            return mock_result

        with patch("subprocess.run", side_effect=capture_run):
            _export_pdf_pandoc("# Test", output_path)

        # Temp file should be tracked for cleanup at exit
        if temp_files_created:
            from markdown_editor.markdown6.temp_files import _tracked
            assert Path(temp_files_created[0]) in _tracked


class TestExportPythonDocx:
    """Tests for python-docx based export."""

    def test_docx_python_missing_dependency(self, tmp_path):
        """Test that missing python-docx raises ExportError."""
        from markdown_editor.markdown6.export_service import (
            _export_docx_python,
        )

        output_path = tmp_path / "output.docx"

        # Simulate import error
        with patch.dict("sys.modules", {"docx": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'docx'")):
                with pytest.raises(ExportError) as exc_info:
                    _export_docx_python("# Test", output_path, "Title")
                assert "python-docx" in str(exc_info.value)


class TestExportWeasyprint:
    """Tests for weasyprint-based export."""

    def test_weasyprint_missing_dependency(self, tmp_path):
        """Test that missing weasyprint raises ExportError."""
        output_path = tmp_path / "output.pdf"

        # Remove weasyprint from sys.modules if present, then mock import
        import sys
        weasyprint_backup = sys.modules.pop("weasyprint", None)
        try:
            with patch.dict("sys.modules", {"weasyprint": None}):
                # Re-import the function to get fresh import attempt
                import importlib

                import markdown_editor.markdown6.export_service as es
                importlib.reload(es)

                # The function should raise ExportError when weasyprint can't be imported
                # Use the ExportError from the reloaded module
                with pytest.raises(es.ExportError) as exc_info:
                    es._export_pdf_weasyprint("# Test", output_path, "Title")
                assert "weasyprint" in str(exc_info.value)
        finally:
            # Restore weasyprint if it was present
            if weasyprint_backup is not None:
                sys.modules["weasyprint"] = weasyprint_backup
            # Reload module to restore normal state
            import importlib

            import markdown_editor.markdown6.export_service as es
            importlib.reload(es)


class TestAddFormattedText:
    """Tests for the _add_formatted_text helper."""

    def test_plain_text(self):
        """Test adding plain text."""
        mock_para = MagicMock()
        _add_formatted_text(mock_para, "plain text")
        mock_para.add_run.assert_called()

    def test_bold_text(self):
        """Test adding bold text."""
        mock_para = MagicMock()
        mock_run = MagicMock()
        mock_para.add_run.return_value = mock_run

        _add_formatted_text(mock_para, "**bold**")
        # Should have called add_run and set bold
        assert mock_para.add_run.called

    def test_italic_text(self):
        """Test adding italic text."""
        mock_para = MagicMock()
        mock_run = MagicMock()
        mock_para.add_run.return_value = mock_run

        _add_formatted_text(mock_para, "*italic*")
        assert mock_para.add_run.called

    def test_code_text(self):
        """Test adding inline code text."""
        mock_para = MagicMock()
        mock_run = MagicMock()
        mock_para.add_run.return_value = mock_run

        _add_formatted_text(mock_para, "`code`")
        assert mock_para.add_run.called

    def test_mixed_formatting(self):
        """Test mixed formatting in text."""
        mock_para = MagicMock()
        mock_run = MagicMock()
        mock_para.add_run.return_value = mock_run

        _add_formatted_text(mock_para, "plain **bold** and *italic*")
        # Should be called multiple times for different parts
        assert mock_para.add_run.call_count >= 3


class TestExportError:
    """Tests for ExportError exception."""

    def test_export_error_is_exception(self):
        """Test that ExportError is an Exception."""
        assert issubclass(ExportError, Exception)

    def test_export_error_message(self):
        """Test ExportError preserves message."""
        error = ExportError("Test error message")
        assert str(error) == "Test error message"

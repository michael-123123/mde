"""Export service for converting Markdown to various formats.

Supports PDF, DOCX, and HTML export with pandoc (if available) or Python fallbacks.
"""

import shutil
import subprocess
from pathlib import Path

import markdown as md


def has_pandoc() -> bool:
    """Check if pandoc is available on the system."""
    from markdown_editor.markdown6.tool_paths import has_pandoc as _has_pandoc
    return _has_pandoc()


def markdown_to_html(
    content: str,
    title: str = "Document",
    backend: str = "viewer",
    **kwargs,
) -> str:
    """Convert markdown content to a complete HTML document.

    Args:
        content: Raw markdown text.
        title: Document title for the <title> tag.
        backend: "viewer" (rich, offline-capable) or "basic" (simple).
        **kwargs: Passed to viewer_export_html when backend="viewer".
            Useful keys: dark_mode, font_size, base_path, logseq_mode.
    """
    if backend == "viewer":
        from markdown_editor.markdown6.viewer_export import viewer_export_html
        return viewer_export_html(content, title=title, **kwargs)

    # Basic backend — original minimal pipeline
    html_content = md.markdown(
        content,
        extensions=["extra", "codehilite", "tables", "toc"]
    )

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }}
        pre {{ background: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }}
        code {{ font-family: monospace; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f6f8fa; }}
        blockquote {{ border-left: 4px solid #ddd; margin: 0; padding-left: 16px; color: #666; }}
        img {{ max-width: 100%; }}
        h1, h2, h3, h4, h5, h6 {{ margin-top: 1.5em; margin-bottom: 0.5em; }}
        @media print {{
            body {{ max-width: none; }}
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""


def export_html(
    content: str,
    output_path: str | Path,
    title: str = "Document",
    backend: str = "viewer",
    single_file: bool = True,
    base_path: Path | None = None,
    output_dir: Path | None = None,
    **kwargs,
) -> None:
    """Export markdown to HTML file.

    Args:
        content: Raw markdown text.
        output_path: Path to write the HTML file.
        title: Document title.
        backend: "viewer" or "basic".
        single_file: If True and backend="viewer", embed images as base64.
        base_path: Directory for resolving relative image paths.
        output_dir: For project export — copy resources here instead of embedding.
        **kwargs: Passed to markdown_to_html (e.g. dark_mode, font_size).
    """
    html = markdown_to_html(content, title, backend=backend, base_path=base_path, **kwargs)

    if backend == "viewer" and base_path:
        from markdown_editor.markdown6.viewer_export import (
            embed_local_images,
            copy_resources_for_project,
        )
        if single_file:
            html = embed_local_images(html, base_path)
        elif output_dir:
            html = copy_resources_for_project(html, base_path, output_dir)

    Path(output_path).write_text(html, encoding="utf-8")


def export_pdf(
    content: str,
    output_path: str | Path,
    title: str = "Document",
    use_pandoc: bool = False,
) -> None:
    """Export markdown to PDF.

    Args:
        content: Markdown content to export
        output_path: Path to save the PDF
        title: Document title
        use_pandoc: If True and pandoc is available, use pandoc+xelatex
    """
    if use_pandoc and has_pandoc():
        _export_pdf_pandoc(content, output_path)
    else:
        _export_pdf_weasyprint(content, output_path, title)


def export_docx(
    content: str,
    output_path: str | Path,
    title: str = "Document",
    use_pandoc: bool = False,
) -> None:
    """Export markdown to DOCX.

    Args:
        content: Markdown content to export
        output_path: Path to save the DOCX
        title: Document title
        use_pandoc: If True and pandoc is available, use pandoc
    """
    if use_pandoc and has_pandoc():
        _export_docx_pandoc(content, output_path)
    else:
        _export_docx_python(content, output_path, title)


def _export_pdf_pandoc(content: str, output_path: str | Path) -> None:
    """Export to PDF using pandoc."""
    from markdown_editor.markdown6.tool_paths import get_pandoc_path
    from markdown_editor.markdown6.temp_files import create_temp_file

    temp_path = create_temp_file(suffix=".md", content=content)

    pandoc = get_pandoc_path() or "pandoc"
    cmd = [pandoc, str(temp_path), "-o", str(output_path), "--pdf-engine=xelatex"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise ExportError(f"Pandoc error: {result.stderr or 'Unknown error'}")


def _export_pdf_weasyprint(content: str, output_path: str | Path, title: str) -> None:
    """Export to PDF using weasyprint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise ExportError(
            "PDF export requires either pandoc or weasyprint.\n"
            "Install weasyprint with: pip install weasyprint"
        )

    html = markdown_to_html(content, title)
    HTML(string=html).write_pdf(str(output_path))


def _export_docx_pandoc(content: str, output_path: str | Path) -> None:
    """Export to DOCX using pandoc."""
    from markdown_editor.markdown6.tool_paths import get_pandoc_path
    from markdown_editor.markdown6.temp_files import create_temp_file

    temp_path = create_temp_file(suffix=".md", content=content)

    pandoc = get_pandoc_path() or "pandoc"
    cmd = [pandoc, str(temp_path), "-o", str(output_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise ExportError(f"Pandoc error: {result.stderr or 'Unknown error'}")


def _export_docx_python(content: str, output_path: str | Path, title: str) -> None:
    """Export to DOCX using python-docx."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise ExportError(
            "DOCX export requires either pandoc or python-docx.\n"
            "Install python-docx with: pip install python-docx"
        )

    doc = Document()

    # Parse markdown and convert to docx
    lines = content.split('\n')
    i = 0
    in_code_block = False
    code_block_content = []

    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.startswith('```'):
            if in_code_block:
                # End code block
                code_text = '\n'.join(code_block_content)
                p = doc.add_paragraph()
                run = p.add_run(code_text)
                run.font.name = 'Courier New'
                run.font.size = Pt(10)
                p.paragraph_format.left_indent = Inches(0.5)
                code_block_content = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_block_content.append(line)
            i += 1
            continue

        # Headings
        if line.startswith('#'):
            level = 0
            for char in line:
                if char == '#':
                    level += 1
                else:
                    break
            text = line[level:].strip()
            if level <= 9:
                doc.add_heading(text, level=min(level, 9))
            i += 1
            continue

        # Horizontal rule
        if line.strip() in ('---', '***', '___'):
            doc.add_paragraph('─' * 50)
            i += 1
            continue

        # Empty lines
        if not line.strip():
            i += 1
            continue

        # Regular paragraph - collect consecutive non-empty lines
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].startswith('```'):
            para_lines.append(lines[i])
            i += 1

        para_text = ' '.join(para_lines)

        # Basic inline formatting
        p = doc.add_paragraph()
        _add_formatted_text(p, para_text)

    doc.save(str(output_path))


def _add_formatted_text(paragraph, text: str) -> None:
    """Add text to paragraph with basic markdown formatting."""
    import re

    # Simple pattern matching for bold, italic, code
    # This is simplified - full markdown parsing would be more complex
    parts = re.split(r'(\*\*.*?\*\*|\*.*?\*|`.*?`)', text)

    for part in parts:
        if not part:
            continue

        if part.startswith('**') and part.endswith('**'):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith('*') and part.endswith('*'):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith('`') and part.endswith('`'):
            run = paragraph.add_run(part[1:-1])
            run.font.name = 'Courier New'
        else:
            paragraph.add_run(part)


class ExportError(Exception):
    """Raised when an export operation fails."""
    pass

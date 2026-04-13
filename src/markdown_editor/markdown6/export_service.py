"""Export service for converting Markdown to various formats.

Supports PDF, DOCX, and HTML export with pandoc (if available) or Python fallbacks.
"""

import subprocess
from pathlib import Path

import markdown as md

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)


def has_pandoc() -> bool:
    """Check if pandoc is available on the system."""
    from markdown_editor.markdown6.tool_paths import has_pandoc as _has_pandoc
    return _has_pandoc()


def markdown_to_html(content: str, title: str = "Document") -> str:
    """Convert markdown content to a complete HTML document."""
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


def export_html(content: str, output_path: str | Path, title: str = "Document") -> None:
    """Export markdown to HTML file."""
    html = markdown_to_html(content, title)
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
    from markdown_editor.markdown6.temp_files import create_temp_file
    from markdown_editor.markdown6.tool_paths import get_pandoc_path

    temp_path = create_temp_file(suffix=".md", content=content)

    pandoc = get_pandoc_path() or "pandoc"
    cmd = [pandoc, str(temp_path), "-o", str(output_path), "--pdf-engine=xelatex"]
    logger.info(f"Running pandoc PDF export: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"Pandoc PDF export failed (rc={result.returncode}): {result.stderr}")
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
    logger.info(f"Exporting PDF via weasyprint to {output_path}")
    HTML(string=html).write_pdf(str(output_path))


def _export_docx_pandoc(content: str, output_path: str | Path) -> None:
    """Export to DOCX using pandoc."""
    from markdown_editor.markdown6.temp_files import create_temp_file
    from markdown_editor.markdown6.tool_paths import get_pandoc_path

    temp_path = create_temp_file(suffix=".md", content=content)

    pandoc = get_pandoc_path() or "pandoc"
    cmd = [pandoc, str(temp_path), "-o", str(output_path)]
    logger.info(f"Running pandoc DOCX export: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"Pandoc DOCX export failed (rc={result.returncode}): {result.stderr}")
        raise ExportError(f"Pandoc error: {result.stderr or 'Unknown error'}")


def _export_docx_python(content: str, output_path: str | Path, title: str) -> None:
    """Export to DOCX using python-docx."""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
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

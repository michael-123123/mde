"""Standalone viewer-quality HTML export.

Produces the same rich output as the live preview but offline-capable:
all JS/CSS inlined, no CDN dependencies. No Qt dependency.
"""

import base64
import html as html_mod
import mimetypes
import re
import shutil
from pathlib import Path

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension
from pygments.formatters import HtmlFormatter

from markdown_editor.markdown6.markdown_extensions import (
    BreaklessListExtension,
    CalloutExtension,
    GraphvizExtension,
    LogseqExtension,
    MathExtension,
    MermaidExtension,
    TaskListExtension,
    WikiLinkExtension,
    get_callout_css,
    get_mermaid_css,
    get_tasklist_css,
)
from markdown_editor.markdown6 import graphviz_service, mermaid_service


def create_markdown_pipeline(
    dark_mode: bool = False,
    base_path: Path | None = None,
    logseq_mode: bool = False,
) -> markdown.Markdown:
    """Create a Markdown instance with the full viewer extension set.

    Same as MarkdownEditor._init_markdown() but without SourceLineExtension
    (which is only for editor scroll sync).
    """
    md = markdown.Markdown(
        extensions=[
            "extra",
            LogseqExtension(),
            BreaklessListExtension(),
            FencedCodeExtension(),
            CodeHiliteExtension(css_class="highlight", guess_lang=True),
            TableExtension(),
            TocExtension(),
            CalloutExtension(),
            WikiLinkExtension(),
            MathExtension(),
            MermaidExtension(),
            GraphvizExtension(),
            TaskListExtension(),
        ]
    )
    md.graphviz_dark_mode = dark_mode
    md.graphviz_base_path = str(base_path) if base_path else None
    md.mermaid_dark_mode = dark_mode
    md.logseq_mode = logseq_mode
    md._pending_diagrams = []
    return md


def _render_pending_diagrams_sync(html_content: str, pending: list) -> str:
    """Render all pending diagrams synchronously and replace placeholders."""
    import json

    for idx, (kind, source, dark_mode) in enumerate(pending):
        placeholder_id = f'id="diagram-pending-{idx}"'
        if placeholder_id not in html_content:
            continue

        if kind == "mermaid":
            svg, error = mermaid_service.render_mermaid(source, dark_mode)
        elif kind == "graphviz":
            svg, error = graphviz_service.render_dot(source, dark_mode)
        else:
            continue

        if error:
            replacement = svg  # error HTML
        else:
            escaped_src = html_mod.escape(source).replace('"', '&quot;')
            tag = "mermaid-diagram" if kind == "mermaid" else "graphviz-diagram"
            replacement = f'<div class="{tag}" data-source="{escaped_src}">{svg}</div>'

        # Replace the entire placeholder div
        pattern = re.compile(
            rf'<div[^>]*{re.escape(placeholder_id)}[^>]*>.*?</div>\s*</div>',
            re.DOTALL,
        )
        html_content = pattern.sub(replacement, html_content, count=1)

    return html_content


def _get_theme_vars(dark_mode: bool) -> dict:
    """Return CSS color variables for the given theme."""
    if dark_mode:
        return {
            "bg_color": "#1e1e1e",
            "text_color": "#d4d4d4",
            "heading_border": "#333",
            "code_bg": "#2d2d2d",
            "blockquote_color": "#888",
            "link_color": "#4ec9b0",
            "pygments_style": "monokai",
            "body_class": "dark",
        }
    return {
        "bg_color": "#ffffff",
        "text_color": "#24292e",
        "heading_border": "#eaecef",
        "code_bg": "#f6f8fa",
        "blockquote_color": "#6a737d",
        "link_color": "#0366d6",
        "pygments_style": "github-dark",
        "body_class": "light",
    }


def build_export_template(
    content: str,
    title: str = "Document",
    dark_mode: bool = False,
    font_size: int = 14,
) -> str:
    """Build a self-contained HTML document from rendered markdown content.

    Same CSS as the live preview template but without editor-specific JS
    (scroll sync, Ctrl+click handlers). External assets are inlined for
    offline use.
    """
    from markdown_editor.markdown6 import asset_cache

    t = _get_theme_vars(dark_mode)
    bg_color = t["bg_color"]
    text_color = t["text_color"]
    heading_border = t["heading_border"]
    code_bg = t["code_bg"]
    blockquote_color = t["blockquote_color"]
    link_color = t["link_color"]
    body_class = t["body_class"]

    formatter = HtmlFormatter(style=t["pygments_style"], cssclass="highlight")
    pygments_css = formatter.get_style_defs(".highlight")
    callout_css = get_callout_css(dark_mode)
    tasklist_css = get_tasklist_css(dark_mode)
    graphviz_css = graphviz_service.get_graphviz_css(dark_mode)
    mermaid_css = get_mermaid_css(dark_mode)

    # Inline KaTeX for offline math rendering
    math_block = asset_cache.get_katex_bundle()

    # Conditionally inline diagram JS only if the content uses them
    mermaid_block = ""
    if 'class="mermaid"' in content and not mermaid_service.has_mermaid():
        mermaid_block = asset_cache.get_mermaid_js_inline()

    graphviz_block = ""
    if 'class="graphviz-pending"' in content and not graphviz_service.has_graphviz():
        graphviz_block = asset_cache.get_viz_js_inline()

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{html_mod.escape(title)}</title>
    {math_block}
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: {font_size}px;
            line-height: 1.5;
            color: {text_color};
            background-color: {bg_color};
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        * {{
            box-sizing: border-box;
        }}
        h1 {{
            font-size: 2em;
            font-weight: 600;
            border-bottom: 1px solid {heading_border};
            padding-bottom: 0.3em;
            margin-top: 24px;
            margin-bottom: 16px;
        }}
        h2 {{
            font-size: 1.5em;
            font-weight: 600;
            border-bottom: 1px solid {heading_border};
            padding-bottom: 0.3em;
            margin-top: 24px;
            margin-bottom: 16px;
        }}
        h3 {{ font-size: 1.25em; font-weight: 600; margin-top: 24px; margin-bottom: 16px; }}
        h4, h5, h6 {{ font-weight: 600; margin-top: 24px; margin-bottom: 16px; }}
        p {{ margin-top: 0; margin-bottom: 16px; }}
        code {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            font-size: 85%;
            background-color: {code_bg};
            padding: 0.2em 0.4em;
            border-radius: 3px;
        }}
        pre {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            font-size: 85%;
            background-color: {code_bg};
            padding: 16px;
            overflow: auto;
            border-radius: 6px;
            line-height: 1.2;
            margin: 0 0 16px 0;
            white-space: pre;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            font-size: 100%;
            line-height: inherit;
            display: block;
        }}
        .highlight {{
            background-color: {code_bg};
            padding: 16px;
            border-radius: 6px;
            overflow: auto;
            margin-bottom: 16px;
            line-height: 1.2;
        }}
        .highlight pre {{
            margin: 0;
            padding: 0;
            background-color: transparent;
            line-height: 1.2;
        }}
        .highlight code {{
            line-height: 1.2;
        }}
        pre *, .highlight * {{
            margin: 0;
            padding: 0;
            line-height: 1.2;
        }}
        pre span, .highlight span {{
            display: inline;
        }}
        .codehilite {{
            background-color: {code_bg};
            padding: 16px;
            border-radius: 6px;
            overflow: auto;
            margin-bottom: 16px;
        }}
        .codehilite pre {{
            margin: 0;
            padding: 0;
            background-color: transparent;
            line-height: 1.2;
        }}
        blockquote {{
            margin: 0;
            padding: 0 1em;
            color: {blockquote_color};
            border-left: 0.25em solid {heading_border};
        }}
        ul, ol {{
            display: block;
            padding-left: 2em;
            margin-top: 0;
            margin-bottom: 16px;
            list-style-position: outside;
        }}
        ul {{ list-style-type: disc; }}
        ol {{ list-style-type: decimal; }}
        li {{
            display: list-item;
            margin-top: 0.25em;
        }}
        table {{ border-collapse: collapse; margin-top: 0; margin-bottom: 16px; width: 100%; }}
        th, td {{ padding: 6px 13px; border: 1px solid {heading_border}; }}
        th {{ font-weight: 600; background-color: {code_bg}; }}
        hr {{ height: 0.25em; padding: 0; margin: 24px 0; background-color: {heading_border}; border: 0; }}
        a {{ color: {link_color}; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        img {{ max-width: 100%; box-sizing: border-box; }}
        a.wiki-link {{
            color: {link_color};
            border-bottom: 1px dashed {link_color};
        }}
        a.wiki-link:hover {{
            border-bottom-style: solid;
        }}
        .math-block {{
            overflow-x: auto;
            padding: 16px 0;
        }}
        .math-inline {{
            padding: 0 2px;
        }}
        .mermaid {{
            background: {code_bg};
            padding: 16px;
            border-radius: 6px;
            margin: 16px 0;
            text-align: center;
        }}
        /* Pygments */
        {pygments_css}
        /* Callouts */
        {callout_css}
        /* Graphviz */
        {graphviz_css}
        /* Mermaid */
        {mermaid_css}
        /* Task lists */
        {tasklist_css}
        @media print {{
            body {{ max-width: none; }}
        }}
    </style>
</head>
<body class="{body_class}">
{content}
{mermaid_block}
{graphviz_block}
</body>
</html>"""


def viewer_export_html(
    content: str,
    title: str = "Document",
    dark_mode: bool = False,
    font_size: int = 14,
    base_path: Path | None = None,
    logseq_mode: bool = False,
) -> str:
    """Convert markdown to a complete, offline-capable HTML document.

    Uses the same extension pipeline as the live preview.
    """
    md = create_markdown_pipeline(
        dark_mode=dark_mode,
        base_path=base_path,
        logseq_mode=logseq_mode,
    )
    html_content = md.convert(content)

    # Render any uncached diagrams synchronously
    pending = getattr(md, "_pending_diagrams", [])
    if pending:
        html_content = _render_pending_diagrams_sync(html_content, pending)

    return build_export_template(
        html_content,
        title=title,
        dark_mode=dark_mode,
        font_size=font_size,
    )


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------

_IMG_SRC_PATTERN = re.compile(
    r'(<img\s[^>]*?\bsrc=")([^"]+)(")',
    re.IGNORECASE,
)


def embed_local_images(html: str, base_path: Path) -> str:
    """Replace local image src paths with inline base64 data URIs.

    Only processes paths that resolve to existing local files.
    Already-absolute URLs (http://, https://, data:) are left untouched.
    """
    def replace_src(m):
        prefix = m.group(1)
        src = m.group(2)
        suffix = m.group(3)

        # Skip URLs and data URIs
        if src.startswith(("http://", "https://", "data:", "//")):
            return m.group(0)

        path = (base_path / src).resolve()
        if not path.is_file():
            return m.group(0)

        mime, _ = mimetypes.guess_type(str(path))
        if not mime or not mime.startswith("image/"):
            return m.group(0)

        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f'{prefix}data:{mime};base64,{b64}{suffix}'

    return _IMG_SRC_PATTERN.sub(replace_src, html)


def copy_resources_for_project(
    html: str,
    base_path: Path,
    output_dir: Path,
) -> str:
    """Copy local image files to output_dir/assets/ and rewrite src paths.

    Returns the modified HTML with updated relative paths.
    """
    assets_dir = output_dir / "assets"
    copied: dict[str, str] = {}  # original src -> new relative path

    def replace_src(m):
        prefix = m.group(1)
        src = m.group(2)
        suffix = m.group(3)

        if src.startswith(("http://", "https://", "data:", "//")):
            return m.group(0)

        if src in copied:
            return f'{prefix}{copied[src]}{suffix}'

        path = (base_path / src).resolve()
        if not path.is_file():
            return m.group(0)

        assets_dir.mkdir(parents=True, exist_ok=True)

        # Use a flat name to avoid directory collisions
        dest_name = path.name
        counter = 1
        while (assets_dir / dest_name).exists() and (assets_dir / dest_name).read_bytes() != path.read_bytes():
            stem = path.stem
            dest_name = f"{stem}_{counter}{path.suffix}"
            counter += 1

        dest = assets_dir / dest_name
        if not dest.exists():
            shutil.copy2(path, dest)

        rel = f"assets/{dest_name}"
        copied[src] = rel
        return f'{prefix}{rel}{suffix}'

    return _IMG_SRC_PATTERN.sub(replace_src, html)

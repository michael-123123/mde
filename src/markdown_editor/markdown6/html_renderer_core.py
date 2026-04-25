"""HTML rendering core — the single source of truth for preview and export.

NON-QT-APPLICATION-SAFE: This module must remain loadable in non-Qt-application
environments (CLI exports run without a `QApplication`). It transitively
imports `PySide6.QtCore` via `AppContext` (QObject + Signal — both usable
without a QApplication), but MUST NOT add dependencies on
`PySide6.QtWidgets`, `QApplication`, or event-loop-requiring code. A regression
here silently breaks `mde export` on minimal systems. See
local/html-export-unify.md §4 decision A.

WATCH-POINT — migrate to a `rendering/` subpackage if this module grows:
If diagram resolution, template CSS bundling (Pygments / callout / tasklist /
math / mermaid / graphviz), the Markdown factory, and template wrapping start
wanting their own files, migrate to a subpackage. See
local/html-export-unify.md §7 "Grow html_renderer_core.py into a rendering/
subpackage" for the sketch. A single module is fine as long as the file stays
coherent — this comment is a reminder for the next contributor, not a
requirement to act now.

Public API (decision A):
  - `build_markdown()` — Markdown factory with the full extension stack.
  - `render_html_document(content, ctx, total_lines=0)` — full export
    pipeline (markdown source → self-contained HTML).
  - `wrap_html_in_full_template(body, ctx, total_lines=0)` — template
    wrap helper (used by `render_html_document` after conversion AND
    by `MarkdownEditor.get_html_template` where the body is already
    converted by the preview's shared `self.md`).

Decision tech-debt marker: `render_html_document` does NOT populate the
`<title>` tag — exports post-process the output via a string `.replace()`
in `export_service` (decision T1). The clean fix is to plumb the title
through `ctx` once `session.current_file_path` is added (see FUTURE WORK in
local/html-export-unify.md).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension
from pygments.formatters import HtmlFormatter

from markdown_editor.markdown6 import graphviz_service
from markdown_editor.markdown6.diagram_helpers import _render_diagram
from markdown_editor.markdown6.extensions import (
    BreaklessListExtension,
    CalloutExtension,
    GraphvizExtension,
    LogseqExtension,
    MathExtension,
    MermaidExtension,
    NormalizeListIndentExtension,
    SourceLineExtension,
    StrikethroughExtension,
    TaskListExtension,
    WikiLinkExtension,
    get_callout_css,
    get_math_js,
    get_mermaid_css,
    get_mermaid_js,
    get_tasklist_css,
)
from markdown_editor.markdown6.templates.preview import PREVIEW_TEMPLATE_FULL
from markdown_editor.markdown6.theme import get_theme

if TYPE_CHECKING:
    from markdown_editor.markdown6.app_context import AppContext


# ── Canonical font/size defaults (decision G) ──────────────────────
#
# When `export.use_canonical_fonts` is True, these values override
# the user's `preview.*` settings. When False (default), the user's
# settings flow through — exports look the same as the GUI preview.

_CANONICAL_BODY_FONT = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
)
_CANONICAL_CODE_FONT = (
    '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace'
)
_CANONICAL_FONT_SIZE = 14
_CANONICAL_LINE_HEIGHT = 1.5
_CANONICAL_HEADING_SIZES = {
    # (value, unit) — matches DEFAULT_SETTINGS defaults in settings_manager.py
    "h1": ("2.0", "em"),
    "h2": ("1.5", "em"),
    "h3": ("1.25", "em"),
    "h4": ("1.0", "em"),
    "h5": ("0.875", "em"),
    "h6": ("0.85", "em"),
    "code": ("85", "%"),
}


# ── Pygments formatter cache ────────────────────────────────────────
#
# Creating an HtmlFormatter is non-trivial (loads the style); cache per
# style name so repeated renders reuse the same instance.

_html_formatter_cache: dict[str, HtmlFormatter] = {}


def get_cached_html_formatter(style: str) -> HtmlFormatter:
    """Get a cached Pygments HtmlFormatter for the given style.

    Creating a formatter is non-trivial (it loads the style into memory);
    we cache per style name so repeated renders reuse the same instance.
    Exposed publicly so `MarkdownEditor.get_html_template`'s QTextBrowser
    fallback path can share this cache rather than duplicate it.
    """
    if style not in _html_formatter_cache:
        _html_formatter_cache[style] = HtmlFormatter(style=style, cssclass="highlight")
    return _html_formatter_cache[style]


# ── Public API ──────────────────────────────────────────────────────

def build_markdown(
    *,
    extra_extensions: list | None = None,
) -> markdown.Markdown:
    """Construct a Markdown instance with the full extension stack.

    This is the SINGLE definition of "preview-grade rendering". Both
    the live preview (via `MarkdownEditor._init_markdown`) and the
    export pipeline build Markdown instances via this function, so
    preview output and exported HTML use the same extensions in the
    same order.

    ``extra_extensions`` is appended after the built-in stack and is
    where plugin-registered ``markdown.Extension`` instances are
    plugged in (see ``plugins.api.register_markdown_extension``).
    The order matters — plugin extensions run last so they can
    transform output produced by the built-in stack.
    """
    extensions = [
        "extra",
        "sane_lists",
        LogseqExtension(),
        NormalizeListIndentExtension(),
        BreaklessListExtension(),
        FencedCodeExtension(),
        CodeHiliteExtension(css_class="highlight", guess_lang=True),
        TableExtension(),
        TocExtension(),
        'admonition',
        CalloutExtension(),
        WikiLinkExtension(),
        MathExtension(),
        MermaidExtension(),
        GraphvizExtension(),
        TaskListExtension(),
        StrikethroughExtension(),
        SourceLineExtension(),
    ]
    if extra_extensions:
        extensions.extend(extra_extensions)
    return markdown.Markdown(extensions=extensions)


def render_html_document(
    content: str, ctx: "AppContext", total_lines: int = 0,
) -> str:
    """Full export pipeline: markdown source → wrapped HTML.

    Runs `build_markdown()`, sets diagram/logseq attributes on the new
    Markdown instance from `ctx`, converts the markdown, synchronously
    resolves any pending diagrams (decision B1), and wraps the result
    in `PREVIEW_TEMPLATE_FULL` via `wrap_html_in_full_template`.

    For exports only. The live preview has its own shared `self.md`
    (see `MarkdownEditor._init_markdown`) and calls
    `wrap_html_in_full_template` directly — it does NOT go through
    this function, to avoid converting the same markdown twice.
    """
    md = build_markdown()
    md.reset()
    md._pending_diagrams = []
    dark_mode = ctx.get("view.theme", "light") == "dark"
    md.mermaid_dark_mode = dark_mode
    md.graphviz_dark_mode = dark_mode
    # Base path for resolving relative `.dot` image references. Callers
    # that know the source markdown file's location set this via
    # `_render.graphviz_base_path` on the ctx (typically an ephemeral
    # export ctx). Project/multi-file/stdin exports leave it unset —
    # inherently ambiguous when multiple sources are combined.
    md.graphviz_base_path = ctx.get("_render.graphviz_base_path", None)
    md.logseq_mode = ctx.get("view.logseq_mode", False)

    body = md.convert(content)
    body = _resolve_pending_diagrams(body, md._pending_diagrams)
    return wrap_html_in_full_template(body, ctx, total_lines)


def wrap_html_in_full_template(
    body: str, ctx: "AppContext", total_lines: int = 0,
) -> str:
    """Wrap already-converted HTML `body` in `PREVIEW_TEMPLATE_FULL`.

    Reads styling values from `ctx`:
      - `view.theme` → dark/light mode (colors, Pygments style)
      - `editor.scroll_past_end` → trailing 80vh div toggle
      - `export.use_canonical_fonts` → ignore user fonts, use canonical defaults
      - `view.preview_font_size`, `preview.body_font_family`, etc.
        (only when `use_canonical_fonts=False`)

    Used by `render_html_document` (after it converts) and by
    `MarkdownEditor.get_html_template` (the FULL-path preview branch —
    body is already converted by the preview's shared Markdown instance).
    """
    theme = ctx.get("view.theme", "light")
    dark_mode = theme == "dark"
    scroll_past_end = ctx.get("editor.scroll_past_end", True)
    use_canonical = ctx.get("export.use_canonical_fonts", False)

    colors = get_theme(dark_mode)
    bg_color = colors.editor_bg
    text_color = colors.editor_text
    heading_border = colors.preview_heading_border
    code_bg = colors.code_bg
    blockquote_color = colors.preview_blockquote
    link_color = colors.link
    # Preview's code-fence colour scheme matches the editor's (both
    # read `DEFAULT_SCHEME_*` from the fenced_code_highlighter facade).
    # "github-dark" was previously used for light mode — a bug, since
    # it's a dark-bg scheme.
    from markdown_editor.markdown6.fenced_code_highlighter import (
        DEFAULT_SCHEME_DARK,
        DEFAULT_SCHEME_LIGHT,
    )
    pygments_style = DEFAULT_SCHEME_DARK if dark_mode else DEFAULT_SCHEME_LIGHT
    body_class = "dark" if dark_mode else "light"

    # Font / size values — canonical (decision G True) or from ctx (False)
    if use_canonical:
        font_size = _CANONICAL_FONT_SIZE
        body_font = _CANONICAL_BODY_FONT
        code_font = _CANONICAL_CODE_FONT
        heading_font_css = ""
        line_height = _CANONICAL_LINE_HEIGHT

        def _canon(prefix: str) -> str:
            val, unit = _CANONICAL_HEADING_SIZES[prefix]
            return f"{val}{unit}"

        h1_size = _canon("h1")
        h2_size = _canon("h2")
        h3_size = _canon("h3")
        h4_size = _canon("h4")
        h5_size = _canon("h5")
        h6_size = _canon("h6")
        code_size = _canon("code")
    else:
        font_size = ctx.get("view.preview_font_size", 14)

        body_font_setting = ctx.get("preview.body_font_family", "")
        body_font = (
            f'"{body_font_setting}", sans-serif' if body_font_setting
            else _CANONICAL_BODY_FONT
        )

        code_font_setting = ctx.get("preview.code_font_family", "")
        code_font = (
            f'"{code_font_setting}", monospace' if code_font_setting
            else _CANONICAL_CODE_FONT
        )

        heading_font_setting = ctx.get("preview.heading_font_family", "")
        heading_font = (
            f'"{heading_font_setting}", sans-serif' if heading_font_setting
            else ""
        )
        heading_font_css = (
            f'font-family: {heading_font};' if heading_font else ""
        )
        line_height = ctx.get("preview.line_height", 1.5)

        def _sz(key_prefix: str) -> str:
            val = ctx.get(f"preview.{key_prefix}_size", 1.0)
            unit = ctx.get(f"preview.{key_prefix}_size_unit", "em")
            return f"{val}{unit}"

        h1_size = _sz("h1")
        h2_size = _sz("h2")
        h3_size = _sz("h3")
        h4_size = _sz("h4")
        h5_size = _sz("h5")
        h6_size = _sz("h6")
        code_size = _sz("code")

    formatter = get_cached_html_formatter(pygments_style)
    pygments_css = formatter.get_style_defs(".highlight")

    callout_css = get_callout_css(dark_mode)
    tasklist_css = get_tasklist_css(dark_mode)
    graphviz_css = graphviz_service.get_graphviz_css(dark_mode)
    graphviz_js = (
        graphviz_service.get_graphviz_js()
        if not graphviz_service.has_graphviz() else ""
    )
    mermaid_css = get_mermaid_css(dark_mode)
    mermaid_js = get_mermaid_js()
    math_js = get_math_js()

    scroll_past_end_div = (
        "<div style='height: 80vh;'></div>" if scroll_past_end else ""
    )

    return PREVIEW_TEMPLATE_FULL.format(
        body_font=body_font, code_font=code_font, font_size=font_size,
        line_height=line_height, text_color=text_color, bg_color=bg_color,
        heading_border=heading_border, code_bg=code_bg,
        blockquote_color=blockquote_color, link_color=link_color,
        heading_font_css=heading_font_css,
        h1_size=h1_size, h2_size=h2_size, h3_size=h3_size,
        h4_size=h4_size, h5_size=h5_size, h6_size=h6_size,
        code_size=code_size, body_class=body_class,
        pygments_css=pygments_css, callout_css=callout_css,
        graphviz_css=graphviz_css, mermaid_css=mermaid_css,
        tasklist_css=tasklist_css,
        math_js=math_js, mermaid_js=mermaid_js, graphviz_js=graphviz_js,
        content=body, total_lines=total_lines,
        scroll_past_end_div=scroll_past_end_div,
    )


# ── Private helpers ─────────────────────────────────────────────────

def _resolve_pending_diagrams(body: str, pending: list) -> str:
    """Synchronously render pending diagrams and substitute their SVGs
    into the placeholder divs in `body`.

    Decision B1: export path blocks until every diagram renders, then
    writes self-contained HTML. Uses a LOCAL `ThreadPoolExecutor` (not
    the GUI's `main_window._diagram_executor`) so this helper works
    from headless CLI exports. The pool is created fresh per call and
    shut down via the `with` block.

    The live preview does NOT call this — it uses its own async
    polling path in `DocumentTab._poll_diagram_futures`.
    """
    if not pending:
        return body
    workers = min(len(pending), 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            idx: pool.submit(_render_diagram, kind, source, dark)
            for idx, (kind, source, dark) in enumerate(pending)
        }
        for idx, future in futures.items():
            svg_html, _css_class = future.result()
            body = _replace_diagram_placeholder(body, idx, svg_html)
    return body


# Outer-div-of-the-placeholder matcher. Anchored on the stable
# `id="diagram-pending-N"` the preprocessor emits. The non-greedy
# `[^>]*?` captures on either side of the id let extensions inject or
# reorder any other attributes on this div — SourceLineExtension
# prepends `data-source-line="N"`, and any future extension that
# decorates block-level divs rides along the same way.
_PENDING_PLACEHOLDER_RE = re.compile(
    r'<div([^>]*?)\bid="diagram-pending-(\d+)"([^>]*?)>'
    r'<div class="diagram-loading">'
    r'<pre class="diagram-loading-source">[^<]*</pre>'
    r'<div class="diagram-loading-spinner">Rendering\.\.\.</div>'
    r'</div>'
    r'</div>'
)


def _replace_diagram_placeholder(body: str, idx: int, svg_html: str) -> str:
    """Swap the pending-diagram placeholder's inner "Rendering..." block
    for the rendered SVG, preserving the outer div and its attributes.

    Finds the outer div by its stable `id="diagram-pending-N"` anchor
    rather than reconstructing the whole placeholder literal. This
    survives `SourceLineExtension` prepending `data-source-line` (and
    any other attribute injection) onto the outer div. The outer div's
    `class`, `data-source`, and `data-source-line` are preserved; only
    the now-meaningless `id` is dropped.

    The result is byte-equivalent (modulo attribute order) to what the
    live preview emits for an already-cached diagram — both paths end
    up with `<div class="X-diagram" data-source="..." data-source-line="N">{svg}</div>`.
    """
    def _sub(m):
        # Scan matches all pending placeholders; only swap the one whose
        # id matches our idx. Non-target matches return unchanged (identity).
        # Can't use `count=1` because a different-idx match occurring first
        # would consume our quota before we reach the target.
        if int(m.group(2)) != idx:
            return m.group(0)
        return f'<div{m.group(1)}{m.group(3)}>{svg_html}</div>'

    return _PENDING_PLACEHOLDER_RE.sub(_sub, body)

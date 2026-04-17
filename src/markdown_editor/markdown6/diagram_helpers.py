"""Diagram rendering helpers shared between GUI (async) and headless (sync) paths.

NON-QT-APPLICATION-SAFE: This module must remain loadable in non-Qt-application
environments. It is used by `html_renderer_core` which runs in CLI exports
without a QApplication. Do NOT add dependencies on PySide6.QtWidgets,
QApplication, or event loops. The underlying services (`mermaid_service`,
`graphviz_service`) shell out via subprocess and are GUI-independent.

The live preview submits `_render_diagram` to a QThreadPoolExecutor and polls
for results asynchronously (see `DocumentTab._render_pending_diagrams`). The
export path invokes it synchronously from a local `ThreadPoolExecutor` inside
`html_renderer_core._resolve_pending_diagrams` (decision B1 in
local/html-export-unify.md).
"""

from __future__ import annotations


def _render_diagram(kind: str, source: str, dark_mode: bool) -> tuple[str, str]:
    """Render a single diagram. Returns (svg_html, css_class).

    Thread-safe: shells out to `mmdc` / `dot` via subprocess, which is
    fully isolated between worker threads. Exceptions are caught and
    converted to a visible error div so one bad diagram doesn't break
    the whole render.
    """
    try:
        if kind == 'mermaid':
            from markdown_editor.markdown6 import mermaid_service
            svg, _error = mermaid_service.render_mermaid(source, dark_mode)
            return svg, 'mermaid-diagram'
        else:
            from markdown_editor.markdown6 import graphviz_service
            svg, _error = graphviz_service.render_dot(source, dark_mode)
            return svg, 'graphviz-diagram'
    except Exception as e:
        import html
        return (
            f'<div class="diagram-loading">Error: {html.escape(str(e))}</div>',
            'mermaid-diagram',
        )

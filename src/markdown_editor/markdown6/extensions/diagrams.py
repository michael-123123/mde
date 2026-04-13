"""Mermaid and Graphviz diagram rendering extensions.

Cached diagrams are inlined immediately. Uncached diagrams get a
placeholder that is filled asynchronously after the page loads (see
DocumentTab._render_pending_diagrams). This keeps the preview snappy
even when mmdc/dot takes 1-2 s per diagram.
"""

import re
from pathlib import Path

from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor

# ── Shared helper ──────────────────────────────────────────────────

_OUTER_FENCE_RE = re.compile(
    r'^(`{4,}|~{4,}).*\n(.*?)^\1\s*$',
    re.MULTILINE | re.DOTALL
)


def _sub_preserving_outer_fences(pattern, repl, text):
    """Run a regex substitution while protecting content inside outer
    fenced code blocks (4+ backticks or tildes) from being matched.

    Outer fences are temporarily replaced with placeholders, the diagram
    regex runs on the remaining text, then the placeholders are restored.
    """
    placeholders = {}
    counter = 0

    def mask(m):
        nonlocal counter
        key = f"\x00FENCE{counter}\x00"
        counter += 1
        placeholders[key] = m.group(0)
        return key

    masked = _OUTER_FENCE_RE.sub(mask, text)
    result = pattern.sub(repl, masked)
    for key, original in placeholders.items():
        result = result.replace(key, original)
    return result


# ── Mermaid ────────────────────────────────────────────────────────

class MermaidPreprocessor(Preprocessor):
    """Preprocessor to convert mermaid code blocks.

    Cached diagrams are inlined immediately.  Uncached diagrams get a
    placeholder that is filled asynchronously after the page loads (see
    DocumentTab._render_pending_diagrams).  This keeps the preview snappy
    even when mmdc takes 1-2 s per diagram.

    Falls back to <div class="mermaid"> for client-side JS when mmdc is
    unavailable.

    Reads dark_mode from md.mermaid_dark_mode attribute (set before convert).
    """

    MERMAID_PATTERN = re.compile(
        r'^```mermaid\s*\n(.*?)^```',
        re.MULTILINE | re.DOTALL
    )

    def run(self, lines):
        import html as html_mod

        from markdown_editor.markdown6 import mermaid_service

        dark_mode = getattr(self.md, 'mermaid_dark_mode', False)
        # Collect pending (uncached) diagram sources for async rendering
        pending = getattr(self.md, '_pending_diagrams', None)
        if pending is None:
            pending = []
            self.md._pending_diagrams = pending

        text = '\n'.join(lines)

        def replace_mermaid(m):
            content = m.group(1).strip()

            if not mermaid_service.has_mermaid():
                return f'<div class="mermaid">\n{content}\n</div>'

            escaped_src = html_mod.escape(content).replace('"', '&quot;')

            # If cached, inline immediately (zero cost)
            if mermaid_service.is_cached(content, dark_mode):
                svg, error = mermaid_service.render_mermaid(content, dark_mode)
                if error:
                    return svg
                return f'<div class="mermaid-diagram" data-source="{escaped_src}">{svg}</div>'

            # Not cached — emit placeholder, schedule async render
            idx = len(pending)
            pending.append(('mermaid', content, dark_mode))
            escaped = html_mod.escape(content)
            return (
                f'<div class="mermaid-diagram" data-source="{escaped_src}" id="diagram-pending-{idx}">'
                f'<div class="diagram-loading">'
                f'<pre class="diagram-loading-source">{escaped}</pre>'
                f'<div class="diagram-loading-spinner">Rendering...</div>'
                f'</div></div>'
            )

        text = _sub_preserving_outer_fences(self.MERMAID_PATTERN, replace_mermaid, text)
        return text.split('\n')


class MermaidExtension(Extension):
    """Extension for Mermaid diagram support."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            MermaidPreprocessor(md),
            'mermaid',
            26
        )


def get_mermaid_js() -> str:
    """Get JavaScript for Mermaid diagram rendering.

    Returns JS only when mmdc is unavailable (client-side fallback).
    When mmdc is installed, diagrams are pre-rendered to SVG and no JS is needed.
    """
    from markdown_editor.markdown6 import mermaid_service

    if mermaid_service.has_mermaid():
        return ""  # Server-side rendered, no JS needed
    return mermaid_service.get_mermaid_js()


def get_mermaid_css(dark_mode: bool = False) -> str:
    """Get CSS for mermaid diagrams and errors."""
    from markdown_editor.markdown6 import mermaid_service
    return mermaid_service.get_mermaid_css(dark_mode)


# ── Graphviz ───────────────────────────────────────────────────────

class GraphvizPreprocessor(Preprocessor):
    """Preprocessor to convert graphviz/dot code blocks to rendered SVG.

    Like MermaidPreprocessor, cached results are inlined immediately and
    uncached ones get a placeholder for async rendering.

    Reads dark_mode from md.graphviz_dark_mode attribute (set before convert).
    """

    GRAPHVIZ_PATTERN = re.compile(
        r'^```(?:dot|graphviz)\s*\n(.*?)^```',
        re.MULTILINE | re.DOTALL
    )

    def run(self, lines):
        import html as html_mod

        from markdown_editor.markdown6 import graphviz_service

        dark_mode = getattr(self.md, 'graphviz_dark_mode', False)
        pending = getattr(self.md, '_pending_diagrams', None)
        if pending is None:
            pending = []
            self.md._pending_diagrams = pending

        text = '\n'.join(lines)

        def replace_graphviz(m):
            source = m.group(1).strip()

            escaped_src = html_mod.escape(source).replace('"', '&quot;')

            if not graphviz_service.has_graphviz():
                escaped = html_mod.escape(source)
                return f'<div class="graphviz-pending" data-source="{escaped_src}">{escaped}</div>'

            # If cached, inline immediately
            if graphviz_service.is_cached(source, dark_mode):
                svg, error = graphviz_service.render_dot(source, dark_mode)
                if error:
                    return svg
                return f'<div class="graphviz-diagram" data-source="{escaped_src}">{svg}</div>'

            # Not cached — emit placeholder, schedule async render
            idx = len(pending)
            pending.append(('graphviz', source, dark_mode))
            escaped = html_mod.escape(source)
            return (
                f'<div class="graphviz-diagram" data-source="{escaped_src}" id="diagram-pending-{idx}">'
                f'<div class="diagram-loading">'
                f'<pre class="diagram-loading-source">{escaped}</pre>'
                f'<div class="diagram-loading-spinner">Rendering...</div>'
                f'</div></div>'
            )

        text = _sub_preserving_outer_fences(self.GRAPHVIZ_PATTERN, replace_graphviz, text)
        return text.split('\n')


class GraphvizImagePostprocessor(Postprocessor):
    """Postprocessor to handle .dot file references in images.

    Reads dark_mode and base_path from md attributes (set before convert).
    """

    DOT_IMAGE_PATTERN = re.compile(
        r'<img\s+[^>]*src=["\']([^"\']+\.dot)["\'][^>]*>',
        re.IGNORECASE
    )

    def run(self, text):
        from markdown_editor.markdown6 import graphviz_service

        # Get config from markdown instance (set by caller before convert)
        dark_mode = getattr(self.md, 'graphviz_dark_mode', False)
        base_path = getattr(self.md, 'graphviz_base_path', None)

        def replace_dot_image(m):
            dot_path = m.group(1)

            # Resolve path relative to base_path if provided
            if base_path:
                full_path = Path(base_path) / dot_path
            else:
                full_path = Path(dot_path)

            # Render the .dot file
            svg, error = graphviz_service.render_dot_file(full_path, dark_mode)
            if error:
                return svg  # Error HTML
            return f'<div class="graphviz-diagram">{svg}</div>'

        text = self.DOT_IMAGE_PATTERN.sub(replace_dot_image, text)
        return text


class GraphvizExtension(Extension):
    """Extension for Graphviz diagram support.

    Before calling md.convert(), set these attributes on the markdown instance:
        md.graphviz_dark_mode = True/False
        md.graphviz_base_path = "/path/to/file/directory"
    """

    def extendMarkdown(self, md):
        md.preprocessors.register(
            GraphvizPreprocessor(md),
            'graphviz',
            27  # After mermaid (26)
        )
        md.postprocessors.register(
            GraphvizImagePostprocessor(md),
            'graphviz_image',
            24  # After math_post (25)
        )

"""Graphviz diagram rendering service with caching."""

import hashlib
from pathlib import Path

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)

# In-memory cache: hash -> (svg_string, error_string or None)
_render_cache: dict[str, tuple[str, str | None]] = {}


def has_graphviz() -> bool:
    """Check if graphviz is available on the system."""
    from markdown_editor.markdown6.tool_paths import has_dot
    return has_dot()


def clear_cache():
    """Clear the render cache."""
    _render_cache.clear()


def is_cached(source: str, dark_mode: bool = False) -> bool:
    """Check if a render result is already cached (no subprocess needed)."""
    cache_key = hashlib.md5(f"{source}:{dark_mode}".encode()).hexdigest()
    return cache_key in _render_cache


def render_dot(source: str, dark_mode: bool = False) -> tuple[str, str | None]:
    """Render DOT source to SVG.

    Args:
        source: DOT language source code
        dark_mode: Whether to use dark mode colors

    Returns:
        Tuple of (svg_string, error_string or None)
        If successful, error is None.
        If failed, svg_string contains error display HTML.
    """
    # Create cache key from source and dark_mode
    cache_key = hashlib.md5(f"{source}:{dark_mode}".encode()).hexdigest()

    if cache_key in _render_cache:
        return _render_cache[cache_key]

    result = _render_dot_impl(source, dark_mode)
    _render_cache[cache_key] = result
    return result


def _render_dot_impl(source: str, dark_mode: bool) -> tuple[str, str | None]:
    """Implementation of DOT rendering."""
    try:
        import graphviz
    except ImportError:
        error = "graphviz package not installed"
        return _format_error(source, error), error

    if not has_graphviz():
        error = "Graphviz not installed on system (dot command not found)"
        return _format_error(source, error), error

    try:
        # Parse and render the DOT source
        # graphviz.Source handles the DOT language
        graph = graphviz.Source(source)

        # Render to SVG
        svg_bytes = graph.pipe(format='svg')
        svg_string = svg_bytes.decode('utf-8')

        # Make SVG responsive (remove fixed dimensions, keep viewBox)
        svg_string = _make_svg_responsive(svg_string)

        # Apply dark mode styling if needed
        if dark_mode:
            svg_string = _apply_dark_mode(svg_string)

        return svg_string, None

    except graphviz.CalledProcessError as e:
        error = e.stderr.decode('utf-8') if e.stderr else str(e)
        logger.warning(f"Graphviz render error: {error}")
        return _format_error(source, error), error
    except Exception as e:
        error = str(e)
        logger.exception("Graphviz render failed")
        return _format_error(source, error), error


def render_dot_file(file_path: Path, dark_mode: bool = False) -> tuple[str, str | None]:
    """Render a .dot file to SVG.

    Args:
        file_path: Path to the .dot file
        dark_mode: Whether to use dark mode colors

    Returns:
        Tuple of (svg_string, error_string or None)
    """
    try:
        source = file_path.read_text(encoding='utf-8')
        return render_dot(source, dark_mode)
    except FileNotFoundError:
        error = f"File not found: {file_path}"
        return _format_error(f"// {file_path}", error), error
    except Exception as e:
        error = str(e)
        return _format_error(f"// {file_path}", error), error


def _make_svg_responsive(svg: str) -> str:
    """Replace pt/px dimensions with pixel values from viewBox so setZoomFactor scales it.

    Graphviz outputs SVGs with fixed pt/px dimensions:
        <svg width="62pt" height="116pt" viewBox="0 0 62 116">
    We replace pt/px units with plain pixel values from viewBox. This gives
    the SVG a fixed intrinsic size that setZoomFactor can scale. The CSS
    max-width:100% on the container prevents horizontal overflow.
    """
    import re

    # Extract viewBox dimensions
    vb_match = re.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg)
    if vb_match:
        vb_w, vb_h = vb_match.group(1), vb_match.group(2)
        # Replace pt/px width with viewBox width in pixels
        svg = re.sub(r'(<svg[^>]*?)\bwidth="[\d.]+p[tx]"', rf'\1width="{vb_w}"', svg, count=1)
        # Replace pt/px height with viewBox height in pixels
        svg = re.sub(r'(<svg[^>]*?)\bheight="[\d.]+p[tx]"', rf'\1height="{vb_h}"', svg, count=1)
    else:
        # No viewBox — just strip the units (pt -> px is close enough)
        svg = re.sub(r'(<svg[^>]*?)\bwidth="([\d.]+)p[tx]"', r'\1width="\2"', svg, count=1)
        svg = re.sub(r'(<svg[^>]*?)\bheight="([\d.]+)p[tx]"', r'\1height="\2"', svg, count=1)
    return svg


def _apply_dark_mode(svg: str) -> str:
    """Apply dark mode styling to SVG.

    Swaps the graphviz defaults (white background, black strokes/text) for
    dark equivalents, but respects user-specified `fillcolor` on nodes.

    Text inside a `<g class="node">` whose shape carries a user-specified
    fill (any colour other than `none` or the dark-mode substitute
    `#1e1e1e`) gets dark text (`#000`) so it stays readable against the
    pastel fill. Text everywhere else — edge labels, graph titles,
    unfilled nodes — gets light text (`#d4d4d4`) for contrast with the
    dark page background.
    """
    import re

    replacements = [
        ('fill="white"', 'fill="#1e1e1e"'),
        ('fill="black"', 'fill="#d4d4d4"'),
        ('stroke="black"', 'stroke="#d4d4d4"'),
        ("fill='white'", "fill='#1e1e1e'"),
        ("fill='black'", "fill='#d4d4d4'"),
        ("stroke='black'", "stroke='#d4d4d4'"),
    ]
    for old, new in replacements:
        svg = svg.replace(old, new)

    text_tag_re = re.compile(r'<text\b[^>]*>')

    def _inject_text_fill(block: str, color: str) -> str:
        def _sub(m):
            tag = m.group(0)
            if 'fill=' in tag:
                return tag
            return tag[:-1] + f' fill="{color}">'
        return text_tag_re.sub(_sub, block)

    # Text inside user-filled node groups needs dark colour for contrast.
    # The first shape (path/polygon/ellipse/rect/circle) inside the group
    # carries the node's fill.
    shape_fill_re = re.compile(
        r'<(?:path|polygon|ellipse|rect|circle)\b[^>]*\bfill="([^"]+)"'
    )

    def _handle_node_group(m):
        block = m.group(0)
        shape = shape_fill_re.search(block)
        if shape and shape.group(1).lower() not in ('none', '#1e1e1e'):
            return _inject_text_fill(block, '#000')
        return _inject_text_fill(block, '#d4d4d4')

    svg = re.sub(
        r'<g[^>]*\bclass="node"[^>]*>.*?</g>',
        _handle_node_group,
        svg,
        flags=re.DOTALL,
    )

    # Any remaining text (outside node groups) gets the default light fill.
    svg = _inject_text_fill(svg, '#d4d4d4')

    return svg


def _format_error(source: str, error: str) -> str:
    """Format an error display with source code and error message.

    Shows the raw DOT source with error annotation.
    """
    # Escape HTML in source and error
    import html
    source_escaped = html.escape(source)
    error_escaped = html.escape(error)

    # Format as HTML with styling
    return f'''<div class="graphviz-error">
<div class="graphviz-error-header">Graphviz Error</div>
<pre class="graphviz-error-source">{source_escaped}</pre>
<div class="graphviz-error-message">{error_escaped}</div>
</div>'''


def get_graphviz_css(dark_mode: bool = False) -> str:
    """Get CSS for graphviz diagrams and errors."""
    if dark_mode:
        return """
        .graphviz-diagram {
            text-align: center;
            margin: 16px 0;
        }
        .graphviz-diagram svg {
            max-width: 100%;
            height: auto;
        }
        .graphviz-error {
            background: #3a1d1d;
            border: 1px solid #f85149;
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            font-family: monospace;
        }
        .graphviz-error-header {
            color: #f85149;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .graphviz-error-source {
            background: #2d2d2d;
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            color: #d4d4d4;
            margin: 8px 0;
        }
        .graphviz-error-message {
            color: #f85149;
            font-size: 0.9em;
        }
        """
    else:
        return """
        .graphviz-diagram {
            text-align: center;
            margin: 16px 0;
        }
        .graphviz-diagram svg {
            max-width: 100%;
            height: auto;
        }
        .graphviz-error {
            background: #ffebe9;
            border: 1px solid #cf222e;
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            font-family: monospace;
        }
        .graphviz-error-header {
            color: #cf222e;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .graphviz-error-source {
            background: #f6f8fa;
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            color: #24292f;
            margin: 8px 0;
        }
        .graphviz-error-message {
            color: #cf222e;
            font-size: 0.9em;
        }
        """


def get_graphviz_js() -> str:
    """Get JavaScript fallback for when Python graphviz is unavailable.

    Uses viz.js to render in the browser.
    """
    return """
    <script src="https://cdn.jsdelivr.net/npm/@viz-js/viz@3.2.4/lib/viz-standalone.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Find all unrendered graphviz blocks (those with raw DOT source)
            document.querySelectorAll('.graphviz-pending').forEach(async function(el) {
                try {
                    const source = el.textContent;
                    const viz = await Viz.instance();
                    const svg = viz.renderSVGElement(source);
                    el.innerHTML = '';
                    el.appendChild(svg);
                    el.classList.remove('graphviz-pending');
                    el.classList.add('graphviz-diagram');
                } catch (e) {
                    el.innerHTML = '<div class="graphviz-error">' +
                        '<div class="graphviz-error-header">Graphviz Error</div>' +
                        '<pre class="graphviz-error-source">' + el.textContent.replace(/</g, '&lt;') + '</pre>' +
                        '<div class="graphviz-error-message">' + e.message.replace(/</g, '&lt;') + '</div>' +
                        '</div>';
                    el.classList.remove('graphviz-pending');
                }
            });
        });
    </script>
    """

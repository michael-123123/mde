"""Graphviz diagram rendering service with caching."""

import hashlib
import shutil
from pathlib import Path

# In-memory cache: hash -> (svg_string, error_string or None)
_render_cache: dict[str, tuple[str, str | None]] = {}


def has_graphviz() -> bool:
    """Check if graphviz is available on the system."""
    return shutil.which("dot") is not None


def clear_cache():
    """Clear the render cache."""
    _render_cache.clear()


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

        # Apply dark mode styling if needed
        if dark_mode:
            svg_string = _apply_dark_mode(svg_string)

        return svg_string, None

    except graphviz.CalledProcessError as e:
        # Graphviz execution error (syntax error, etc.)
        error = e.stderr.decode('utf-8') if e.stderr else str(e)
        return _format_error(source, error), error
    except Exception as e:
        error = str(e)
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


def _apply_dark_mode(svg: str) -> str:
    """Apply dark mode styling to SVG.

    Inverts common colors used by Graphviz.
    """
    # Replace common light colors with dark equivalents
    replacements = [
        ('fill="white"', 'fill="#1e1e1e"'),
        ('fill="black"', 'fill="#d4d4d4"'),
        ('stroke="black"', 'stroke="#d4d4d4"'),
        ("fill='white'", "fill='#1e1e1e'"),
        ("fill='black'", "fill='#d4d4d4'"),
        ("stroke='black'", "stroke='#d4d4d4'"),
        # Handle none background
        ('fill="none"', 'fill="none"'),  # Keep as-is
    ]

    for old, new in replacements:
        svg = svg.replace(old, new)

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

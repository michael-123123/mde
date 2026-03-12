"""Mermaid diagram rendering service with caching.

Uses mmdc (mermaid CLI) to render mermaid diagrams to SVG server-side.
Falls back to client-side mermaid.js if mmdc is not available.
"""

import hashlib
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

# In-memory cache: hash -> (svg_string, error_string or None)
_render_cache: dict[str, tuple[str, str | None]] = {}


def has_mermaid() -> bool:
    """Check if mmdc (mermaid CLI) is available on the system."""
    from fun.markdown6.tool_paths import has_mmdc
    return has_mmdc()


def clear_cache():
    """Clear the render cache."""
    _render_cache.clear()


def render_mermaid(source: str, dark_mode: bool = False) -> tuple[str, str | None]:
    """Render mermaid source to SVG.

    Args:
        source: Mermaid diagram source code
        dark_mode: Whether to use dark theme

    Returns:
        Tuple of (svg_string, error_string or None).
        If successful, error is None.
        If failed, svg_string contains error display HTML.
    """
    cache_key = hashlib.md5(f"{source}:{dark_mode}".encode()).hexdigest()

    if cache_key in _render_cache:
        return _render_cache[cache_key]

    result = _render_mermaid_impl(source, dark_mode)
    _render_cache[cache_key] = result
    return result


def _render_mermaid_impl(source: str, dark_mode: bool) -> tuple[str, str | None]:
    """Implementation of mermaid rendering via mmdc."""
    from fun.markdown6.tool_paths import get_mmdc_path

    mmdc = get_mmdc_path()
    if not mmdc:
        error = "mmdc not installed (npm install -g @mermaid-js/mermaid-cli)"
        return _format_error(source, error), error

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mmd"
            output_path = Path(tmpdir) / "output.svg"

            input_path.write_text(source, encoding="utf-8")

            theme = "dark" if dark_mode else "default"
            cmd = [
                mmdc,
                "-i", str(input_path),
                "-o", str(output_path),
                "-t", theme,
                "-b", "transparent",
                "--quiet",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "mmdc failed"
                return _format_error(source, error), error

            if not output_path.exists():
                error = "mmdc produced no output"
                return _format_error(source, error), error

            svg_string = output_path.read_text(encoding="utf-8")
            svg_string = _make_svg_responsive(svg_string)
            return svg_string, None

    except subprocess.TimeoutExpired:
        error = "Mermaid rendering timed out (15s)"
        return _format_error(source, error), error
    except Exception as e:
        error = str(e)
        return _format_error(source, error), error


def _make_svg_responsive(svg: str) -> str:
    """Set explicit pixel dimensions from viewBox so setZoomFactor can scale it.

    mmdc outputs SVGs like:
        <svg width="100%" style="max-width: 2525px; ..." viewBox="0 0 2525 888">
    width="100%" (or no width at all) makes the SVG fill its container,
    which defeats setZoomFactor — the SVG re-flows instead of scaling.

    We replace width="100%" with the actual viewBox width in pixels, strip
    max-width from inline style, and add height from viewBox. This gives
    the SVG a fixed intrinsic size that setZoomFactor can scale. The CSS
    max-width:100% on the container prevents horizontal overflow.
    """
    import re
    # Extract viewBox dimensions
    vb_match = re.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', svg)
    if vb_match:
        vb_w, vb_h = vb_match.group(1), vb_match.group(2)
        # Replace width="100%" with viewBox width, or add width if missing
        if 'width="100%"' in svg:
            svg = svg.replace('width="100%"', f'width="{vb_w}"', 1)
        elif not re.search(r'<svg[^>]*\bwidth=', svg):
            svg = svg.replace('<svg ', f'<svg width="{vb_w}" ', 1)
        # Add height if missing
        if not re.search(r'<svg[^>]*\bheight=', svg):
            svg = svg.replace('<svg ', f'<svg height="{vb_h}" ', 1)
    # Remove max-width from inline style attribute
    svg = re.sub(r'(style="[^"]*?)max-width:\s*[^;]+;?\s*', r'\1', svg, count=1)
    # Clean up empty or whitespace-only style attributes
    svg = re.sub(r'\s*style="\s*"', '', svg)
    return svg


def _format_error(source: str, error: str) -> str:
    """Format an error display with source code and error message."""
    source_escaped = html.escape(source)
    error_escaped = html.escape(error)

    return f'''<div class="mermaid-error">
<div class="mermaid-error-header">Mermaid Error</div>
<pre class="mermaid-error-source">{source_escaped}</pre>
<div class="mermaid-error-message">{error_escaped}</div>
</div>'''


def get_mermaid_css(dark_mode: bool = False) -> str:
    """Get CSS for mermaid diagrams and errors."""
    if dark_mode:
        return """
        .mermaid-diagram {
            text-align: center;
            margin: 16px 0;
        }
        .mermaid-diagram svg {
            max-width: 100%;
            height: auto;
        }
        .mermaid-error {
            background: #3a1d1d;
            border: 1px solid #f85149;
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            font-family: monospace;
        }
        .mermaid-error-header {
            color: #f85149;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .mermaid-error-source {
            background: #2d2d2d;
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            color: #d4d4d4;
            margin: 8px 0;
        }
        .mermaid-error-message {
            color: #f85149;
            font-size: 0.9em;
        }
        """
    else:
        return """
        .mermaid-diagram {
            text-align: center;
            margin: 16px 0;
        }
        .mermaid-diagram svg {
            max-width: 100%;
            height: auto;
        }
        .mermaid-error {
            background: #ffebe9;
            border: 1px solid #cf222e;
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            font-family: monospace;
        }
        .mermaid-error-header {
            color: #cf222e;
            font-weight: bold;
            margin-bottom: 8px;
        }
        .mermaid-error-source {
            background: #f6f8fa;
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            color: #24292f;
            margin: 8px 0;
        }
        .mermaid-error-message {
            color: #cf222e;
            font-size: 0.9em;
        }
        """


def get_mermaid_js() -> str:
    """Get JavaScript fallback for when mmdc is unavailable.

    Uses mermaid.js CDN to render in the browser.
    """
    return """
    <script src="https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js"></script>
    <script>
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({
                startOnLoad: true,
                theme: document.body.classList.contains('dark') ? 'dark' : 'default',
                securityLevel: 'loose'
            });
        }
    </script>
    """

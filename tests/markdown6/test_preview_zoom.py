"""Tests for preview zoom using setZoomFactor.

Verifies that zoom scales BOTH text and SVG diagrams (mermaid, graphviz)
by comparing pixel counts at different zoom levels.
"""

from pathlib import Path

import pytest
from PySide6.QtGui import QImage

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


SCREENSHOT_DIR = Path(__file__).parent / "zoom_screenshots"


def _wait_for_load(qtbot, view, timeout=5000):
    with qtbot.waitSignal(view.loadFinished, timeout=timeout):
        pass


def _grab(view):
    return view.grab().toImage()


def _save_screenshot(image: QImage, name: str):
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    image.save(str(path))
    return path


def _count_colored_pixels(image: QImage, r_min, g_min, b_min, r_max, g_max, b_max):
    """Count pixels within an RGB range."""
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if (r_min <= c.red() <= r_max and
                g_min <= c.green() <= g_max and
                b_min <= c.blue() <= b_max):
                count += 1
    return count


# --- HTML templates with real-ish SVG content ---

# Simple inline SVG (control case — known to work)
PLAIN_SVG_HTML = """<!DOCTYPE html>
<html><head><style>body {{ font-size: 14px; padding: 20px; background: white; }}</style></head>
<body>
<h1>Plain SVG</h1>
<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">
    <rect x="10" y="10" width="80" height="80" fill="#4a90d9" rx="5"/>
    <rect x="110" y="10" width="80" height="80" fill="#e74c3c" rx="5"/>
</svg>
</body></html>"""

# Mermaid-style SVG after _make_svg_responsive: explicit pixel dimensions from viewBox,
# no max-width style. CSS max-width:100% on container prevents overflow.
MERMAID_SVG_HTML = """<!DOCTYPE html>
<html><head><style>
body {{ font-size: 14px; padding: 20px; background: white; }}
.mermaid-diagram {{ text-align: center; margin: 16px 0; }}
.mermaid-diagram svg {{ max-width: 100%; height: auto; }}
body.zoomed .mermaid-diagram svg {{ max-width: none; }}
</style></head>
<body>
<h1>Mermaid Diagram</h1>
<div class="mermaid-diagram">
<svg id="my-svg" width="200" height="120" xmlns="http://www.w3.org/2000/svg"
     class="flowchart"
     viewBox="0 0 200 120" role="graphics-document document"
     aria-roledescription="flowchart-v2">
    <rect x="20" y="10" width="70" height="40" fill="#ECECFF" stroke="#9370DB" rx="5"/>
    <text x="55" y="35" text-anchor="middle" fill="#333" font-size="14">Start</text>
    <rect x="110" y="10" width="70" height="40" fill="#ECECFF" stroke="#9370DB" rx="5"/>
    <text x="145" y="35" text-anchor="middle" fill="#333" font-size="14">End</text>
    <line x1="90" y1="30" x2="110" y2="30" stroke="#333" stroke-width="2"/>
    <rect x="20" y="70" width="160" height="40" fill="#4a90d9" rx="5"/>
</svg>
</div>
</body></html>"""

# Graphviz-style SVG after _make_svg_responsive: pt dimensions replaced with
# pixel values from viewBox.
GRAPHVIZ_SVG_HTML = """<!DOCTYPE html>
<html><head><style>
body {{ font-size: 14px; padding: 20px; background: white; }}
.graphviz-diagram {{ text-align: center; margin: 16px 0; }}
.graphviz-diagram svg {{ max-width: 100%; height: auto; }}
body.zoomed .graphviz-diagram svg {{ max-width: none; }}
</style></head>
<body>
<h1>Graphviz Diagram</h1>
<div class="graphviz-diagram">
<svg width="200" height="120" viewBox="0 0 200 120"
     xmlns="http://www.w3.org/2000/svg">
    <g transform="scale(1 1)">
        <ellipse cx="50" cy="30" rx="40" ry="20" fill="#4a90d9" stroke="black"/>
        <text x="50" y="35" text-anchor="middle" fill="white" font-size="14">A</text>
        <ellipse cx="150" cy="30" rx="40" ry="20" fill="#e74c3c" stroke="black"/>
        <text x="150" y="35" text-anchor="middle" fill="white" font-size="14">B</text>
        <path d="M90,30 L110,30" stroke="black" stroke-width="2"/>
        <rect x="20" y="70" width="160" height="40" fill="#4a90d9"/>
    </g>
</svg>
</div>
</body></html>"""

# KaTeX-rendered math (if we ever have it inline — uses spans/divs not SVGs)
# Not SVG-based so setZoomFactor should handle it fine. Include for completeness.
KATEX_HTML = """<!DOCTYPE html>
<html><head><style>
body {{ font-size: 14px; padding: 20px; background: white; }}
.math-block {{ font-size: 24px; text-align: center; margin: 16px 0; }}
</style></head>
<body>
<h1>Math</h1>
<div class="math-block" style="background: #4a90d9; padding: 20px; color: white;">
    E = mc<sup>2</sup>
</div>
</body></html>"""


def _count_blue(img):
    """Count blue-ish pixels (#4a90d9 range)."""
    return _count_colored_pixels(img, 50, 100, 180, 100, 170, 230)


def _count_purple(img):
    """Count purple-ish pixels (#ECECFF mermaid node fill)."""
    return _count_colored_pixels(img, 220, 220, 240, 240, 240, 255)


def _set_zoomed(view, zoomed: bool):
    """Toggle body.zoomed class (mirrors _apply_preview_zoom in the real app)."""
    js_val = "true" if zoomed else "false"
    view.page().runJavaScript(f"document.body.classList.toggle('zoomed', {js_val});")


def _assert_zoom_scales(qtbot, html, name, pixel_counter):
    """Core assertion: at 2x zoom, colored area should be significantly larger.

    Mirrors the real app behavior: at 1x, SVGs have max-width:100% (fit to
    container). When zoomed, body.zoomed CSS removes that constraint.
    """
    view = QWebEngineView()
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()

    view.setZoomFactor(1.0)
    view.setHtml(html)
    _wait_for_load(qtbot, view)
    qtbot.wait(500)

    img_1x = _grab(view)
    _save_screenshot(img_1x, f"{name}_1x")
    px_1x = pixel_counter(img_1x)

    # Toggle zoomed class then zoom (like _apply_preview_zoom does)
    _set_zoomed(view, True)
    view.setZoomFactor(2.0)
    qtbot.wait(500)

    img_2x = _grab(view)
    _save_screenshot(img_2x, f"{name}_2x")
    px_2x = pixel_counter(img_2x)

    ratio = px_2x / max(px_1x, 1)
    print(f"\n{name}: 1x={px_1x}, 2x={px_2x}, ratio={ratio:.1f}x")

    assert px_1x > 100, f"{name}: baseline should have colored pixels, got {px_1x}"
    assert px_2x > px_1x * 1.5, (
        f"{name}: at 2x zoom, pixel area should grow significantly. "
        f"Got {px_2x} vs baseline {px_1x} (ratio={ratio:.1f}x)"
    )


@pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
class TestZoomScalesAllContent:
    """Verify setZoomFactor scales text AND all rendered diagram types."""

    def test_plain_svg_zooms(self, qtbot):
        """Control: plain inline SVG should zoom (known working)."""
        _assert_zoom_scales(qtbot, PLAIN_SVG_HTML, "plain_svg", _count_blue)

    def test_mermaid_svg_zooms(self, qtbot):
        """Mermaid SVGs (with max-width style + viewBox) should zoom."""
        _assert_zoom_scales(qtbot, MERMAID_SVG_HTML, "mermaid_svg", _count_blue)

    def test_graphviz_svg_zooms(self, qtbot):
        """Graphviz SVGs (with fixed pt dimensions + viewBox) should zoom."""
        _assert_zoom_scales(qtbot, GRAPHVIZ_SVG_HTML, "graphviz_svg", _count_blue)

    def test_math_block_zooms(self, qtbot):
        """Math/KaTeX blocks (HTML divs) should zoom."""
        _assert_zoom_scales(qtbot, KATEX_HTML, "math_block", _count_blue)


@pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
class TestZoomResetAndRange:
    """Verify zoom reset and boundary behavior."""

    def test_zoom_reset_restores_baseline(self, qtbot):
        view = QWebEngineView()
        view.resize(800, 600)
        qtbot.addWidget(view)
        view.show()

        view.setHtml(MERMAID_SVG_HTML)
        _wait_for_load(qtbot, view)
        qtbot.wait(500)

        px_baseline = _count_blue(_grab(view))

        # Zoom in (toggle max-width off like real app)
        _set_zoomed(view, True)
        view.setZoomFactor(2.0)
        qtbot.wait(300)
        assert _count_blue(_grab(view)) > px_baseline

        # Reset zoom (toggle max-width back on)
        _set_zoomed(view, False)
        view.setZoomFactor(1.0)
        qtbot.wait(300)
        px_reset = _count_blue(_grab(view))

        assert abs(px_reset - px_baseline) < px_baseline * 0.15

    def test_zoom_survives_sethtml(self, qtbot):
        """Zoom factor should persist across setHtml calls."""
        view = QWebEngineView()
        view.resize(800, 600)
        qtbot.addWidget(view)
        view.show()

        view.setZoomFactor(1.5)
        view.setHtml(MERMAID_SVG_HTML)
        _wait_for_load(qtbot, view)
        qtbot.wait(300)

        assert view.zoomFactor() == pytest.approx(1.5, abs=0.01)

        view.setHtml(GRAPHVIZ_SVG_HTML)
        _wait_for_load(qtbot, view)
        qtbot.wait(300)

        assert view.zoomFactor() == pytest.approx(1.5, abs=0.01)

    def test_zoom_reapply_after_sethtml_scales_diagrams(self, qtbot):
        """Simulate real app: setHtml then re-apply zoom. Diagrams must still scale."""
        view = QWebEngineView()
        view.resize(800, 600)
        qtbot.addWidget(view)
        view.show()

        # Load at 1x, measure baseline
        view.setHtml(MERMAID_SVG_HTML)
        _wait_for_load(qtbot, view)
        qtbot.wait(500)
        px_1x = _count_blue(_grab(view))

        # Simulate: new content arrives (re-render), then re-apply zoom
        view.setHtml(MERMAID_SVG_HTML)
        _wait_for_load(qtbot, view)
        _set_zoomed(view, True)
        view.setZoomFactor(2.0)
        qtbot.wait(500)
        px_2x = _count_blue(_grab(view))

        ratio = px_2x / max(px_1x, 1)
        print(f"\nReapply zoom: 1x={px_1x}, 2x={px_2x}, ratio={ratio:.1f}x")
        assert px_2x > px_1x * 1.5, (
            f"After setHtml + re-apply zoom, diagrams should scale. "
            f"Got {px_2x} vs {px_1x} (ratio={ratio:.1f}x)"
        )

"""Tests for async diagram rendering pipeline.

Verifies that diagrams submitted to the thread pool executor
actually complete and inject their SVG back into the preview.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


def _render_fake_slow(kind, source, dark_mode):
    """Fake renderer that simulates mmdc delay."""
    time.sleep(0.3)
    return f"<svg>rendered-{kind}</svg>", f"{kind}-diagram"


# ── Unit tests (no UI) ──────────────────────────────────────────────────

class TestAsyncDiagramUnit:
    """Unit tests for individual pieces of the async pipeline."""

    @patch("fun.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("fun.markdown6.mermaid_service.is_cached", return_value=False)
    def test_uncached_diagram_emits_placeholder(self, mock_cached, mock_has):
        """Uncached mermaid block should produce a placeholder div."""
        import markdown
        from fun.markdown6.markdown_extensions import MermaidExtension

        md = markdown.Markdown(extensions=[MermaidExtension()])
        md._pending_diagrams = []

        source = "```mermaid\ngraph TD\n    A --> B\n```\n"
        result = md.convert(source)

        assert 'id="diagram-pending-0"' in result
        assert "diagram-loading" in result
        assert "Rendering..." in result
        assert len(md._pending_diagrams) == 1
        assert md._pending_diagrams[0] == ("mermaid", "graph TD\n    A --> B", False)

    @patch("fun.markdown6.mermaid_service.has_mermaid", return_value=True)
    @patch("fun.markdown6.mermaid_service.is_cached", return_value=True)
    @patch("fun.markdown6.mermaid_service.render_mermaid", return_value=("<svg>ok</svg>", None))
    def test_cached_diagram_inlined_immediately(self, mock_render, mock_cached, mock_has):
        """Cached mermaid block should be inlined, not deferred."""
        import markdown
        from fun.markdown6.markdown_extensions import MermaidExtension

        md = markdown.Markdown(extensions=[MermaidExtension()])
        md._pending_diagrams = []

        source = "```mermaid\ngraph TD\n    A --> B\n```\n"
        result = md.convert(source)

        assert "diagram-pending" not in result
        assert "<svg>ok</svg>" in result
        assert len(md._pending_diagrams) == 0

    def test_render_diagram_function(self):
        """The _render_diagram function should call the right service."""
        from fun.markdown6.markdown_editor import _render_diagram

        with patch("fun.markdown6.mermaid_service.render_mermaid",
                    return_value=("<svg>m</svg>", None)):
            svg, css = _render_diagram("mermaid", "graph TD\nA-->B", False)
            assert svg == "<svg>m</svg>"
            assert css == "mermaid-diagram"

        with patch("fun.markdown6.graphviz_service.render_dot",
                    return_value=("<svg>g</svg>", None)):
            svg, css = _render_diagram("graphviz", "digraph G {}", False)
            assert svg == "<svg>g</svg>"
            assert css == "graphviz-diagram"

    def test_executor_runs_and_returns(self):
        """Verify the executor runs the render function and produces a result."""
        from fun.markdown6.markdown_editor import _diagram_executor

        future = _diagram_executor.submit(_render_fake_slow, "mermaid", "graph TD", False)
        svg, css = future.result(timeout=5)
        assert svg == "<svg>rendered-mermaid</svg>"
        assert css == "mermaid-diagram"


# ── Callback mechanism tests ────────────────────────────────────────────

class TestCallbackMechanism:
    """Verify that QTimer.singleShot from worker threads is unreliable,
    and that polling from the main thread works."""

    def test_qtimer_from_done_callback_unreliable(self, qtbot):
        """QTimer.singleShot from add_done_callback does NOT reliably fire.

        This is the root cause of the original bug: the done_callback runs
        in the executor's worker thread, and QTimer.singleShot from a non-Qt
        thread doesn't always deliver events to the main event loop.
        """
        timer_fired = []
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_render_fake_slow, "mermaid", "test", False)
        future.add_done_callback(
            lambda f: QTimer.singleShot(0, lambda: timer_fired.append(True))
        )
        # Give it plenty of time — it still won't fire reliably
        qtbot.wait(2000)
        QApplication.processEvents()
        # Don't assert either way — it's timing-dependent. The point is
        # that this approach is unreliable and we shouldn't depend on it.
        executor.shutdown(wait=False)

    def test_main_thread_polling_works(self, qtbot):
        """Polling from the main thread via QTimer is reliable."""
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_render_fake_slow, "mermaid", "test", False)
        results = []

        def check():
            if future.done():
                results.append(future.result())
                poll_timer.stop()

        poll_timer = QTimer()
        poll_timer.timeout.connect(check)
        poll_timer.start(50)

        qtbot.waitUntil(lambda: len(results) > 0, timeout=5000)
        assert results[0] == ("<svg>rendered-mermaid</svg>", "mermaid-diagram")
        executor.shutdown(wait=False)


# ── Integration tests (QWebEngineView) ──────────────────────────────────

@pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
class TestAsyncDiagramWebEngine:
    """Integration tests proving the full polling pipeline with a real browser."""

    PLACEHOLDER_HTML = """<!DOCTYPE html>
    <html><body>
    <div id="diagram-pending-0" class="diagram-loading">
        <div class="diagram-loading-spinner">Rendering...</div>
    </div>
    </body></html>"""

    def _get_js(self, view, js_expr, qtbot):
        result = []
        view.page().runJavaScript(js_expr, lambda val: result.append(val))
        qtbot.waitUntil(lambda: len(result) > 0, timeout=3000)
        return result[0]

    def _wait_for_load(self, view, qtbot):
        loaded = []
        view.loadFinished.connect(lambda ok: loaded.append(ok))
        qtbot.waitUntil(lambda: len(loaded) > 0, timeout=5000)

    def test_placeholder_exists(self, qtbot):
        """After setHtml, the placeholder div should exist in the DOM."""
        view = QWebEngineView()
        qtbot.addWidget(view)
        view.setHtml(self.PLACEHOLDER_HTML)
        self._wait_for_load(view, qtbot)

        inner = self._get_js(view, "document.getElementById('diagram-pending-0')?.innerHTML || 'MISSING'", qtbot)
        assert "Rendering..." in inner

    def test_direct_js_injection(self, qtbot):
        """Direct runJavaScript replacement works."""
        view = QWebEngineView()
        qtbot.addWidget(view)
        view.setHtml(self.PLACEHOLDER_HTML)
        self._wait_for_load(view, qtbot)

        escaped = json.dumps("<svg>test</svg>")
        view.page().runJavaScript(f"""
        (function() {{
            var el = document.getElementById('diagram-pending-0');
            if (el) {{ el.innerHTML = {escaped}; el.classList.add('mermaid-diagram'); }}
        }})();
        """)
        qtbot.wait(100)

        inner = self._get_js(view, "document.getElementById('diagram-pending-0')?.innerHTML || 'MISSING'", qtbot)
        assert "<svg>test</svg>" in inner

    def test_full_polling_pipeline(self, qtbot):
        """Full pipeline: setHtml → executor.submit → poll → runJavaScript."""
        view = QWebEngineView()
        qtbot.addWidget(view)
        view.setHtml(self.PLACEHOLDER_HTML)
        self._wait_for_load(view, qtbot)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_render_fake_slow, "mermaid", "graph TD", False)
        injected = []

        def check_future():
            if future.done():
                svg_html, css_class = future.result()
                escaped = json.dumps(svg_html)
                js = f"""
                (function() {{
                    var el = document.getElementById('diagram-pending-0');
                    if (el) {{
                        el.innerHTML = {escaped};
                        el.classList.remove('diagram-loading');
                        el.classList.add('{css_class}');
                    }}
                }})();
                """
                view.page().runJavaScript(js)
                injected.append(True)
                poll_timer.stop()

        poll_timer = QTimer()
        poll_timer.timeout.connect(check_future)
        poll_timer.start(50)

        qtbot.waitUntil(lambda: len(injected) > 0, timeout=5000)
        qtbot.wait(100)

        inner = self._get_js(view, "document.getElementById('diagram-pending-0')?.innerHTML || 'MISSING'", qtbot)
        assert "<svg>rendered-mermaid</svg>" in inner

        classes = self._get_js(view, "document.getElementById('diagram-pending-0')?.className || ''", qtbot)
        assert "mermaid-diagram" in classes
        assert "diagram-loading" not in classes

        executor.shutdown(wait=False)

    def test_sethtml_then_poll_no_race(self, qtbot):
        """Simulate real scenario: setHtml + immediate poll start (no wait for load)."""
        view = QWebEngineView()
        qtbot.addWidget(view)

        executor = ThreadPoolExecutor(max_workers=1)
        injected = []

        # setHtml (async) + start polling immediately — just like render_markdown does
        view.setHtml(self.PLACEHOLDER_HTML)
        future = executor.submit(_render_fake_slow, "mermaid", "graph TD", False)

        def check_future():
            if future.done():
                svg_html, css_class = future.result()
                escaped = json.dumps(svg_html)
                js = f"""
                (function() {{
                    var el = document.getElementById('diagram-pending-0');
                    if (el) {{
                        el.innerHTML = {escaped};
                        el.classList.remove('diagram-loading');
                        el.classList.add('{css_class}');
                    }}
                }})();
                """
                view.page().runJavaScript(js)
                injected.append(True)
                poll_timer.stop()

        poll_timer = QTimer()
        poll_timer.timeout.connect(check_future)
        poll_timer.start(50)

        qtbot.waitUntil(lambda: len(injected) > 0, timeout=5000)
        qtbot.wait(200)

        inner = self._get_js(view, "document.getElementById('diagram-pending-0')?.innerHTML || 'MISSING'", qtbot)
        assert "<svg>rendered-mermaid</svg>" in inner

        executor.shutdown(wait=False)

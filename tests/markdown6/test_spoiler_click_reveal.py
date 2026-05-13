"""Real-browser reproduction: clicking a spoiler must toggle ``.revealed``.

The earlier unit tests verified that the JS *contains* the right
strings (``classList.toggle``, ``revealed``, ``addEventListener``).
They did NOT verify the JS actually runs in QWebEngineView the way it
does in mde's preview pane. The user reports clicking the spoiler in
the GUI doesn't unblur - this test pins that exact scenario:

  1. Render markdown with ``||hidden||``.
  2. Load it in a QWebEngineView (same widget mde uses for preview).
  3. Programmatically dispatch a click on the spoiler span.
  4. Assert the ``revealed`` class is now on the span.

If this test fails the JS isn't running / isn't wiring up handlers /
the click isn't reaching the span. Whichever it is, the GUI bug is
reproduced.
"""

import pytest

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

if not HAS_WEBENGINE:
    pytest.skip("QtWebEngine not available", allow_module_level=True)

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.html_renderer_core import render_html_document


def _eval_js(qtbot, view, js: str, timeout_ms: int = 5000):
    """Run JS in the view and return its value (synchronously, via qtbot)."""
    result = []
    view.page().runJavaScript(js, lambda r: result.append(r))
    qtbot.waitUntil(lambda: len(result) == 1, timeout=timeout_ms)
    return result[0]


@pytest.mark.timeout(15, method="thread")
def test_clicking_spoiler_toggles_revealed_class(qtbot):
    """The user-facing bug: clicking a spoiler in the rendered preview
    must toggle the ``revealed`` class. Without it the blur never
    clears."""
    ctx = init_app_context(ephemeral=True)
    html = render_html_document("||hidden||", ctx)

    view = QWebEngineView()
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    with qtbot.waitSignal(view.loadFinished, timeout=10000):
        view.setHtml(html)

    # Sanity: the span is in the DOM.
    count = _eval_js(qtbot, view, "document.querySelectorAll('span.spoiler').length")
    assert count == 1, "render_html_document did not produce a spoiler span"

    # Before click: revealed class should NOT be present.
    before = _eval_js(
        qtbot, view,
        "document.querySelector('span.spoiler').classList.contains('revealed')",
    )
    assert before is False, "spoiler should start blurred"

    # Dispatch a real click event on the span. This exercises the
    # actual click handler (not just calling toggle() directly).
    _eval_js(
        qtbot, view,
        """
        (function() {
            var el = document.querySelector('span.spoiler');
            el.click();
        })();
        """,
    )

    # After click: revealed class MUST be present.
    after = _eval_js(
        qtbot, view,
        "document.querySelector('span.spoiler').classList.contains('revealed')",
    )
    assert after is True, (
        "clicking the spoiler did not toggle the .revealed class - "
        "the JS handler isn't firing in QWebEngineView"
    )


@pytest.mark.timeout(15, method="thread")
def test_revealed_clears_blur_visually(qtbot):
    """Beyond the class toggle, the CSS rule must actually win - the
    computed ``filter`` value should change from a blur to ``none``
    once the ``.revealed`` class lands."""
    ctx = init_app_context(ephemeral=True)
    html = render_html_document("||hidden||", ctx)

    view = QWebEngineView()
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    with qtbot.waitSignal(view.loadFinished, timeout=10000):
        view.setHtml(html)

    # Before click: filter is a blur (computed string starts with "blur(").
    filter_before = _eval_js(
        qtbot, view,
        "getComputedStyle(document.querySelector('span.spoiler')).filter",
    )
    assert "blur" in filter_before.lower(), (
        f"expected blurry filter before click; got {filter_before!r}"
    )

    # Click and re-measure. The CSS uses transition: filter 0.15s, so
    # the computed value mid-flight can still report a blur. Wait past
    # the transition before reading.
    _eval_js(qtbot, view, "document.querySelector('span.spoiler').click()")
    qtbot.wait(250)
    filter_after = _eval_js(
        qtbot, view,
        "getComputedStyle(document.querySelector('span.spoiler')).filter",
    )
    assert "blur" not in filter_after.lower(), (
        f"after click, filter should be 'none' but is {filter_after!r}"
    )

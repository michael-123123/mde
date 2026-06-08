"""Custom URL scheme handler for preview HTML.

Bug: ``QWebEngineView.setHtml()`` percent-encodes the HTML and passes
it through a URL, which the Chromium engine caps at 2 MB. Markdown
files that produce HTML larger than that (e.g. a 4 MB exported AI
conversation log → ~5.6 MB HTML) silently render as a blank pane.

Fix: register a custom ``mde-preview://`` URL scheme and serve the
HTML from in-memory storage on request. No URL-length cap; arbitrary
HTML size works.
"""

from __future__ import annotations

import pytest
from PySide6.QtWebEngineCore import QWebEngineUrlScheme

from markdown_editor.markdown6 import preview_scheme


@pytest.mark.timeout(15, method="thread")
def test_scheme_is_registered():
    """Importing the module registers the ``mde-preview`` URL scheme.
    Qt requires registration before any ``QWebEngineProfile`` is
    constructed; doing it at module import time is the simplest way
    to honor that ordering."""
    scheme = QWebEngineUrlScheme.schemeByName(preview_scheme.SCHEME)
    assert bytes(scheme.name()) == preview_scheme.SCHEME


@pytest.mark.timeout(15, method="thread")
def test_handler_stores_html_by_key():
    """The handler holds HTML per tab key in memory."""
    handler = preview_scheme.PreviewSchemeHandler()
    handler.set_html("alpha", "<p>one</p>")
    handler.set_html("beta", "<p>two</p>")
    assert handler.get_html("alpha") == "<p>one</p>"
    assert handler.get_html("beta") == "<p>two</p>"


@pytest.mark.timeout(15, method="thread")
def test_handler_remove_clears_key():
    """Tab close calls remove() so stale HTML doesn't pile up."""
    handler = preview_scheme.PreviewSchemeHandler()
    handler.set_html("k", "<p>x</p>")
    handler.remove("k")
    assert handler.get_html("k") is None


@pytest.mark.timeout(15, method="thread")
def test_handler_holds_html_above_setHtml_cap():
    """The whole point: HTML above the 2 MB ``setHtml`` cap survives
    intact when routed through the handler."""
    big = "<p>" + "x" * (5 * 1024 * 1024) + "</p>"  # > 5 MB
    handler = preview_scheme.PreviewSchemeHandler()
    handler.set_html("big", big)
    out = handler.get_html("big")
    assert out == big
    assert len(out) > 5 * 1024 * 1024


@pytest.mark.timeout(15, method="thread")
def test_preview_url_uses_scheme():
    """``preview_url(key)`` returns the URL a QWebEngineView should
    load to fetch the HTML stored under ``key``."""
    url = preview_scheme.preview_url("tab-42")
    assert url.scheme() == preview_scheme.SCHEME.decode("ascii")
    assert url.host() == "tab-42"


@pytest.mark.timeout(15, method="thread")
def test_get_handler_is_singleton(qtbot):
    """One handler is installed on the default profile; repeat calls
    return the same instance. ``qtbot`` is just here to ensure
    ``QApplication`` exists before ``get_handler`` installs."""
    h1 = preview_scheme.get_handler()
    h2 = preview_scheme.get_handler()
    assert h1 is h2


# ──────────── DocumentTab integration ────────────


@pytest.mark.timeout(15, method="thread")
def test_document_tab_render_stores_html_via_handler(qtbot):
    """Regression for the bug: a full-reload render must route its
    HTML through the scheme handler (no more direct setHtml). The
    handler having a non-empty payload after render_markdown is the
    observable signal that the new path is in use."""
    from markdown_editor.markdown6.components.document_tab import (
        HAS_WEBENGINE,
    )
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    if not HAS_WEBENGINE:
        pytest.skip("QWebEngineView not available; the handler path only matters for it")

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    tab = editor.current_tab()
    tab._preview_needs_full_reload = True
    tab.editor.setPlainText("# Hello")
    tab.render_markdown()

    handler = preview_scheme.get_handler()
    stored = handler.get_html(tab._preview_key)
    assert stored is not None
    assert "Hello" in stored


@pytest.mark.timeout(15, method="thread")
def test_document_tab_render_handles_html_above_setHtml_cap(qtbot):
    """The bug: HTML > 2 MB silently fails when passed through
    ``QWebEngineView.setHtml``. After the fix, the handler holds the
    full payload regardless of size."""
    from markdown_editor.markdown6.components.document_tab import (
        HAS_WEBENGINE,
    )
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    if not HAS_WEBENGINE:
        pytest.skip("QWebEngineView not available; the handler path only matters for it")

    # ~3 MB of paragraph text. Markdown renders to a similar-size
    # HTML, comfortably above the 2 MB setHtml cap.
    big_md = "\n\n".join("paragraph " + "x" * 1000 for _ in range(3000))
    assert len(big_md) > 2 * 1024 * 1024

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    tab = editor.current_tab()
    tab._preview_needs_full_reload = True
    tab.editor.setPlainText(big_md)
    tab.render_markdown()

    stored = preview_scheme.get_handler().get_html(tab._preview_key)
    assert stored is not None
    assert len(stored) > 2 * 1024 * 1024, (
        f"handler must hold the full large payload; got {len(stored)} bytes"
    )


@pytest.mark.timeout(15, method="thread")
def test_document_tab_preview_url_uses_scheme(qtbot):
    """After render_markdown, the preview's URL points at the
    ``mde-preview`` scheme - that's how the handler gets invoked on
    the next page load."""
    from markdown_editor.markdown6.components.document_tab import (
        HAS_WEBENGINE,
    )
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    if not HAS_WEBENGINE:
        pytest.skip("QWebEngineView not available; the handler path only matters for it")

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    tab = editor.current_tab()
    tab._preview_needs_full_reload = True
    tab.editor.setPlainText("# Hi")
    tab.render_markdown()

    assert tab.preview.url().scheme() == preview_scheme.SCHEME.decode("ascii")

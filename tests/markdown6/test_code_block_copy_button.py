"""Tests for the copy-to-clipboard button on preview code blocks.

Each `<pre>` rendered into the preview gets an overlay button. The
button is injected by inline JS (plus a MutationObserver so incremental
`innerHTML` updates re-button). Clicking copies the block's textContent
via navigator.clipboard, falling back to execCommand('copy').

These tests cover:
- The template carries the CSS/JS markers that implement the feature.
- In a live QWebEngineView, a fenced code block actually gets a button
  in the rendered DOM.
- JS clipboard access is enabled on the WebEngine settings.
"""

import markdown
import pytest
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension

from markdown_editor.markdown6.app_context import get_app_context

try:
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False


class _Ctx:
    """Minimal stand-in for MarkdownEditor — just enough to drive
    get_html_template() against a real AppContext."""

    def __init__(self):
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor
        self.ctx = get_app_context()
        self.get_html_template = MarkdownEditor.get_html_template.__get__(self)


def _render(md_text: str) -> str:
    """Render markdown to the full preview HTML (matches MarkdownEditor setup)."""
    md = markdown.Markdown(extensions=[
        FencedCodeExtension(),
        CodeHiliteExtension(css_class="highlight", guess_lang=True),
    ])
    html_content = md.convert(md_text)
    return _Ctx().get_html_template(html_content)


class TestTemplateMarkers:
    """String-level checks that the template ships the copy-button CSS/JS."""

    def test_css_class_defined(self):
        html = _render("```python\nprint('hi')\n```")
        assert ".mde-copy-btn" in html

    def test_js_clipboard_call_present(self):
        html = _render("```\necho hi\n```")
        assert "navigator.clipboard" in html

    def test_mutation_observer_installed(self):
        html = _render("")
        assert "MutationObserver" in html

    def test_init_guard_prevents_double_install(self):
        html = _render("")
        assert "_mdeCopyInit" in html

    def test_button_icon_is_inline_svg_not_emoji(self):
        """Regression: the button icon must be inline SVG, not a color-emoji
        codepoint. Color emoji can trigger the renderer to resolve a web
        font, producing SSL handshakes on every re-render."""
        html = _render("")
        # Clipboard emoji (U+1F4CB) must not appear anywhere in the emitted page.
        assert "\U0001f4cb" not in html
        # The SVG icon marker (Feather-style copy icon uses a rect) must be present.
        assert "<svg" in html
        assert 'viewBox="0 0 24 24"' in html


@pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
class TestCopyButtonInjection:
    """Integration: load full template in a real QWebEngineView and verify
    that copy buttons appear in the DOM for each `<pre>`."""

    def _load_and_count(self, qtbot, html: str, selector: str = ".mde-copy-btn") -> int:
        view = QWebEngineView()
        qtbot.addWidget(view)
        view.show()
        qtbot.waitExposed(view)
        with qtbot.waitSignal(view.loadFinished, timeout=10000):
            view.setHtml(html)

        result = []
        view.page().runJavaScript(
            f"document.querySelectorAll('{selector}').length",
            lambda r: result.append(r),
        )
        qtbot.waitUntil(lambda: len(result) == 1, timeout=5000)
        return result[0]

    def test_fenced_code_block_gets_button(self, qtbot):
        html = _render("```python\nprint('hello')\n```")
        assert self._load_and_count(qtbot, html) == 1

    def test_plain_paragraph_gets_no_button(self, qtbot):
        html = _render("Just a sentence with no code.")
        assert self._load_and_count(qtbot, html) == 0

    def test_multiple_code_blocks_each_get_button(self, qtbot):
        md_text = (
            "```python\nprint('one')\n```\n\n"
            "Some prose.\n\n"
            "```bash\necho two\n```\n"
        )
        html = _render(md_text)
        assert self._load_and_count(qtbot, html) == 2

    def test_bare_pre_tag_gets_button(self, qtbot):
        """Raw `<pre>` in the markdown source should also get a button —
        the feature targets all `<pre>` elements, not only fenced blocks."""
        html = _render("<pre>raw preformatted</pre>")
        assert self._load_and_count(qtbot, html) == 1

    def test_button_reads_code_content(self, qtbot):
        """Clicking the button should read the `<code>` textContent. Verify
        via JS (can't reliably read the system clipboard in headless)."""
        html = _render("```\nLINE_ONE\nLINE_TWO\n```")
        view = QWebEngineView()
        qtbot.addWidget(view)
        view.show()
        qtbot.waitExposed(view)
        with qtbot.waitSignal(view.loadFinished, timeout=10000):
            view.setHtml(html)

        # Resolve the text that the handler would copy — mirror its logic
        # (pre.querySelector('code').textContent fallback to pre.textContent).
        result = []
        view.page().runJavaScript(
            """
            (function() {
                var pre = document.querySelector('#md-content pre');
                if (!pre) return null;
                var code = pre.querySelector('code');
                return (code || pre).textContent;
            })();
            """,
            lambda r: result.append(r),
        )
        qtbot.waitUntil(lambda: len(result) == 1, timeout=5000)
        assert "LINE_ONE" in result[0]
        assert "LINE_TWO" in result[0]


@pytest.mark.skipif(not HAS_WEBENGINE, reason="QWebEngineView not available")
class TestClipboardAccessEnabled:
    """The DocumentTab must enable JavascriptCanAccessClipboard on the
    WebEngine settings — without it, navigator.clipboard.writeText silently
    fails."""

    def test_setting_enabled(self, qtbot):
        from markdown_editor.markdown6.components.document_tab import \
            DocumentTab

        class FakeMainWindow:
            def __init__(self):
                from markdown_editor.markdown6.extensions.math import \
                    MathExtension
                self.ctx = get_app_context()
                self.md = markdown.Markdown(extensions=["extra", MathExtension()])

            def update_tab_title(self, tab): pass
            def update_window_title(self): pass
            def get_html_template(self, content, **kw):
                return f"<html><body>{content}</body></html>"

        tab = DocumentTab(FakeMainWindow())
        qtbot.addWidget(tab)
        settings = tab.preview.page().settings()
        assert settings.testAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard
        )

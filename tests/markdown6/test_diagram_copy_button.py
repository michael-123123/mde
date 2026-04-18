"""Tests for the copy-to-clipboard button on rendered mermaid/graphviz diagrams.

The existing code-block copy button (on `<pre>`/`.highlight`) got extended
to also install on `.mermaid-diagram` and `.graphviz-diagram` containers,
copying the container's `data-source` attribute to the clipboard. We can't
drive navigator.clipboard from pytest, so these tests assert the template
contains the wiring that makes the button appear in the browser.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def mermaid_mocks(monkeypatch):
    monkeypatch.setattr(
        "markdown_editor.markdown6.mermaid_service.has_mermaid",
        lambda: True,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.mermaid_service.is_cached",
        lambda source, dark_mode=False: False,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.mermaid_service.render_mermaid",
        lambda source, dark_mode=False: (
            '<svg class="sentinel-mermaid-svg">OK</svg>', None,
        ),
    )


@pytest.fixture
def graphviz_mocks(monkeypatch):
    monkeypatch.setattr(
        "markdown_editor.markdown6.graphviz_service.has_graphviz",
        lambda: True,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.graphviz_service.is_cached",
        lambda source, dark_mode=False: False,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.graphviz_service.render_dot",
        lambda source, dark_mode=False: (
            '<svg class="sentinel-graphviz-svg">OK</svg>', None,
        ),
    )


def _render(source: str) -> str:
    from markdown_editor.markdown6 import html_renderer_core
    from markdown_editor.markdown6.app_context import init_app_context

    ctx = init_app_context(ephemeral=True)
    return html_renderer_core.render_html_document(source, ctx)


class TestDiagramCopyButton:
    def test_css_hover_selector_targets_mermaid_and_graphviz(
        self, mermaid_mocks, graphviz_mocks,
    ):
        """The CSS must reveal the copy button on hover of diagram containers."""
        html = _render(
            "```mermaid\ngraph TD\nA-->B\n```\n\n"
            "```dot\ndigraph G { A -> B; }\n```\n"
        )
        assert ".mermaid-diagram:hover > .mde-copy-btn" in html
        assert ".graphviz-diagram:hover > .mde-copy-btn" in html

    def test_css_makes_diagram_containers_positioned(
        self, mermaid_mocks,
    ):
        """The absolutely-positioned copy button needs a positioned ancestor."""
        html = _render("```mermaid\ngraph TD\nA-->B\n```\n")
        # Accept either a combined rule or separate rules; both are equivalent.
        has_rule = (
            ".mermaid-diagram,\n                .graphviz-diagram {\n"
            "                    position: relative;" in html
            or ".mermaid-diagram {\n                    position: relative;" in html
        )
        assert has_rule, (
            "Diagram containers must have position:relative so "
            ".mde-copy-btn (absolute, top:8px right:8px) anchors inside them."
        )

    def test_js_installer_queries_diagram_containers(self, mermaid_mocks):
        """installAll() must scan for diagram containers, not just <pre>."""
        html = _render("```mermaid\ngraph TD\nA-->B\n```\n")
        assert "'.mermaid-diagram, .graphviz-diagram'" in html, (
            "installAll() must querySelectorAll diagram containers so "
            "they get a copy button injected."
        )
        assert "'Copy diagram source'" in html, (
            "Diagram buttons should use a distinct aria-label / title."
        )

    def test_js_click_handler_reads_data_source_for_diagrams(
        self, mermaid_mocks,
    ):
        """The copy handler must branch on diagram class and pull the
        source from `host.dataset.source` (HTML-unescaped)."""
        html = _render("```mermaid\ngraph TD\nA-->B\n```\n")
        assert "host.dataset.source" in html, (
            "Click handler must read `host.dataset.source` to get the "
            "diagram's original markup for copying."
        )
        assert "unescapeHtml" in html, (
            "data-source is HTML-escaped by the preprocessor; the handler "
            "must unescape before writing to the clipboard."
        )

    def test_pre_inside_diagram_loading_placeholder_is_skipped(
        self, mermaid_mocks,
    ):
        """The preprocessor's pending placeholder wraps the source in a
        <pre class="diagram-loading-source">. The code-block installer
        must skip that <pre> so the rendered diagram doesn't get two
        stacked buttons (one from the <pre>, one from the diagram div).
        """
        html = _render("```mermaid\ngraph TD\nA-->B\n```\n")
        assert ".diagram-loading" in html, (
            "sanity: test source should exercise the pending path."
        )
        assert ".closest('.diagram-loading')" in html, (
            "installAll() must skip <pre>s inside .diagram-loading to "
            "avoid double-installing buttons on pending placeholders."
        )

    def test_rendered_diagram_carries_data_source_attribute(
        self, mermaid_mocks,
    ):
        """The copy button reads `data-source`. The preprocessor (and the
        sync resolver) must preserve it on the rendered outer div."""
        html = _render('```mermaid\ngraph TD\n    A --> B\n```\n')
        assert 'class="mermaid-diagram"' in html
        assert 'data-source="' in html

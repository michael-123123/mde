"""Tests for the sync pending-diagram resolver used by exports.

When `has_mermaid()` (or `has_graphviz()`) is True but the diagram is
NOT cached, the Mermaid/Graphviz preprocessor emits a "pending
placeholder" `<div id="diagram-pending-N">` with a "Rendering..."
spinner, and appends the source to `md._pending_diagrams` for async
rendering.

In the live PREVIEW this is resolved asynchronously via JavaScript:
`document.getElementById('diagram-pending-N').innerHTML = svg`. The
JS doesn't care about attribute order on the outer div.

In EXPORTS (decision B1 in local/html-export-unify.md) there is no
browser JS runtime — `html_renderer_core._resolve_pending_diagrams`
resolves each diagram synchronously and must substitute the rendered
SVG into the HTML body before the file is written.

This test exercises that sync export path end-to-end: preprocessor
emits pending placeholder, `SourceLineExtension` mutates the outer
div (adds `data-source-line`), `_resolve_pending_diagrams` runs, the
final HTML must contain the rendered SVG and must NOT still contain
the "Rendering..." spinner text.

Mocks the actual mermaid/graphviz binaries to avoid depending on
`mmdc` / `dot` being installed in the test environment.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def mermaid_rendering_mocks(monkeypatch):
    """`has_mermaid` True + `is_cached` False — forces the preprocessor
    to emit a pending placeholder and schedule async render. The sync
    resolver then calls `render_mermaid` which we stub to return a
    sentinel SVG."""
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
def graphviz_rendering_mocks(monkeypatch):
    """`has_graphviz` True + `is_cached` False — forces pending placeholder."""
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


class TestSyncPendingDiagramResolution:
    """End-to-end: markdown with fenced mermaid/graphviz blocks →
    `render_html_document` → output HTML must contain rendered SVG
    (not the pending-placeholder spinner)."""

    def test_mermaid_pending_placeholder_is_replaced_with_svg(
        self, mermaid_rendering_mocks,
    ):
        from markdown_editor.markdown6 import html_renderer_core
        from markdown_editor.markdown6.app_context import init_app_context

        ctx = init_app_context(ephemeral=True)
        source = (
            "# Doc\n\n"
            "Some text.\n\n"
            "```mermaid\n"
            "graph TD\n"
            "    A --> B\n"
            "```\n\n"
            "More text.\n"
        )
        html = html_renderer_core.render_html_document(source, ctx)

        # The rendered SVG must appear in the output.
        assert "sentinel-mermaid-svg" in html, (
            "Sync resolver failed: placeholder was NOT replaced with "
            "rendered SVG. The exported HTML has only the pending "
            "placeholder — the browser would show 'Rendering...' forever."
        )
        # The pending-placeholder markup must NOT still be in the output.
        # Matching on the div literal (not the bare class name) so we don't
        # false-positive against the `.diagram-loading-spinner { ... }` CSS
        # rule bundled in by `mermaid_service.get_mermaid_css()`.
        assert '<div class="diagram-loading-spinner">' not in html, (
            "Placeholder's 'Rendering...' spinner div is still in the "
            "exported HTML — the sync replacement didn't happen."
        )
        assert "Rendering..." not in html, (
            "'Rendering...' text still visible in exported HTML."
        )
        assert 'id="diagram-pending-' not in html, (
            "Pending placeholder id still in exported HTML — the sync "
            "resolver never replaced the placeholder."
        )

    def test_graphviz_pending_placeholder_is_replaced_with_svg(
        self, graphviz_rendering_mocks,
    ):
        from markdown_editor.markdown6 import html_renderer_core
        from markdown_editor.markdown6.app_context import init_app_context

        ctx = init_app_context(ephemeral=True)
        source = (
            "# Doc\n\n"
            "```dot\n"
            "digraph G {\n"
            "    A -> B;\n"
            "}\n"
            "```\n"
        )
        html = html_renderer_core.render_html_document(source, ctx)

        assert "sentinel-graphviz-svg" in html, (
            "Sync resolver failed: graphviz placeholder was NOT replaced "
            "with rendered SVG."
        )
        assert '<div class="diagram-loading-spinner">' not in html
        assert "Rendering..." not in html
        assert 'id="diagram-pending-' not in html

    def test_mixed_mermaid_and_graphviz_both_replaced(
        self, mermaid_rendering_mocks, graphviz_rendering_mocks,
    ):
        """Document with BOTH a mermaid and a graphviz block — each
        placeholder must be replaced with its own rendered SVG."""
        from markdown_editor.markdown6 import html_renderer_core
        from markdown_editor.markdown6.app_context import init_app_context

        ctx = init_app_context(ephemeral=True)
        source = (
            "# Mixed\n\n"
            "```mermaid\n"
            "graph TD\n"
            "    A --> B\n"
            "```\n\n"
            "```dot\n"
            "digraph G { A -> B; }\n"
            "```\n"
        )
        html = html_renderer_core.render_html_document(source, ctx)

        assert "sentinel-mermaid-svg" in html
        assert "sentinel-graphviz-svg" in html
        assert "Rendering..." not in html
        assert 'id="diagram-pending-' not in html

    def test_placeholder_survives_source_line_attribute_injection(
        self, mermaid_rendering_mocks,
    ):
        """Regression test for the specific bug found in manual
        browser testing of `examples/EXAMPLE.md`:

        `SourceLineExtension` runs AFTER `MermaidPreprocessor` emits
        its pending placeholder. The preprocessor emits:
            `<div class="mermaid-diagram" data-source="..." id="diagram-pending-N">...`
        SourceLineExtension mutates the outer div to:
            `<div data-source-line="N" class="mermaid-diagram" data-source="..." id="diagram-pending-N">...`
        (prepending `data-source-line="N"` — changing the attribute
        order of the outer opening tag).

        A placeholder-replacement strategy that reconstructs the
        preprocessor's exact output and does a literal `.replace()`
        will NOT find a match (attribute order differs) → placeholder
        stays in the output → user sees 'Rendering...' forever.

        This test asserts that the sync resolver survives the
        data-source-line mutation.
        """
        from markdown_editor.markdown6 import html_renderer_core
        from markdown_editor.markdown6.app_context import init_app_context

        ctx = init_app_context(ephemeral=True)
        source = "```mermaid\ngraph TD\n    A --> B\n```\n"
        html = html_renderer_core.render_html_document(source, ctx)

        # Crucial assertion: SVG present, spinner absent.
        assert "sentinel-mermaid-svg" in html, (
            "Regression: sync resolver broke when SourceLineExtension "
            "prepends data-source-line to the placeholder's outer div. "
            "Likely a literal-string-reconstruct-and-replace approach "
            "that doesn't tolerate attribute-order changes."
        )
        # And crucially — confirm the data-source-line attribute WAS
        # added (so we know we're actually exercising the mutation
        # path, not a code path where SourceLineExtension didn't run).
        assert "data-source-line=" in html, (
            "SourceLineExtension did not run — this test isn't "
            "exercising the SL-mutation scenario."
        )

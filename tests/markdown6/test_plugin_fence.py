"""Tests for plugin-registered fenced-code-block renderers.

Plugins register a ``(source: str) -> str`` callback for a named
fence (``"plantuml"``, ``"chart"``, etc.). When a fenced code block
with that language tag appears in the markdown source, the framework
invokes the callback and embeds the returned HTML in the rendered
output - same conceptual mechanism as the built-in mermaid/graphviz
fences, just routed through plugins.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import markdown
import pytest

from markdown_editor.markdown6.html_renderer_core import build_markdown
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.fence import PluginFenceExtension
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_fence_stores_record() -> None:
    @plugin_api.register_fence("plantuml")
    def render(src):
        return f"<svg>{src}</svg>"
    [rec] = plugin_api._REGISTRY.fences()
    assert rec.name == "plantuml"
    assert rec.callback is render


def test_register_fence_returns_original_function() -> None:
    @plugin_api.register_fence("x")
    def render(src):
        return src
    assert render("hi") == "hi"


def test_register_fence_stamps_plugin_name(tmp_path: Path) -> None:
    (tmp_path / "fenceplug").mkdir()
    (tmp_path / "fenceplug" / "fenceplug.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "fenceplug"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "fenceplug" / "fenceplug.py").write_text(textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import register_fence
        @register_fence("plantuml")
        def render(src):
            return "<svg/>"
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [rec] = plugin_api._REGISTRY.fences()
    assert rec.plugin_name == "fenceplug"


def test_register_fence_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        @plugin_api.register_fence("")
        def render(src):
            return ""


def test_register_fence_duplicate_name_raises() -> None:
    @plugin_api.register_fence("dup")
    def first(src):
        return ""
    with pytest.raises(ValueError, match="dup"):
        @plugin_api.register_fence("dup")
        def second(src):
            return ""


# ---------------------------------------------------------------------------
# Render integration
# ---------------------------------------------------------------------------


def _md_with_plugin_fences(disabled: set[str] | None = None) -> markdown.Markdown:
    """Build a markdown converter with the PluginFenceExtension wired in."""
    return build_markdown(extra_extensions=[
        PluginFenceExtension(disabled=disabled or set()),
    ])


def test_registered_fence_is_rendered_via_callback() -> None:
    @plugin_api.register_fence("plantuml")
    def render(src):
        return f"<plantuml-svg>{src.strip()}</plantuml-svg>"

    md = _md_with_plugin_fences()
    out = md.convert("```plantuml\nfoo->bar\n```")
    assert "<plantuml-svg>foo->bar</plantuml-svg>" in out


def test_unregistered_fence_unchanged() -> None:
    md = _md_with_plugin_fences()
    out = md.convert("```text\nplain body content\n```")
    # text is unknown to our plugin extension; it should fall through
    # to the builtin fenced-code handler (a <pre><code> block).
    assert "plain body content" in out
    assert "<plantuml" not in out


def test_disabled_plugin_fence_not_invoked() -> None:
    calls = []

    @plugin_api.register_fence("plantuml", _plugin_name="off_plug")
    def render(src):
        calls.append(src)
        return "<should-not-appear/>"

    md = _md_with_plugin_fences(disabled={"off_plug"})
    out = md.convert("```plantuml\nfoo\n```")
    assert calls == []
    assert "<should-not-appear" not in out


def test_failing_callback_falls_back_to_raw_fence(caplog) -> None:
    @plugin_api.register_fence("crashy")
    def render(src):
        raise RuntimeError("plantuml crashed")

    md = _md_with_plugin_fences()
    out = md.convert("```crashy\nbroken\n```")
    # Plugin's HTML is NOT embedded; the source is still visible
    # (the framework leaves the original fence in place so the user
    # can see what went wrong)
    assert "broken" in out
    assert any("plantuml crashed" in r.getMessage() for r in caplog.records)


def test_multiple_fences_in_same_document() -> None:
    @plugin_api.register_fence("aaa")
    def a(src):
        return f"<A>{src.strip()}</A>"

    @plugin_api.register_fence("bbb")
    def b(src):
        return f"<B>{src.strip()}</B>"

    md = _md_with_plugin_fences()
    out = md.convert(
        "First:\n\n```aaa\none\n```\n\nSecond:\n\n```bbb\ntwo\n```\n"
    )
    assert "<A>one</A>" in out
    assert "<B>two</B>" in out


def test_indented_code_blocks_not_rewritten() -> None:
    """Sanity: a plugin fence with the same name as some code shouldn't
    rewrite indented code blocks (only fenced ones)."""
    @plugin_api.register_fence("xxx")
    def render(src):
        return "<replaced/>"

    md = _md_with_plugin_fences()
    out = md.convert("    xxx\n    body\n")   # indented code block
    assert "<replaced" not in out

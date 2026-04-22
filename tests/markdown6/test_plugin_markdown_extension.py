"""Tests for plugin-registered Python-Markdown extensions.

A plugin can ship a ``markdown.Extension`` (preprocessor /
postprocessor / inline pattern / etc.) and have it transparently added
to the editor's preview + export pipeline. Disabled plugins'
extensions are excluded; toggling causes the markdown converter to
be rebuilt so changes take effect immediately.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from markdown import Extension
from markdown.preprocessors import Preprocessor

from markdown_editor.markdown6.html_renderer_core import build_markdown
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


# ---------------------------------------------------------------------------
# Tiny Extension fixture: replaces "REPLACE_ME" with "REPLACED"
# ---------------------------------------------------------------------------


class _ReplacePre(Preprocessor):
    def run(self, lines):
        return [line.replace("REPLACE_ME", "REPLACED") for line in lines]


class _ReplaceExt(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(_ReplacePre(md), "_replace_me", 25)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_markdown_extension_stores_record() -> None:
    ext = _ReplaceExt()
    plugin_api.register_markdown_extension(ext)
    extensions = plugin_api._REGISTRY.markdown_extensions()
    assert len(extensions) == 1
    assert extensions[0].extension is ext


def test_registration_stamps_plugin_name(tmp_path: Path) -> None:
    """The same _CURRENT_PLUGIN_NAME context used by other registration
    decorators must apply here too - needed for live disable filtering."""
    (tmp_path / "extplug").mkdir()
    (tmp_path / "extplug" / "extplug.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "extplug"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "extplug" / "extplug.py").write_text(textwrap.dedent("""
        from markdown import Extension
        from markdown.preprocessors import Preprocessor
        from markdown_editor.markdown6.plugins.api import register_markdown_extension

        class _Pre(Preprocessor):
            def run(self, lines):
                return [l.upper() for l in lines]

        class _Ext(Extension):
            def extendMarkdown(self, md):
                md.preprocessors.register(_Pre(md), "_upper", 25)

        register_markdown_extension(_Ext())
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [rec] = plugin_api._REGISTRY.markdown_extensions()
    assert rec.plugin_name == "extplug"


# ---------------------------------------------------------------------------
# build_markdown extra_extensions parameter
# ---------------------------------------------------------------------------


def test_build_markdown_accepts_extra_extensions() -> None:
    md = build_markdown(extra_extensions=[_ReplaceExt()])
    out = md.convert("This is REPLACE_ME inline")
    assert "REPLACED" in out
    assert "REPLACE_ME" not in out


def test_build_markdown_without_extras_is_unaffected() -> None:
    md = build_markdown()
    out = md.convert("This is REPLACE_ME inline")
    assert "REPLACE_ME" in out


# ---------------------------------------------------------------------------
# Disable filtering
# ---------------------------------------------------------------------------


def test_active_extensions_skips_disabled_plugins() -> None:
    plugin_api.register_markdown_extension(_ReplaceExt(), _plugin_name="active_plug")
    plugin_api.register_markdown_extension(_ReplaceExt(), _plugin_name="off_plug")

    active = plugin_api._REGISTRY.active_markdown_extensions(disabled={"off_plug"})
    assert len(active) == 1


def test_active_extensions_no_disabled_returns_all() -> None:
    plugin_api.register_markdown_extension(_ReplaceExt(), _plugin_name="a")
    plugin_api.register_markdown_extension(_ReplaceExt(), _plugin_name="b")
    active = plugin_api._REGISTRY.active_markdown_extensions(disabled=set())
    assert len(active) == 2

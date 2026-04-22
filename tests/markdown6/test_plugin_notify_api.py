"""Tests for the plugin-authored ``notify_*`` API.

Plugins push their own notifications (non-error: "export complete",
"cache rebuilt", etc.) via three thin helpers in the public shim.
Source defaults to the loader-managed current plugin name so
notifications group correctly in the drawer; plugin authors can
override with an explicit ``source=``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import markdown_editor.plugins as shim
from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.notifications import Severity
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_current_plugin_name("")
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_current_plugin_name("")


# ---------------------------------------------------------------------------
# Shim exports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["notify_info", "notify_warning", "notify_error"])
def test_shim_exports_notify_helpers(name: str) -> None:
    assert hasattr(shim, name), f"shim missing {name!r}"
    assert name in shim.__all__


# ---------------------------------------------------------------------------
# Direct calls (no loader context) - explicit source required
# ---------------------------------------------------------------------------


def test_notify_info_posts_to_center(ctx) -> None:
    shim.notify_info("Hello", "World", source="manual")
    [n] = ctx.notifications.all()
    assert n.title == "Hello"
    assert n.message == "World"
    assert n.severity is Severity.INFO
    assert n.source == "manual"


def test_notify_warning_severity(ctx) -> None:
    shim.notify_warning("Heads up", "watch out", source="manual")
    [n] = ctx.notifications.all()
    assert n.severity is Severity.WARNING


def test_notify_error_severity(ctx) -> None:
    shim.notify_error("Oops", "details", source="manual")
    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR


# ---------------------------------------------------------------------------
# Auto-stamping source from loader context
# ---------------------------------------------------------------------------


def test_notify_inside_plugin_import_auto_stamps_source(ctx, tmp_path: Path) -> None:
    """When a plugin's `.py` calls notify_* during import (via the
    loader), the source defaults to ``plugin:<plugin_name>``."""
    (tmp_path / "talky").mkdir()
    (tmp_path / "talky" / "talky.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "talky"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "talky" / "talky.py").write_text(textwrap.dedent("""
        from markdown_editor.plugins import notify_info
        notify_info("Loaded", "talky says hi")
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    [n] = ctx.notifications.all()
    assert n.title == "Loaded"
    assert n.source == "plugin:talky"


def test_explicit_source_overrides_auto_stamp(ctx) -> None:
    """An explicit source= argument wins over the loader auto-stamp."""
    plugin_api._set_current_plugin_name("talky")
    try:
        shim.notify_info("Hello", source="custom-source")
    finally:
        plugin_api._set_current_plugin_name("")
    [n] = ctx.notifications.all()
    assert n.source == "custom-source"


def test_notify_outside_loader_with_no_source_uses_generic_label(ctx) -> None:
    """Code calling notify_* outside any loader context AND without an
    explicit source still posts - just with an empty source string."""
    shim.notify_info("Hello")
    [n] = ctx.notifications.all()
    assert n.title == "Hello"
    assert n.source == ""


# ---------------------------------------------------------------------------
# Sanity: notify_* has no Qt types in its surface
# ---------------------------------------------------------------------------


def test_notify_helpers_take_only_strings(ctx) -> None:
    """Sanity that the API surface stays Qt-free per the design rule."""
    shim.notify_info(title="t", message="m", source="s")
    shim.notify_warning(title="t", message="m", source="s")
    shim.notify_error(title="t", message="m", source="s")
    assert len(ctx.notifications.all()) == 3

"""Tests for plugin-registered sidebar panels.

A plugin declares a panel with an id, a label (header text), an icon
(emoji shown in the activity bar), and a factory function that returns
a ``QWidget`` to live in the sidebar's stacked widget. The framework
calls the factory once at editor startup, adds the result to the
sidebar via ``Sidebar.addPanel``, and tracks the index so disable can
hide both the activity-bar tab and the panel itself.

Unlike actions/transforms, plugin panels DO require Qt code (the
factory must return a QWidget) — building UI is intrinsically
Qt-tied. The framework still keeps the plugin's *registration* API
Qt-free (no Qt types in `register_panel(...)`), but the factory's
return value crosses into Qt. This trade-off is documented in
plan.md's "Qt exposure rule" section.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.sidebar import Sidebar
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.editor_integration import (
    install_plugin_panels,
)
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
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_panel_decorator_stores_record() -> None:
    @plugin_api.register_panel(id="wc", label="Word Count", icon="📊")
    def make():
        return None   # not invoked here; just verifying registration

    [rec] = plugin_api._REGISTRY.panels()
    assert rec.id == "wc"
    assert rec.label == "Word Count"
    assert rec.icon == "📊"
    assert rec.factory is make


def test_register_panel_returns_original_function(qtbot) -> None:
    @plugin_api.register_panel(id="x", label="X", icon="•")
    def make():
        w = QLabel("y")
        qtbot.addWidget(w)
        return w
    assert isinstance(make(), QLabel)


def test_register_panel_stamps_plugin_name(qtbot, tmp_path: Path) -> None:
    (tmp_path / "panplug").mkdir()
    (tmp_path / "panplug" / "panplug.toml").write_text(textwrap.dedent("""
        [plugin]
        name = "panplug"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "panplug" / "panplug.py").write_text(textwrap.dedent("""
        from PySide6.QtWidgets import QLabel
        from markdown_editor.markdown6.plugins.api import register_panel

        @register_panel(id="x", label="X", icon="*")
        def make():
            return QLabel("body")
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [rec] = plugin_api._REGISTRY.panels()
    assert rec.plugin_name == "panplug"


def test_register_panel_duplicate_id_raises() -> None:
    @plugin_api.register_panel(id="dup", label="A", icon="a")
    def first():
        return None
    with pytest.raises(ValueError, match="dup"):
        @plugin_api.register_panel(id="dup", label="B", icon="b")
        def second():
            return None


# ---------------------------------------------------------------------------
# install_plugin_panels — wires registered panels into a Sidebar
# ---------------------------------------------------------------------------


def test_install_adds_panel_to_sidebar(qtbot, ctx) -> None:
    sidebar = Sidebar(ctx)
    qtbot.addWidget(sidebar)
    initial = sidebar.activity_bar.tabCount()

    @plugin_api.register_panel(id="wc", label="Word Count", icon="📊")
    def make():
        w = QLabel("WC body")
        return w

    install_plugin_panels(sidebar, plugin_api._REGISTRY, disabled=set())

    assert sidebar.activity_bar.tabCount() == initial + 1
    assert sidebar.activity_bar.isTabVisible(initial) is True


def test_install_skips_disabled_plugin_panels(qtbot, ctx) -> None:
    sidebar = Sidebar(ctx)
    qtbot.addWidget(sidebar)
    initial = sidebar.activity_bar.tabCount()

    @plugin_api.register_panel(
        id="off", label="Off", icon="✗", _plugin_name="off_plug",
    )
    def make():
        return QLabel("hidden")

    install_plugin_panels(sidebar, plugin_api._REGISTRY, disabled={"off_plug"})

    # Panel WAS added (so toggle can reveal it later) but its tab is hidden.
    assert sidebar.activity_bar.tabCount() == initial + 1
    assert sidebar.activity_bar.isTabVisible(initial) is False


def test_install_factory_exception_logged_and_skipped(qtbot, ctx, caplog) -> None:
    sidebar = Sidebar(ctx)
    qtbot.addWidget(sidebar)
    initial = sidebar.activity_bar.tabCount()

    @plugin_api.register_panel(id="bad", label="Bad", icon="!")
    def make():
        raise RuntimeError("plugin panel factory failed")

    install_plugin_panels(sidebar, plugin_api._REGISTRY, disabled=set())

    # Panel was NOT installed (factory failed) — no new tab.
    assert sidebar.activity_bar.tabCount() == initial
    assert any("plugin panel factory failed" in r.getMessage() for r in caplog.records)


def test_install_factory_returning_non_widget_logged_and_skipped(qtbot, ctx, caplog) -> None:
    sidebar = Sidebar(ctx)
    qtbot.addWidget(sidebar)
    initial = sidebar.activity_bar.tabCount()

    @plugin_api.register_panel(id="bad", label="Bad", icon="!")
    def make():
        return "not a widget"

    install_plugin_panels(sidebar, plugin_api._REGISTRY, disabled=set())

    assert sidebar.activity_bar.tabCount() == initial
    assert any("QWidget" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Live disable: setPanelVisible flips visibility of installed panels
# ---------------------------------------------------------------------------


def test_setPanelVisible_hides_tab_and_panel(qtbot, ctx) -> None:
    sidebar = Sidebar(ctx)
    qtbot.addWidget(sidebar)

    @plugin_api.register_panel(id="x", label="X", icon="x")
    def make():
        return QLabel("body")

    install_plugin_panels(sidebar, plugin_api._REGISTRY, disabled=set())
    new_index = sidebar.activity_bar.tabCount() - 1

    sidebar.setPanelVisible(new_index, False)
    assert sidebar.activity_bar.isTabVisible(new_index) is False

    sidebar.setPanelVisible(new_index, True)
    assert sidebar.activity_bar.isTabVisible(new_index) is True

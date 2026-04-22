"""Tests for live enable/disable of loaded plugins.

When the user toggles a plugin in Settings → Plugins and clicks Apply,
the change must take effect immediately for in-memory plugins — the
menu entries should be hidden and the palette commands should vanish,
without requiring an editor restart.

Re-enabling a plugin that wasn't loaded this session still requires a
restart (its code isn't in memory); that's covered by a separate
test.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import textwrap
from PySide6.QtWidgets import QMainWindow, QPlainTextEdit

from markdown_editor.markdown6.components.command_palette import Command
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.editor_integration import (
    apply_disabled_set,
    inject_plugin_actions,
    plugin_palette_commands_filtered,
)
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginRegistry,
    PluginTextTransform,
)


# ---------------------------------------------------------------------------
# Fixture plugin dir used by several tests
# ---------------------------------------------------------------------------


def _make_plugin_dir(root: Path, name: str, body: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.toml").write_text(textwrap.dedent(f"""
        [tool.mde.plugin]
        name = "{name}"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (d / f"{name}.py").write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


def _make_window(qtbot) -> QMainWindow:
    win = QMainWindow()
    qtbot.addWidget(win)
    return win


def _action_by_text(menu, text):
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


def _find_top_menu(window, title: str):
    for a in window.menuBar().actions():
        m = a.menu()
        if m and m.title().replace("&", "") == title:
            return m
    return None


# ---------------------------------------------------------------------------
# Registration records carry their plugin name
# ---------------------------------------------------------------------------


def test_plugin_action_has_plugin_name_field() -> None:
    a = PluginAction(id="x", label="x", plugin_name="foo", callback=lambda: None)
    assert a.plugin_name == "foo"


def test_plugin_text_transform_has_plugin_name_field() -> None:
    t = PluginTextTransform(id="x", label="x", plugin_name="foo", transform=lambda s: s)
    assert t.plugin_name == "foo"


def test_loader_stamps_plugin_name_on_registrations(tmp_path: Path) -> None:
    """When the loader imports a plugin's .py and the plugin calls
    register_action / register_text_transform, the registrations must
    be stamped with the loading plugin's name."""
    _make_plugin_dir(tmp_path, "myplug", textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import (
            register_action, register_text_transform,
        )

        @register_action(id="myplug.a1", label="Action1")
        def a1():
            pass

        @register_text_transform(id="myplug.t1", label="T1")
        def t1(text):
            return text
    """))
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    [a] = plugin_api._REGISTRY.actions()
    [t] = plugin_api._REGISTRY.text_transforms()
    assert a.plugin_name == "myplug"
    assert t.plugin_name == "myplug"


# ---------------------------------------------------------------------------
# inject_plugin_actions groups QActions by plugin name
# ---------------------------------------------------------------------------


def test_inject_groups_actions_by_plugin(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p1.a", label="P1 Action", plugin_name="p1", callback=lambda: None,
    ))
    registry.register_text_transform(PluginTextTransform(
        id="p1.t", label="P1 Transform", plugin_name="p1",
        transform=lambda s: s,
    ))
    registry.register_action(PluginAction(
        id="p2.a", label="P2 Action", plugin_name="p2", callback=lambda: None,
    ))

    inject_plugin_actions(win, registry, [])

    groups = win._mde_plugin_actions_by_name   # populated by inject
    assert set(groups) == {"p1", "p2"}
    assert len(groups["p1"]) == 2
    assert len(groups["p2"]) == 1


# ---------------------------------------------------------------------------
# apply_disabled_set hides + greys actions for disabled plugins
# ---------------------------------------------------------------------------


def test_disable_hides_plugin_menu_entries(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="p.t", label="Transform", plugin_name="p", transform=lambda s: s,
    ))
    inject_plugin_actions(win, registry, [])

    plugins_menu = _find_top_menu(win, "Plugins")
    action = _action_by_text(plugins_menu, "Transform")
    assert action.isVisible() is True
    assert action.isEnabled() is True

    apply_disabled_set(win, {"p"})

    assert action.isVisible() is False
    assert action.isEnabled() is False


def test_reenable_restores_plugin_menu_entries(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="p.t", label="Transform", plugin_name="p", transform=lambda s: s,
    ))
    inject_plugin_actions(win, registry, [])
    plugins_menu = _find_top_menu(win, "Plugins")
    action = _action_by_text(plugins_menu, "Transform")

    apply_disabled_set(win, {"p"})
    assert action.isVisible() is False

    apply_disabled_set(win, set())
    assert action.isVisible() is True
    assert action.isEnabled() is True


def test_disable_one_plugin_leaves_others_alone(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="a.x", label="Alpha", plugin_name="a", callback=lambda: None,
    ))
    registry.register_action(PluginAction(
        id="b.x", label="Beta", plugin_name="b", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    plugins_menu = _find_top_menu(win, "Plugins")
    alpha = _action_by_text(plugins_menu, "Alpha")
    beta = _action_by_text(plugins_menu, "Beta")

    apply_disabled_set(win, {"a"})
    assert alpha.isVisible() is False
    assert beta.isVisible() is True


# ---------------------------------------------------------------------------
# Palette command filtering
# ---------------------------------------------------------------------------


def test_palette_commands_filtered_excludes_disabled(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="a.x", label="Alpha", plugin_name="a", callback=lambda: None,
    ))
    registry.register_action(PluginAction(
        id="b.x", label="Beta", plugin_name="b", callback=lambda: None,
    ))
    commands: list[Command] = []
    inject_plugin_actions(win, registry, commands)

    assert {c.id for c in commands} == {"a.x", "b.x"}

    # Filter produces a subset with disabled plugins removed
    filtered = plugin_palette_commands_filtered(win, disabled={"a"})
    assert {c.id for c in filtered} == {"b.x"}


def test_palette_commands_filtered_empty_disabled_returns_all(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="a.x", label="Alpha", plugin_name="a", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    filtered = plugin_palette_commands_filtered(win, disabled=set())
    assert {c.id for c in filtered} == {"a.x"}


# ---------------------------------------------------------------------------
# Triggering a disabled plugin's action is a no-op
# ---------------------------------------------------------------------------


def test_disabled_plugin_still_imports_so_reenable_works(tmp_path: Path) -> None:
    """A plugin disabled at startup must still be imported, so its
    actions exist in memory and can be revealed without a restart
    when the user re-enables it in Settings → Plugins."""
    _make_plugin_dir(tmp_path, "zap", textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import register_text_transform

        @register_text_transform(id="zap.up", label="UpperZap")
        def up(text):
            return text.upper()
    """))
    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled={"zap"})
    [p] = plugins
    from markdown_editor.markdown6.plugins.plugin import PluginStatus
    assert p.status == PluginStatus.DISABLED_BY_USER
    assert p.module is not None           # loaded despite being disabled
    # And the registration made it into the global registry
    ids = [t.id for t in plugin_api._REGISTRY.text_transforms()]
    assert "zap.up" in ids


def test_startup_disabled_plugin_can_be_reenabled_live(qtbot, tmp_path: Path) -> None:
    """Full path: plugin disabled at startup, then re-enabled live."""
    from markdown_editor.markdown6.plugins.plugin import PluginStatus

    _make_plugin_dir(tmp_path, "zap", textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import register_text_transform

        @register_text_transform(id="zap.up", label="UpperZap")
        def up(text):
            return text.upper()
    """))
    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled={"zap"})
    assert plugins[0].status == PluginStatus.DISABLED_BY_USER

    win = _make_window(qtbot)
    inject_plugin_actions(win, plugin_api.get_registry(), [])
    apply_disabled_set(win, {"zap"})

    plugins_menu = _find_top_menu(win, "Plugins")
    action = _action_by_text(plugins_menu, "UpperZap")
    assert action is not None
    assert action.isVisible() is False

    # User removes "zap" from plugins.disabled and clicks Apply
    apply_disabled_set(win, set())
    assert action.isVisible() is True
    assert action.isEnabled() is True


def test_disable_hides_empty_plugin_submenu(qtbot) -> None:
    """When all actions under a plugin-created submenu are hidden,
    the submenu node itself should also be hidden — no empty dropdowns.
    Tests the plain (Plugins-namespaced) path here; the same logic
    handles ``/Edit/Transform`` escape-hatch submenus identically.
    """
    win = _make_window(qtbot)

    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="p.t", label="Transform", plugin_name="p", menu="Transform",
        transform=lambda s: s,
    ))
    inject_plugin_actions(win, registry, [])

    plugins = _find_top_menu(win, "Plugins")
    transform_menu_action = next(
        (a for a in plugins.actions()
         if a.menu() and a.menu().title() == "Transform"),
        None,
    )
    assert transform_menu_action is not None
    assert transform_menu_action.isVisible() is True

    apply_disabled_set(win, {"p"})
    assert transform_menu_action.isVisible() is False

    apply_disabled_set(win, set())
    assert transform_menu_action.isVisible() is True


def test_disable_does_not_hide_editor_builtin_submenu(qtbot) -> None:
    """Pre-existing non-plugin menus must NEVER be hidden by apply_disabled_set,
    even if all of their (plugin) contents are."""
    from PySide6.QtWidgets import QMenu
    from markdown_editor.markdown6.plugins.editor_integration import (
        register_existing_menu,
    )
    win = _make_window(qtbot)
    edit = QMenu("&Edit", win)
    win.menuBar().addMenu(edit)
    win._edit_ref = edit
    register_existing_menu(win, "Edit", edit)

    # A plugin puts an action directly in Edit (no submenu).
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="A", plugin_name="p", menu="Edit", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    edit_action_on_bar = next(
        (a for a in win.menuBar().actions() if a.menu() is edit),
        None,
    )
    assert edit_action_on_bar is not None
    assert edit_action_on_bar.isVisible() is True

    apply_disabled_set(win, {"p"})
    # Edit must remain visible — it's a pre-existing menu, not plugin-created.
    assert edit_action_on_bar.isVisible() is True


def test_disabled_plugin_action_does_nothing_if_invoked(qtbot) -> None:
    """Belt-and-suspenders: even if something manages to trigger a
    disabled plugin's QAction (e.g. stale keyboard shortcut), the
    callback must not run."""
    win = _make_window(qtbot)
    calls = []
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="A", plugin_name="p",
        callback=lambda: calls.append("ran"),
    ))
    inject_plugin_actions(win, registry, [])
    plugins_menu = _find_top_menu(win, "Plugins")
    action = _action_by_text(plugins_menu, "A")

    apply_disabled_set(win, {"p"})
    action.trigger()
    # setEnabled(False) blocks trigger() in Qt, so callback never runs.
    assert calls == []

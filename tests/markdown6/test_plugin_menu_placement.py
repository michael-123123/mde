"""Tests for the menu-placement design.

Default placement: every plugin's ``menu="..."`` lands under a top-level
``Plugins`` menu, which always exists and sits just before ``Help`` on
the menu bar.

Escape hatch: ``menu="/X/Y/..."`` (leading slash) opts out of the
``Plugins/`` namespace and inserts directly into the editor's real
top-level menus. The escape hatch *requires* a ``place=`` argument
explaining where in the target menu the action should land.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.editor_integration import (
    inject_plugin_actions,
    register_existing_menu,
    resolve_menu_path,
)
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginRegistry,
    PluginTextTransform,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_window(qtbot, pre_menus=None) -> QMainWindow:
    """Create a QMainWindow with named pre-existing menus + their actions.

    ``pre_menus`` is a list of ``(menu_name, [action_id, ...])`` pairs.
    Each named action becomes a QAction in the menu with its objectName
    set to the action_id (so the placement helpers can find anchors via
    that id).
    """
    win = QMainWindow()
    qtbot.addWidget(win)
    win._test_menus = {}
    win._test_actions = {}
    for name, action_ids in (pre_menus or []):
        m = QMenu(name, win)
        win.menuBar().addMenu(m)
        win._test_menus[name.replace("&", "")] = m
        register_existing_menu(win, name.replace("&", ""), m)
        for aid in action_ids:
            qa = QAction(aid, win)
            qa.setObjectName(aid)
            m.addAction(qa)
            win._test_actions[aid] = qa
    return win


def _menu_titles(menubar) -> list[str]:
    return [
        a.menu().title().replace("&", "")
        for a in menubar.actions()
        if a.menu() is not None
    ]


def _menu_action_texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions() if a.text()]


def _find_menu(menubar, title: str) -> QMenu | None:
    for a in menubar.actions():
        m = a.menu()
        if m and m.title().replace("&", "") == title:
            return m
    return None


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


# ---------------------------------------------------------------------------
# Default namespacing under "Plugins"
# ---------------------------------------------------------------------------


def test_empty_menu_path_lands_under_top_level_plugins(qtbot) -> None:
    win = _make_window(qtbot)
    menu = resolve_menu_path(win, "")
    assert menu.title() == "Plugins"
    # The Plugins menu must be a top-level item of the menubar
    assert _find_menu(win.menuBar(), "Plugins") is menu


def test_simple_path_namespaced_under_plugins(qtbot) -> None:
    win = _make_window(qtbot)
    menu = resolve_menu_path(win, "Foo")
    plugins = _find_menu(win.menuBar(), "Plugins")
    assert plugins is not None
    # The Foo submenu lives inside Plugins, not as a top-level menu.
    assert _find_menu(win.menuBar(), "Foo") is None
    foo_in_plugins = next(
        (a.menu() for a in plugins.actions()
         if a.menu() and a.menu().title() == "Foo"),
        None,
    )
    assert foo_in_plugins is menu


def test_nested_path_namespaced_under_plugins(qtbot) -> None:
    win = _make_window(qtbot)
    menu = resolve_menu_path(win, "Foo/Bar")
    plugins = _find_menu(win.menuBar(), "Plugins")
    foo = next(
        (a.menu() for a in plugins.actions()
         if a.menu() and a.menu().title() == "Foo"),
        None,
    )
    assert foo is not None
    bar = next(
        (a.menu() for a in foo.actions()
         if a.menu() and a.menu().title() == "Bar"),
        None,
    )
    assert bar is menu


def test_emdash_style_path_lands_under_plugins_not_real_edit(qtbot) -> None:
    """Reproduces the behaviour change: ``Edit/Transform`` no longer
    means the editor's real Edit menu — it means ``Plugins/Edit/Transform``.
    """
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find"])])
    menu = resolve_menu_path(win, "Edit/Transform")

    # The real Edit menu must NOT have a Transform child
    real_edit = win._test_menus["Edit"]
    assert not any(
        a.menu() and a.menu().title() == "Transform"
        for a in real_edit.actions()
    )

    # But Plugins/Edit/Transform should exist
    plugins = _find_menu(win.menuBar(), "Plugins")
    edit_in_plugins = next(
        (a.menu() for a in plugins.actions()
         if a.menu() and a.menu().title() == "Edit"),
        None,
    )
    assert edit_in_plugins is not None
    transform = next(
        (a.menu() for a in edit_in_plugins.actions()
         if a.menu() and a.menu().title() == "Transform"),
        None,
    )
    assert transform is menu


# ---------------------------------------------------------------------------
# Escape-hatch ``/``-prefix
# ---------------------------------------------------------------------------


def test_slash_prefix_resolves_to_top_level(qtbot) -> None:
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find"])])
    menu = resolve_menu_path(win, "/Edit")
    # Returns the real Edit menu, not Plugins/Edit
    assert menu is win._test_menus["Edit"]


def test_slash_prefix_creates_submenu_in_top_level(qtbot) -> None:
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find"])])
    menu = resolve_menu_path(win, "/Edit/Transform")
    real_edit = win._test_menus["Edit"]
    transform = next(
        (a.menu() for a in real_edit.actions()
         if a.menu() and a.menu().title() == "Transform"),
        None,
    )
    assert transform is menu


# ---------------------------------------------------------------------------
# `place=` requirement for `/`-prefixed registrations
# ---------------------------------------------------------------------------


def test_slash_prefix_register_action_requires_place() -> None:
    with pytest.raises(ValueError, match="place"):
        @plugin_api.register_action(id="x", label="x", menu="/Edit")
        def fn():
            pass


def test_slash_prefix_register_text_transform_requires_place() -> None:
    with pytest.raises(ValueError, match="place"):
        @plugin_api.register_text_transform(id="x", label="x", menu="/Edit")
        def fn(text):
            return text


def test_non_slash_path_does_not_require_place() -> None:
    """Default Plugins-namespaced registration ignores ``place=``."""
    @plugin_api.register_action(id="x.a", label="A", menu="Foo")
    def fn():
        pass
    # If we got here without raising, we're good.
    [a] = plugin_api._REGISTRY.actions()
    assert a.id == "x.a"


# ---------------------------------------------------------------------------
# Anchor-based placement (after:/before:)
# ---------------------------------------------------------------------------


def test_place_after_inserts_immediately_after_anchor(qtbot) -> None:
    win = _make_window(
        qtbot,
        pre_menus=[("&Edit", ["edit.find", "edit.find_next", "edit.preferences"])],
    )
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="P-Action", plugin_name="p",
        menu="/Edit", place="after:edit.find",
        callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    edit = win._test_menus["Edit"]
    titles = _menu_action_texts(edit)
    assert titles == ["edit.find", "P-Action", "edit.find_next", "edit.preferences"]


def test_place_before_inserts_immediately_before_anchor(qtbot) -> None:
    win = _make_window(
        qtbot,
        pre_menus=[("&Edit", ["edit.find", "edit.find_next", "edit.preferences"])],
    )
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="P-Action", plugin_name="p",
        menu="/Edit", place="before:edit.preferences",
        callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    edit = win._test_menus["Edit"]
    titles = _menu_action_texts(edit)
    assert titles == ["edit.find", "edit.find_next", "P-Action", "edit.preferences"]


def test_place_start_prepends(qtbot) -> None:
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find", "edit.preferences"])])
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="P-Action", plugin_name="p",
        menu="/Edit", place="start", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    titles = _menu_action_texts(win._test_menus["Edit"])
    assert titles == ["P-Action", "edit.find", "edit.preferences"]


def test_place_end_appends(qtbot) -> None:
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find", "edit.preferences"])])
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="P-Action", plugin_name="p",
        menu="/Edit", place="end", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    titles = _menu_action_texts(win._test_menus["Edit"])
    assert titles == ["edit.find", "edit.preferences", "P-Action"]


# ---------------------------------------------------------------------------
# Multiple plugins targeting the same anchor cluster in load order
# ---------------------------------------------------------------------------


def test_multiple_after_anchors_cluster_in_load_order(qtbot) -> None:
    """plugin-a and plugin-b both want after:edit.find. They should
    appear in load order (a then b), both clustered after Find."""
    win = _make_window(
        qtbot,
        pre_menus=[("&Edit", ["edit.find", "edit.find_next"])],
    )
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="a.x", label="A-Action", plugin_name="plugin-a",
        menu="/Edit", place="after:edit.find", callback=lambda: None,
    ))
    registry.register_action(PluginAction(
        id="b.x", label="B-Action", plugin_name="plugin-b",
        menu="/Edit", place="after:edit.find", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    titles = _menu_action_texts(win._test_menus["Edit"])
    assert titles == ["edit.find", "A-Action", "B-Action", "edit.find_next"]


def test_multiple_before_anchors_cluster_in_load_order(qtbot) -> None:
    win = _make_window(
        qtbot,
        pre_menus=[("&Edit", ["edit.find", "edit.preferences"])],
    )
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="a.x", label="A-Action", plugin_name="plugin-a",
        menu="/Edit", place="before:edit.preferences", callback=lambda: None,
    ))
    registry.register_action(PluginAction(
        id="b.x", label="B-Action", plugin_name="plugin-b",
        menu="/Edit", place="before:edit.preferences", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    titles = _menu_action_texts(win._test_menus["Edit"])
    assert titles == ["edit.find", "A-Action", "B-Action", "edit.preferences"]


# ---------------------------------------------------------------------------
# Anchor failure: nonexistent anchor → forgiving fallback to Plugins menu
# ---------------------------------------------------------------------------


def test_unknown_anchor_id_falls_back_to_plugins_menu(qtbot, caplog) -> None:
    """An unknown ``place=`` anchor is forgiving: the action still
    surfaces in the top-level Plugins menu (not the originally-
    requested escape-hatch menu). A log line explains why.

    Previously the action was orphaned — QAction existed, shortcut
    worked, palette entry worked, but the user never saw it in any
    menu. Falling back to the default Plugins namespace gives the
    action a visible, discoverable home.
    """
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find"])])
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="p.a", label="P-Action", plugin_name="p",
        menu="/Edit", place="after:edit.does_not_exist",
        callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    # Not in the Edit menu (the originally-requested target).
    assert "P-Action" not in _menu_action_texts(win._test_menus["Edit"])

    # But present in the Plugins menu as a fallback.
    plugins_menu = _find_menu(win.menuBar(), "Plugins")
    assert plugins_menu is not None
    assert "P-Action" in _menu_action_texts(plugins_menu)

    # And we should see a clear log message about the unknown anchor.
    assert any(
        "edit.does_not_exist" in r.getMessage()
        for r in caplog.records
    )


def test_unknown_anchor_transform_also_falls_back(qtbot) -> None:
    """Same fallback applies to text transforms with a broken ``place=``."""
    win = _make_window(qtbot, pre_menus=[("&Edit", ["edit.find"])])
    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="p.t", label="P-Transform", plugin_name="p",
        menu="/Edit", place="after:edit.does_not_exist",
        transform=lambda s: s,
    ))
    inject_plugin_actions(win, registry, [])

    plugins_menu = _find_menu(win.menuBar(), "Plugins")
    assert plugins_menu is not None
    assert "P-Transform" in _menu_action_texts(plugins_menu)


# ---------------------------------------------------------------------------
# Plugins menu always present and positioned before Help
# ---------------------------------------------------------------------------


def test_full_editor_has_plugins_menu_before_help(qtbot) -> None:
    """The real MarkdownEditor's menu bar must contain a Plugins menu
    positioned just before Help, regardless of whether any plugin is
    installed."""
    from PySide6.QtWidgets import QApplication
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

    editor = MarkdownEditor()
    try:
        titles = _menu_titles(editor.menuBar())
        assert "Plugins" in titles, f"Plugins menu missing; got {titles}"
        assert "Help" in titles, f"Help menu missing; got {titles}"
        plugins_idx = titles.index("Plugins")
        help_idx = titles.index("Help")
        assert plugins_idx == help_idx - 1, (
            f"Plugins should be immediately before Help. "
            f"plugins={plugins_idx}, help={help_idx}, order={titles}"
        )
    finally:
        editor.close()
        del editor
        QApplication.processEvents()

"""Tests for the menu/palette/shortcut integration helper.

This layer is unit-testable without starting the full MarkdownEditor:
we give it a bare QMainWindow + a populated PluginRegistry and verify
that the right QActions appear on the right menus, shortcuts are
bound, and palette commands are produced.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QPlainTextEdit

from markdown_editor.markdown6.components.command_palette import Command
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
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


def _make_window(qtbot, pre_menus: list[str] | None = None) -> QMainWindow:
    """Create a QMainWindow, optionally pre-populating named top-level menus.

    Pre-created menus are built with ``QMenu(name, window)`` so they are
    Qt-parented to the long-lived window (matching how the real
    ``MarkdownEditor`` builds its menus and dodging PySide6's
    addMenu-return ownership pitfall). They are also registered with
    the plugin integration cache so plugin path resolution can find
    them by name.
    """
    from PySide6.QtWidgets import QMenu

    win = QMainWindow()
    qtbot.addWidget(win)
    win._test_menus = {}   # type: ignore[attr-defined]
    for name in pre_menus or []:
        stripped = name.replace("&", "")
        m = QMenu(name, win)
        win.menuBar().addMenu(m)
        win._test_menus[stripped] = m
        register_existing_menu(win, stripped, m)
    return win


def _menu_by_title(menubar, title: str) -> QMenu | None:
    for action in menubar.actions():
        menu = action.menu()
        if menu and menu.title().replace("&", "") == title.replace("&", ""):
            return menu
    return None


def _action_by_text(menu: QMenu, text: str):
    for action in menu.actions():
        if action.text() == text:
            return action
    return None


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


# ---------------------------------------------------------------------------
# resolve_menu_path
# ---------------------------------------------------------------------------


def test_resolve_menu_path_creates_top_level_plugins(qtbot) -> None:
    """Empty path → action goes directly into the top-level Plugins menu."""
    win = _make_window(qtbot)
    menu = resolve_menu_path(win, "")
    assert menu.title().replace("&", "") == "Plugins"
    assert _menu_by_title(win.menuBar(), "Plugins") is menu


def test_resolve_menu_path_escape_hatch_reuses_existing_top_level(qtbot) -> None:
    """`/Edit` reuses the editor's pre-existing top-level Edit menu."""
    win = _make_window(qtbot, pre_menus=["&Edit"])
    edit_menu = win._test_menus["Edit"]
    menu = resolve_menu_path(win, "/Edit")
    assert menu is edit_menu


def test_resolve_menu_path_escape_hatch_creates_submenu(qtbot) -> None:
    """`/Edit/Transform` creates a Transform submenu inside the real Edit."""
    win = _make_window(qtbot, pre_menus=["&Edit"])
    transform = resolve_menu_path(win, "/Edit/Transform")
    assert transform.title() == "Transform"
    edit = win._test_menus["Edit"]
    assert transform in [a.menu() for a in edit.actions() if a.menu()]


def test_resolve_menu_path_empty_defaults_to_plugins(qtbot) -> None:
    win = _make_window(qtbot)
    menu = resolve_menu_path(win, "")
    assert menu.title().replace("&", "") == "Plugins"


# ---------------------------------------------------------------------------
# inject_plugin_actions - PluginAction
# ---------------------------------------------------------------------------


def test_inject_action_adds_menu_entry_under_default_plugins_menu(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.hello", label="Hello", callback=lambda: None,
    ))
    commands: list[Command] = []
    inject_plugin_actions(win, registry, commands)

    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    assert plugins_menu is not None
    assert _action_by_text(plugins_menu, "Hello") is not None


def test_inject_action_respects_namespaced_menu_path(qtbot) -> None:
    """Plain `Edit/Transform` lands at Plugins/Edit/Transform - namespaced
    under the top-level Plugins menu, not in the editor's real Edit."""
    win = _make_window(qtbot, pre_menus=["&Edit"])

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.fmt", label="Format", menu="Edit/Transform", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])

    real_edit = win._test_menus["Edit"]
    real_subs = [a.menu().title() for a in real_edit.actions() if a.menu()]
    assert "Transform" not in real_subs   # NOT in the real Edit

    plugins = _menu_by_title(win.menuBar(), "Plugins")
    edit_in_plugins = next(
        (a.menu() for a in plugins.actions()
         if a.menu() and a.menu().title() == "Edit"), None,
    )
    assert edit_in_plugins is not None
    transform = next(
        (a.menu() for a in edit_in_plugins.actions()
         if a.menu() and a.menu().title() == "Transform"), None,
    )
    assert transform is not None
    assert _action_by_text(transform, "Format") is not None


def test_inject_action_binds_shortcut(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.z", label="Zap", shortcut="Ctrl+Alt+Z", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    action = _action_by_text(plugins_menu, "Zap")
    assert action.shortcut() == QKeySequence("Ctrl+Alt+Z")


def test_inject_action_appends_palette_command(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.p", label="Palette Me", palette_category="Plugin", callback=lambda: None,
    ))
    commands: list[Command] = []
    inject_plugin_actions(win, registry, commands)
    assert any(c.id == "x.p" for c in commands)
    [cmd] = [c for c in commands if c.id == "x.p"]
    assert cmd.name == "Palette Me"
    assert cmd.category == "Plugin"


def test_inject_action_invokes_callback_with_no_args(qtbot) -> None:
    """Core invariant: callback must NOT receive any framework Qt object."""
    win = _make_window(qtbot)
    received: list = []

    def handler():
        # If the framework passed anything at all, this would fail.
        received.append("called")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.noarg", label="NoArg", callback=handler,
    ))
    inject_plugin_actions(win, registry, [])

    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    action = _action_by_text(plugins_menu, "NoArg")
    action.trigger()
    assert received == ["called"]


def test_inject_action_swallows_callback_exceptions(qtbot) -> None:
    """Editor must never crash because a plugin's action raised."""
    win = _make_window(qtbot)

    def boom():
        raise RuntimeError("plugin exploded")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.boom", label="Boom", callback=boom,
    ))
    inject_plugin_actions(win, registry, [])

    action = _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "Boom")
    # Trigger MUST NOT raise out of the slot.
    action.trigger()


# ---------------------------------------------------------------------------
# inject_plugin_actions - PluginTextTransform
# ---------------------------------------------------------------------------


def test_inject_transform_menu_entry(qtbot) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="t.up", label="Upper", transform=lambda s: s.upper(),
    ))
    inject_plugin_actions(win, registry, [])
    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    assert _action_by_text(plugins_menu, "Upper") is not None


def test_inject_transform_triggers_atomic_apply(qtbot) -> None:
    """Triggering a transform menu entry applies the transform to the
    active document atomically (single undo step)."""
    win = _make_window(qtbot)

    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)
    plugin_api._set_active_document_provider(lambda: doc)

    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="t.up", label="Upper", transform=lambda s: s.upper(),
    ))
    inject_plugin_actions(win, registry, [])

    action = _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "Upper")
    action.trigger()
    assert editor.toPlainText() == "HELLO WORLD"
    editor.undo()
    assert editor.toPlainText() == "hello world"


def test_inject_transform_noop_if_no_active_document(qtbot) -> None:
    """Transform invoked with no active document is a silent no-op, not a crash."""
    win = _make_window(qtbot)
    plugin_api._set_active_document_provider(lambda: None)

    registry = PluginRegistry()
    calls: list[str] = []
    registry.register_text_transform(PluginTextTransform(
        id="t.noop", label="Noop",
        transform=lambda s: (calls.append(s), s)[1],
    ))
    inject_plugin_actions(win, registry, [])

    action = _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "Noop")
    action.trigger()
    # Transform must NOT have been called - no document was available.
    assert calls == []


def test_inject_transform_failure_leaves_document_unchanged(qtbot) -> None:
    win = _make_window(qtbot)
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("pristine")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    plugin_api._set_active_document_provider(lambda: DocumentHandle(tab))

    def explode(_text: str) -> str:
        raise RuntimeError("bad transform")

    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="t.boom", label="Boom", transform=explode,
    ))
    inject_plugin_actions(win, registry, [])

    action = _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "Boom")
    action.trigger()   # must not raise
    assert editor.toPlainText() == "pristine"
    assert tab.unsaved_changes is False


# ---------------------------------------------------------------------------
# Combined: a PluginAction and a PluginTextTransform in one registry
# ---------------------------------------------------------------------------


def test_inject_mixed_actions_and_transforms(qtbot) -> None:
    win = _make_window(qtbot, pre_menus=["&Edit"])
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.a", label="ActionA", menu="", callback=lambda: None,
    ))
    registry.register_text_transform(PluginTextTransform(
        id="t.b", label="TransformB", menu="Edit/Transform",
        transform=lambda s: s,
    ))

    commands: list[Command] = []
    inject_plugin_actions(win, registry, commands)

    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    # Top-level action goes directly into Plugins
    assert _action_by_text(plugins_menu, "ActionA") is not None

    # Nested action goes into Plugins/Edit/Transform
    edit_in_plugins = next(
        (a.menu() for a in plugins_menu.actions()
         if a.menu() and a.menu().title() == "Edit"), None,
    )
    assert edit_in_plugins is not None
    transform_sub = next(
        (a.menu() for a in edit_in_plugins.actions()
         if a.menu() and a.menu().title() == "Transform"), None,
    )
    assert transform_sub is not None
    assert _action_by_text(transform_sub, "TransformB") is not None

    ids = [c.id for c in commands]
    assert "x.a" in ids and "t.b" in ids

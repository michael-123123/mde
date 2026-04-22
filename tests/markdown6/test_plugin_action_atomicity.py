"""Plugin-action atomicity: action mutates inside ``atomic_edit`` then
raises → document text is unchanged after the dust settles.

This is the contract the plan promises for "imperative" plugin actions
(the ``with doc.atomic_edit():`` style - counterpart to the pure-
transform style which is atomic by construction).

Also covers the *non*-atomic case (plugin mutates without
``atomic_edit`` and raises) so we have a clear executable record of
what happens: the partial mutation persists, the document is left
modified, the user sees a notification but their content has
changed. Atomicity is opt-in.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMainWindow, QPlainTextEdit

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.notifications import Severity
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.editor_integration import (
    inject_plugin_actions,
)
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginRegistry,
)


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


def _setup(qtbot, initial_text: str = "ORIGINAL"):
    """Build a window + a fresh document handle wired as the active doc."""
    win = QMainWindow()
    qtbot.addWidget(win)
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(initial_text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)
    plugin_api._set_active_document_provider(lambda: doc)
    return win, editor, tab, doc


def _menu_by_title(menubar, title):
    for a in menubar.actions():
        m = a.menu()
        if m and m.title().replace("&", "") == title:
            return m
    return None


def _action_by_text(menu, text):
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


def _trigger(win, label):
    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    _action_by_text(plugins_menu, label).trigger()


# ---------------------------------------------------------------------------
# The contract: action mutates inside atomic_edit + raises → text unchanged
# ---------------------------------------------------------------------------


def test_action_mutates_in_atomic_edit_then_raises_text_unchanged(qtbot, ctx) -> None:
    win, editor, tab, _ = _setup(qtbot, "ORIGINAL")

    def my_action():
        d = plugin_api.get_active_document()
        with d.atomic_edit():
            d.replace_all("MUTATED")
            raise RuntimeError("boom after mutation")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.atom", label="AtomicTest", plugin_name="testplug",
        callback=my_action,
    ))
    inject_plugin_actions(win, registry, [])

    _trigger(win, "AtomicTest")

    assert editor.toPlainText() == "ORIGINAL"
    assert tab.unsaved_changes is False


def test_action_in_atomic_edit_with_multiple_mutations_then_raises_all_rolled_back(qtbot, ctx) -> None:
    """All mutations inside the same ``atomic_edit`` block are reverted
    as one - there's no "first edit applied, second edit rolled back"
    half-state."""
    win, editor, tab, _ = _setup(qtbot, "START")

    def my_action():
        d = plugin_api.get_active_document()
        with d.atomic_edit():
            d.replace_all("FIRST")
            d.replace_all("SECOND")
            d.replace_all("THIRD")
            raise RuntimeError("after three edits")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.multi", label="MultiAtomic", plugin_name="testplug",
        callback=my_action,
    ))
    inject_plugin_actions(win, registry, [])

    _trigger(win, "MultiAtomic")

    assert editor.toPlainText() == "START"
    assert tab.unsaved_changes is False


def test_action_atomic_edit_clean_exit_commits(qtbot, ctx) -> None:
    """Sanity baseline: when the action does NOT raise, the mutations
    inside ``atomic_edit`` do persist."""
    win, editor, _, _ = _setup(qtbot, "BEFORE")

    def my_action():
        d = plugin_api.get_active_document()
        with d.atomic_edit():
            d.replace_all("AFTER")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.ok", label="OkAtomic", plugin_name="testplug",
        callback=my_action,
    ))
    inject_plugin_actions(win, registry, [])

    _trigger(win, "OkAtomic")
    assert editor.toPlainText() == "AFTER"


def test_action_atomic_edit_rollback_posts_error_notification(qtbot, ctx) -> None:
    """The exception is swallowed by the framework's wrapper, but the
    user sees it surfaced via the notifications drawer."""
    win, _, _, _ = _setup(qtbot, "X")

    def my_action():
        d = plugin_api.get_active_document()
        with d.atomic_edit():
            d.replace_all("Y")
            raise RuntimeError("post-mutation failure")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.notify", label="NotifyTest", plugin_name="testplug",
        callback=my_action,
    ))
    inject_plugin_actions(win, registry, [])

    _trigger(win, "NotifyTest")

    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR
    assert "testplug" in n.source
    assert "post-mutation failure" in n.message


# ---------------------------------------------------------------------------
# Counter-test: mutation WITHOUT atomic_edit is NOT rolled back.
# Documents the "atomicity is opt-in" rule with a runnable example.
# ---------------------------------------------------------------------------


def test_action_mutates_without_atomic_edit_then_raises_partial_persists(qtbot, ctx) -> None:
    """Without ``with doc.atomic_edit():``, a plugin's mutation persists
    even if the action subsequently raises. This is the documented
    behavior: atomicity is opt-in. Plugins that mutate THEN call
    something that might fail must wrap the whole block in
    ``atomic_edit``."""
    win, editor, _, _ = _setup(qtbot, "ORIGINAL")

    def my_action():
        d = plugin_api.get_active_document()
        d.replace_all("PARTIAL")   # no atomic_edit guard
        raise RuntimeError("after partial mutation")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.partial", label="PartialMut", plugin_name="testplug",
        callback=my_action,
    ))
    inject_plugin_actions(win, registry, [])

    _trigger(win, "PartialMut")

    # The mutation IS visible - the framework can't undo what the
    # plugin did outside an atomic_edit.
    assert editor.toPlainText() == "PARTIAL"
    # And the user still sees the failure surfaced in notifications.
    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR

"""Tests for routing plugin runtime errors into the NotificationCenter.

Each kind of plugin callback that the framework wraps with try/except
(action, text-transform, exporter, signal handler) must additionally
post a notification on failure so the user sees the issue surfaced
in the bell/drawer UI — not just buried in the log.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from PySide6.QtWidgets import QFileDialog, QMainWindow, QPlainTextEdit

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.notifications import NotificationCenter, Severity
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.editor_integration import (
    inject_plugin_actions,
)
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginExporter,
    PluginRegistry,
    PluginTextTransform,
)
from markdown_editor.markdown6.plugins.signals import SignalKind, dispatch


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


def _make_window(qtbot) -> QMainWindow:
    win = QMainWindow()
    qtbot.addWidget(win)
    return win


def _make_doc(qtbot, text: str = "x") -> DocumentHandle:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    return DocumentHandle(tab)


def _menu_by_title(menubar, title: str):
    for a in menubar.actions():
        m = a.menu()
        if m and m.title().replace("&", "") == title:
            return m
    return None


def _action_by_text(menu, text: str):
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


# ---------------------------------------------------------------------------
# AppContext exposes a NotificationCenter
# ---------------------------------------------------------------------------


def test_app_context_provides_notification_center(ctx) -> None:
    assert isinstance(ctx.notifications, NotificationCenter)


def test_notifications_center_is_singleton_per_context(ctx) -> None:
    assert ctx.notifications is ctx.notifications


# ---------------------------------------------------------------------------
# Plugin action runtime error → notification posted
# ---------------------------------------------------------------------------


def test_plugin_action_raise_posts_error_notification(qtbot, ctx) -> None:
    win = _make_window(qtbot)

    def boom():
        raise RuntimeError("action exploded")

    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.bad", label="Bad", plugin_name="bad_plugin",
        callback=boom,
    ))
    inject_plugin_actions(win, registry, [])

    plugins_menu = _menu_by_title(win.menuBar(), "Plugins")
    action = _action_by_text(plugins_menu, "Bad")
    action.trigger()    # must not raise

    notifications = ctx.notifications.all()
    assert len(notifications) == 1
    n = notifications[0]
    assert n.severity is Severity.ERROR
    assert "bad_plugin" in n.source
    assert "action exploded" in n.message


# ---------------------------------------------------------------------------
# Plugin text-transform raise → notification posted
# ---------------------------------------------------------------------------


def test_plugin_text_transform_raise_posts_error_notification(qtbot, ctx) -> None:
    win = _make_window(qtbot)
    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    def explode(_text: str) -> str:
        raise RuntimeError("transform broken")

    registry = PluginRegistry()
    registry.register_text_transform(PluginTextTransform(
        id="t.bad", label="BadT", plugin_name="bad_plugin",
        transform=explode,
    ))
    inject_plugin_actions(win, registry, [])
    _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "BadT").trigger()

    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR
    assert "bad_plugin" in n.source
    assert "transform broken" in n.message


# ---------------------------------------------------------------------------
# Plugin exporter raise → notification posted
# ---------------------------------------------------------------------------


def test_plugin_exporter_raise_posts_error_notification(qtbot, ctx, tmp_path: Path) -> None:
    win = _make_window(qtbot)
    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    registry = PluginRegistry()
    registry.register_exporter(PluginExporter(
        id="exp.bad", label="BadExporter",
        extensions=("md",),
        plugin_name="bad_plugin",
        callback=lambda d, p: (_ for _ in ()).throw(RuntimeError("export broken")),
    ))
    inject_plugin_actions(win, registry, [])

    with mock.patch.object(
        QFileDialog, "getSaveFileName",
        return_value=(str(tmp_path / "out.md"), ""),
    ):
        plugins = _menu_by_title(win.menuBar(), "Plugins")
        export_sub = next(
            (a.menu() for a in plugins.actions()
             if a.menu() and a.menu().title() == "Export"), None,
        )
        _action_by_text(export_sub, "BadExporter").trigger()

    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR
    assert "bad_plugin" in n.source
    assert "export broken" in n.message


# ---------------------------------------------------------------------------
# Plugin signal handler raise → notification posted
# ---------------------------------------------------------------------------


def test_signal_handler_raise_posts_error_notification(qtbot, ctx) -> None:
    @plugin_api.on_save
    def boom(doc):
        raise RuntimeError("save handler broken")
    # Stamp plugin_name manually (since we're not going through loader)
    plugin_api._REGISTRY.signal_handlers(SignalKind.SAVE)[0].plugin_name = "bad_plugin"

    doc = _make_doc(qtbot)
    dispatch(SignalKind.SAVE, doc, disabled=set())

    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR
    assert "bad_plugin" in n.source
    assert "save handler broken" in n.message


def test_signal_handler_no_plugin_name_still_posts(qtbot, ctx) -> None:
    """Handlers registered outside the loader (tests, dev REPL) have an
    empty plugin_name. They should still be reported when they fail —
    just with a generic source label.
    """
    @plugin_api.on_content_changed
    def boom(doc):
        raise RuntimeError("change handler broken")

    doc = _make_doc(qtbot)
    dispatch(SignalKind.CONTENT_CHANGED, doc, disabled=set())

    [n] = ctx.notifications.all()
    assert n.severity is Severity.ERROR
    assert "change handler broken" in n.message


# ---------------------------------------------------------------------------
# Healthy plugins do NOT post anything
# ---------------------------------------------------------------------------


def test_healthy_action_does_not_post_notification(qtbot, ctx) -> None:
    win = _make_window(qtbot)
    registry = PluginRegistry()
    registry.register_action(PluginAction(
        id="x.ok", label="OK", plugin_name="good", callback=lambda: None,
    ))
    inject_plugin_actions(win, registry, [])
    _action_by_text(_menu_by_title(win.menuBar(), "Plugins"), "OK").trigger()
    assert ctx.notifications.all() == []

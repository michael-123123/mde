"""Tests for plugin-registered exporters.

A plugin declares an export format with a callback ``(doc, path) -> None``;
the framework adds a menu entry under ``Plugins/Export/<label>``, opens
a save dialog filtered by the declared file extensions, and invokes
the callback with the chosen path.

The plugin never sees Qt - the dialog is the framework's
responsibility. The callback gets a ``DocumentHandle`` and a
``pathlib.Path``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from PySide6.QtWidgets import QFileDialog, QMainWindow, QPlainTextEdit

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.editor_integration import (
    inject_plugin_actions,
)
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


def _make_window_with_doc(qtbot, text: str = "hello"):
    win = QMainWindow()
    qtbot.addWidget(win)
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)
    plugin_api._set_active_document_provider(lambda: doc)
    return win, doc


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
# Registration
# ---------------------------------------------------------------------------


def test_register_exporter_decorator_stores_record() -> None:
    @plugin_api.register_exporter(
        id="jekyll", label="Jekyll Post", extensions=["md"],
    )
    def export_fn(doc, path):
        pass

    [rec] = plugin_api._REGISTRY.exporters()
    assert rec.id == "jekyll"
    assert rec.label == "Jekyll Post"
    assert rec.extensions == ("md",)
    assert rec.callback is export_fn


def test_register_exporter_returns_original_function() -> None:
    @plugin_api.register_exporter(
        id="x", label="X", extensions=["txt"],
    )
    def export_fn(doc, path):
        return "kept"
    assert export_fn(None, None) == "kept"


def test_register_exporter_stamps_plugin_name(tmp_path: Path) -> None:
    (tmp_path / "expplug").mkdir()
    (tmp_path / "expplug" / "expplug.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "expplug"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "expplug" / "expplug.py").write_text(textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import register_exporter
        @register_exporter(id="x", label="X", extensions=["md"])
        def fn(doc, path):
            path.write_text(doc.text)
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [rec] = plugin_api._REGISTRY.exporters()
    assert rec.plugin_name == "expplug"


def test_register_exporter_requires_extensions() -> None:
    with pytest.raises(ValueError, match="extensions"):
        @plugin_api.register_exporter(
            id="x", label="X", extensions=[],
        )
        def fn(doc, path):
            pass


# ---------------------------------------------------------------------------
# Menu integration
# ---------------------------------------------------------------------------


def test_exporter_appears_in_plugins_export_menu(qtbot) -> None:
    @plugin_api.register_exporter(
        id="jekyll", label="Jekyll Post", extensions=["md"],
    )
    def fn(doc, path):
        pass

    win, _ = _make_window_with_doc(qtbot)
    inject_plugin_actions(win, plugin_api._REGISTRY, [])

    plugins = _menu_by_title(win.menuBar(), "Plugins")
    export_sub = next(
        (a.menu() for a in plugins.actions()
         if a.menu() and a.menu().title() == "Export"),
        None,
    )
    assert export_sub is not None
    assert _action_by_text(export_sub, "Jekyll Post") is not None


def test_triggering_exporter_opens_dialog_and_calls_callback(qtbot, tmp_path: Path) -> None:
    captured: dict = {}

    @plugin_api.register_exporter(
        id="jekyll", label="Jekyll", extensions=["md"],
    )
    def fn(doc, path):
        captured["doc"] = doc
        captured["path"] = path
        path.write_text(doc.text + " (jekyll)")

    win, doc = _make_window_with_doc(qtbot, text="hello world")
    inject_plugin_actions(win, plugin_api._REGISTRY, [])

    target = tmp_path / "out.md"
    with mock.patch.object(
        QFileDialog, "getSaveFileName",
        return_value=(str(target), ""),
    ):
        plugins = _menu_by_title(win.menuBar(), "Plugins")
        export_sub = next(
            (a.menu() for a in plugins.actions()
             if a.menu() and a.menu().title() == "Export"), None,
        )
        action = _action_by_text(export_sub, "Jekyll")
        action.trigger()

    assert captured["doc"] is doc
    assert captured["path"] == target
    assert target.read_text() == "hello world (jekyll)"


def test_triggering_exporter_with_cancelled_dialog_is_noop(qtbot) -> None:
    calls = []

    @plugin_api.register_exporter(
        id="x", label="X", extensions=["txt"],
    )
    def fn(doc, path):
        calls.append((doc, path))

    win, _ = _make_window_with_doc(qtbot)
    inject_plugin_actions(win, plugin_api._REGISTRY, [])

    with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
        plugins = _menu_by_title(win.menuBar(), "Plugins")
        export_sub = next(
            (a.menu() for a in plugins.actions()
             if a.menu() and a.menu().title() == "Export"), None,
        )
        action = _action_by_text(export_sub, "X")
        action.trigger()

    assert calls == []


def test_exporter_callback_exception_is_swallowed(qtbot, tmp_path: Path, caplog) -> None:
    @plugin_api.register_exporter(
        id="bad", label="Bad", extensions=["md"],
    )
    def fn(doc, path):
        raise RuntimeError("boom in plugin export")

    win, _ = _make_window_with_doc(qtbot)
    inject_plugin_actions(win, plugin_api._REGISTRY, [])

    with mock.patch.object(
        QFileDialog, "getSaveFileName",
        return_value=(str(tmp_path / "out.md"), ""),
    ):
        plugins = _menu_by_title(win.menuBar(), "Plugins")
        export_sub = next(
            (a.menu() for a in plugins.actions()
             if a.menu() and a.menu().title() == "Export"), None,
        )
        # Must not raise out of the slot
        _action_by_text(export_sub, "Bad").trigger()

    assert any("boom in plugin export" in r.getMessage() for r in caplog.records)


def test_exporter_with_no_active_document_is_noop(qtbot) -> None:
    plugin_api._set_active_document_provider(lambda: None)
    calls = []

    @plugin_api.register_exporter(
        id="x", label="X", extensions=["md"],
    )
    def fn(doc, path):
        calls.append("ran")

    win = QMainWindow()
    qtbot.addWidget(win)
    inject_plugin_actions(win, plugin_api._REGISTRY, [])

    # If the framework opened the dialog with no doc, the user might
    # have wasted a dialog interaction. Better: don't even open it.
    with mock.patch.object(QFileDialog, "getSaveFileName") as m:
        plugins = _menu_by_title(win.menuBar(), "Plugins")
        export_sub = next(
            (a.menu() for a in plugins.actions()
             if a.menu() and a.menu().title() == "Export"), None,
        )
        _action_by_text(export_sub, "X").trigger()

    m.assert_not_called()
    assert calls == []

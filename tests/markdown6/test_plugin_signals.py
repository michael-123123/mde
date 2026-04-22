"""Tests for plugin signal decorators.

Plugins subscribe to document lifecycle events with declarative
decorators that pass a Qt-free :class:`DocumentHandle` to the handler.
The framework dispatches to all registered handlers when the editor
emits the corresponding event, with three guarantees:

1. Disabled plugins' handlers do not fire.
2. An exception in one handler is logged and swallowed; subsequent
   handlers still run.
3. Handlers receive a :class:`DocumentHandle`, never a Qt object.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource
from markdown_editor.markdown6.plugins.signals import (
    SignalKind,
    dispatch,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


def _make_doc(qtbot, text: str = "hello") -> DocumentHandle:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    return DocumentHandle(tab)


# ---------------------------------------------------------------------------
# Decorator registration
# ---------------------------------------------------------------------------


def test_on_save_registers_handler() -> None:
    @plugin_api.on_save
    def handler(doc):
        pass

    handlers = plugin_api._REGISTRY.signal_handlers(SignalKind.SAVE)
    assert len(handlers) == 1
    assert handlers[0].callback is handler


def test_on_content_changed_registers_handler() -> None:
    @plugin_api.on_content_changed
    def handler(doc):
        pass
    assert len(plugin_api._REGISTRY.signal_handlers(SignalKind.CONTENT_CHANGED)) == 1


def test_on_file_opened_registers_handler() -> None:
    @plugin_api.on_file_opened
    def handler(doc):
        pass
    assert len(plugin_api._REGISTRY.signal_handlers(SignalKind.FILE_OPENED)) == 1


def test_on_file_closed_registers_handler() -> None:
    @plugin_api.on_file_closed
    def handler(doc):
        pass
    assert len(plugin_api._REGISTRY.signal_handlers(SignalKind.FILE_CLOSED)) == 1


def test_decorators_return_original_function() -> None:
    @plugin_api.on_save
    def handler(doc):
        return "kept"
    assert handler(None) == "kept"


def test_handlers_stamped_with_plugin_name(tmp_path: Path) -> None:
    """The loader's _CURRENT_PLUGIN_NAME context applies to signal
    decorators too — needed so live disable can skip handlers from
    disabled plugins."""
    (tmp_path / "p1").mkdir()
    (tmp_path / "p1" / "p1.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "p1"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "p1" / "p1.py").write_text(textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import on_save

        @on_save
        def my_handler(doc):
            pass
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    [h] = plugin_api._REGISTRY.signal_handlers(SignalKind.SAVE)
    assert h.plugin_name == "p1"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_dispatch_calls_registered_handlers(qtbot) -> None:
    calls: list = []

    @plugin_api.on_save
    def h1(doc):
        calls.append(("h1", doc))

    @plugin_api.on_save
    def h2(doc):
        calls.append(("h2", doc))

    doc = _make_doc(qtbot, "x")
    dispatch(SignalKind.SAVE, doc, disabled=set())
    assert [c[0] for c in calls] == ["h1", "h2"]
    assert all(c[1] is doc for c in calls)


def test_dispatch_passes_document_handle_not_raw_tab(qtbot) -> None:
    received: list = []

    @plugin_api.on_save
    def h(doc):
        received.append(doc)

    doc = _make_doc(qtbot)
    dispatch(SignalKind.SAVE, doc, disabled=set())
    [got] = received
    assert isinstance(got, DocumentHandle)
    # And no Qt types leak via attribute access on the public API
    assert isinstance(got.text, str)


def test_dispatch_skips_disabled_plugin_handlers(tmp_path: Path, qtbot) -> None:
    # Plugin "loud" registers an on_save handler that records its call.
    (tmp_path / "loud").mkdir()
    (tmp_path / "loud" / "loud.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "loud"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "loud" / "loud.py").write_text(textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import on_save
        CALLS = []
        @on_save
        def h(doc):
            CALLS.append(doc)
    """), encoding="utf-8")
    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    loud = plugins[0].module

    doc = _make_doc(qtbot)
    dispatch(SignalKind.SAVE, doc, disabled={"loud"})
    assert loud.CALLS == []          # disabled → skipped

    dispatch(SignalKind.SAVE, doc, disabled=set())
    assert loud.CALLS == [doc]       # re-enabled → fires


def test_dispatch_handler_exception_does_not_stop_others(qtbot, caplog) -> None:
    calls: list = []

    @plugin_api.on_save
    def boom(doc):
        raise RuntimeError("first handler failed")

    @plugin_api.on_save
    def runs_anyway(doc):
        calls.append("runs_anyway")

    doc = _make_doc(qtbot)
    dispatch(SignalKind.SAVE, doc, disabled=set())   # must not raise
    assert calls == ["runs_anyway"]
    # The failure is logged so plugin authors see it
    assert any("first handler failed" in r.getMessage() for r in caplog.records)


def test_dispatch_with_no_handlers_is_a_noop(qtbot) -> None:
    doc = _make_doc(qtbot)
    # No registrations → just returns
    dispatch(SignalKind.SAVE, doc, disabled=set())
    dispatch(SignalKind.CONTENT_CHANGED, doc, disabled=set())


def test_dispatch_isolates_signal_kinds(qtbot) -> None:
    """on_save handlers don't fire on content_changed and vice versa."""
    save_calls: list = []
    change_calls: list = []

    @plugin_api.on_save
    def s(doc):
        save_calls.append("s")

    @plugin_api.on_content_changed
    def c(doc):
        change_calls.append("c")

    doc = _make_doc(qtbot)
    dispatch(SignalKind.CONTENT_CHANGED, doc, disabled=set())
    assert save_calls == []
    assert change_calls == ["c"]


def test_dispatch_handler_can_inspect_document(qtbot) -> None:
    """End-to-end: handler reads the doc via the public API."""
    seen_text: list = []

    @plugin_api.on_save
    def h(doc):
        seen_text.append(doc.text)

    doc = _make_doc(qtbot, text="hello world")
    dispatch(SignalKind.SAVE, doc, disabled=set())
    assert seen_text == ["hello world"]

"""Tests for the documented Qt-access escape hatches.

The plugin API is Qt-free by default, but four explicit opt-in
hatches let advanced plugins reach Qt when they need it:

* ``get_active_document()`` - already covered elsewhere; sanity-checked here.
* ``get_all_documents()`` - every open tab as a list of DocumentHandles.
* ``get_app_context()`` - the AppContext (QObject; signals + settings).
* ``get_main_window()`` - the editor's QMainWindow.
* ``DocumentHandle.editor`` - the underlying QPlainTextEdit.
* ``DocumentHandle.preview`` - the underlying QWebEngineView.

These are *opt-in*: the plugin author has to write the import or
attribute access. They're documented as "not guaranteed stable" so we
can refactor the editor's internals without breaking plugins that use
the supported API.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit

import markdown_editor.plugins as shim
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle


@pytest.fixture(autouse=True)
def _clean_active_document_provider():
    from markdown_editor.markdown6.plugins import api
    api._set_active_document_provider(lambda: None)
    api._set_all_documents_provider(lambda: [])
    api._set_main_window_provider(lambda: None)
    yield
    api._set_active_document_provider(lambda: None)
    api._set_all_documents_provider(lambda: [])
    api._set_main_window_provider(lambda: None)


def _make_doc(qtbot, text: str = "hi") -> DocumentHandle:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    return DocumentHandle(tab)


# ---------------------------------------------------------------------------
# Stable: get_all_documents
# ---------------------------------------------------------------------------


def test_get_all_documents_exported_from_shim() -> None:
    assert hasattr(shim, "get_all_documents")
    assert "get_all_documents" in shim.__all__


def test_get_all_documents_default_returns_empty_list() -> None:
    assert shim.get_all_documents() == []


def test_get_all_documents_returns_provider_result(qtbot) -> None:
    docs = [_make_doc(qtbot, "a"), _make_doc(qtbot, "b")]
    from markdown_editor.markdown6.plugins import api
    api._set_all_documents_provider(lambda: docs)
    got = shim.get_all_documents()
    assert got == docs
    assert all(isinstance(d, DocumentHandle) for d in got)


# ---------------------------------------------------------------------------
# Escape hatches: get_app_context, get_main_window
# ---------------------------------------------------------------------------


def test_get_app_context_exported_from_shim() -> None:
    assert hasattr(shim, "get_app_context")
    assert "get_app_context" in shim.__all__


def test_get_app_context_returns_appcontext() -> None:
    """Sanity: the returned object behaves like AppContext (has .get())."""
    import markdown_editor.markdown6.app_context as ctx_mod
    from markdown_editor.markdown6.app_context import (
        AppContext,
        init_app_context,
    )

    ctx_mod._app_context = None
    init_app_context(ephemeral=True)

    ctx = shim.get_app_context()
    assert isinstance(ctx, AppContext)


def test_get_main_window_exported_from_shim() -> None:
    assert hasattr(shim, "get_main_window")
    assert "get_main_window" in shim.__all__


def test_get_main_window_default_returns_none() -> None:
    assert shim.get_main_window() is None


def test_get_main_window_returns_provider_result(qtbot) -> None:
    from PySide6.QtWidgets import QMainWindow

    from markdown_editor.markdown6.plugins import api

    win = QMainWindow()
    qtbot.addWidget(win)
    api._set_main_window_provider(lambda: win)
    assert shim.get_main_window() is win


# ---------------------------------------------------------------------------
# Escape hatches on DocumentHandle: .editor, .preview
# ---------------------------------------------------------------------------


def test_document_handle_editor_property_exposes_qplaintext(qtbot) -> None:
    """Power-user plugins can reach the underlying QPlainTextEdit via
    `doc.editor` - explicitly documented as an unstable escape hatch."""
    doc = _make_doc(qtbot, "body")
    assert isinstance(doc.editor, QPlainTextEdit)
    # Same object as the wrapped tab's editor
    assert doc.editor is doc._tab.editor


def test_document_handle_preview_property_returns_tab_preview(qtbot) -> None:
    """`doc.preview` exposes the QWebEngineView (or fallback) when the
    wrapped tab has one. None for tabs without a preview widget."""
    # tab without a preview attribute → None
    doc_no_preview = _make_doc(qtbot, "x")
    assert doc_no_preview.preview is None

    # tab with a preview attribute → returned as-is
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    fake_preview = object()
    tab = SimpleNamespace(editor=editor, preview=fake_preview,
                          file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)
    assert doc.preview is fake_preview

"""End-to-end tests for the `wordcount` example plugin.

The plugin exercises three Phase 2 extension points at once:

* ``register_panel`` — the sidebar Word Count panel.
* ``@on_content_changed`` / ``@on_file_opened`` — keep the panel
  in sync as the user edits or opens a different document.
* ``plugin_settings`` — remember the user's target word count
  across editor restarts.

The reference implementation lives under ``docs/plugins-examples/``;
the tests use a self-contained copy in ``tests/markdown6/fixtures/plugins/``
so the test suite never reaches outside the test tree.

This test covers loader discovery + registration end-to-end and
exercises the panel widget with a stand-in document handle (the
full editor isn't constructed here to keep tests fast and
dependency-light — the plugin itself doesn't touch QtWebEngine).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit, QProgressBar, QSpinBox

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource, PluginStatus
from markdown_editor.markdown6.plugins.signals import SignalKind, dispatch

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "plugins"


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


def _make_doc(qtbot, text: str) -> DocumentHandle:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    return DocumentHandle(tab)


# ---------------------------------------------------------------------------
# Plugin discoverable from the test fixtures dir
# ---------------------------------------------------------------------------


def test_wordcount_plugin_files_present() -> None:
    d = FIXTURES_DIR / "wordcount"
    assert (d / "wordcount.py").is_file()
    assert (d / "wordcount.toml").is_file()


def test_wordcount_plugin_loads_clean(ctx) -> None:
    plugins = load_all(
        [(FIXTURES_DIR, PluginSource.USER)], user_disabled=set(),
    )
    by_name = {p.name: p for p in plugins}
    assert "wordcount" in by_name
    assert by_name["wordcount"].status == PluginStatus.ENABLED


def test_wordcount_registers_panel_and_signal_handlers(ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    panels = plugin_api._REGISTRY.panels()
    [wc_panel] = [p for p in panels if p.id == "wordcount"]
    assert wc_panel.label == "Word Count"
    assert wc_panel.icon  # non-empty icon string
    assert wc_panel.plugin_name == "wordcount"

    # Both content-changed and file-opened handlers should be registered
    cc = plugin_api._REGISTRY.signal_handlers(SignalKind.CONTENT_CHANGED)
    fo = plugin_api._REGISTRY.signal_handlers(SignalKind.FILE_OPENED)
    assert any(h.plugin_name == "wordcount" for h in cc)
    assert any(h.plugin_name == "wordcount" for h in fo)


# ---------------------------------------------------------------------------
# Panel behavior
# ---------------------------------------------------------------------------


def _build_panel(qtbot, ctx):
    """Materialize the wordcount panel via its registered factory."""
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [rec] = [p for p in plugin_api._REGISTRY.panels() if p.id == "wordcount"]
    widget = rec.factory()
    qtbot.addWidget(widget)
    return widget


def test_panel_initial_state_zero_count(qtbot, ctx) -> None:
    panel = _build_panel(qtbot, ctx)
    assert panel.count_label.text().startswith("Words: 0")


def test_panel_default_target_loaded_from_settings(qtbot, ctx) -> None:
    ctx.plugin_settings("wordcount")["target"] = 250
    panel = _build_panel(qtbot, ctx)
    spinner = panel.findChild(QSpinBox)
    assert spinner.value() == 250


def test_panel_responds_to_content_changed_signal(qtbot, ctx) -> None:
    panel = _build_panel(qtbot, ctx)
    plugin_api._set_active_document_provider(
        lambda: _make_doc(qtbot, "one two three four five"),
    )
    dispatch(SignalKind.CONTENT_CHANGED, plugin_api.get_active_document(), disabled=set())
    assert "5" in panel.count_label.text()


def test_panel_progress_bar_reflects_progress(qtbot, ctx) -> None:
    ctx.plugin_settings("wordcount")["target"] = 10
    panel = _build_panel(qtbot, ctx)
    plugin_api._set_active_document_provider(
        lambda: _make_doc(qtbot, "one two three four five"),
    )
    dispatch(SignalKind.CONTENT_CHANGED, plugin_api.get_active_document(), disabled=set())
    bar = panel.findChild(QProgressBar)
    assert bar.value() == 50    # 5 / 10 = 50%


def test_panel_progress_bar_clamps_at_100(qtbot, ctx) -> None:
    ctx.plugin_settings("wordcount")["target"] = 3
    panel = _build_panel(qtbot, ctx)
    plugin_api._set_active_document_provider(
        lambda: _make_doc(qtbot, "one two three four five"),
    )
    dispatch(SignalKind.CONTENT_CHANGED, plugin_api.get_active_document(), disabled=set())
    bar = panel.findChild(QProgressBar)
    assert bar.value() == 100


def test_panel_target_change_persists_to_settings(qtbot, ctx) -> None:
    panel = _build_panel(qtbot, ctx)
    spinner = panel.findChild(QSpinBox)
    spinner.setValue(750)
    assert ctx.plugin_settings("wordcount").get("target") == 750


def test_panel_responds_to_file_opened_signal(qtbot, ctx) -> None:
    panel = _build_panel(qtbot, ctx)
    plugin_api._set_active_document_provider(
        lambda: _make_doc(qtbot, "hello world"),
    )
    dispatch(SignalKind.FILE_OPENED, plugin_api.get_active_document(), disabled=set())
    assert "2" in panel.count_label.text()


def test_signal_handler_with_no_active_document_is_safe(qtbot, ctx) -> None:
    """Handler is called when there's no active document — must not raise."""
    _build_panel(qtbot, ctx)
    plugin_api._set_active_document_provider(lambda: None)

    # Get the registered handler and call it through dispatch
    # with a fake doc that won't be used (handler ignores its arg
    # and reads via get_active_document).
    fake = _make_doc(qtbot, "anything")
    dispatch(SignalKind.CONTENT_CHANGED, fake, disabled=set())
    # No assertion needed — just verify no exception.

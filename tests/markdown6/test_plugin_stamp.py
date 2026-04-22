"""End-to-end tests for the `stamp` example plugin.

The stamp plugin demonstrates the schema-driven Configure UI by
declaring a settings schema with every supported field type
(str / str+choices / str+multiline / int with bounds / bool) and
an action that uses the stored values.

The reference implementation lives under ``docs/plugins-examples/``;
the tests use a self-contained copy in ``tests/markdown6/fixtures/plugins/``
so the test suite never reaches outside the test tree.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource, PluginStatus

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


def _make_doc(qtbot, text: str = "") -> DocumentHandle:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    return DocumentHandle(tab)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_stamp_plugin_loads_clean(ctx) -> None:
    plugins = load_all(
        [(FIXTURES_DIR, PluginSource.USER)], user_disabled=set(),
    )
    by_name = {p.name: p for p in plugins}
    assert "stamp" in by_name
    assert by_name["stamp"].status == PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# Schema registration: covers all supported field types
# ---------------------------------------------------------------------------


def test_stamp_registers_schema_with_all_field_types(ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    schema = plugin_api._REGISTRY.get_settings_schema("stamp")
    assert schema is not None
    by_key = {f.key: f for f in schema.fields}

    assert by_key["text"].type is str
    assert by_key["position"].type is str
    assert by_key["position"].choices is not None
    assert by_key["repeat"].type is int
    assert by_key["repeat"].min == 1
    assert by_key["repeat"].max == 20
    assert by_key["include_timestamp"].type is bool
    assert by_key["notes"].widget == "multiline"


def test_stamp_registers_action(ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    ids = [a.id for a in plugin_api._REGISTRY.actions()]
    assert "stamp.insert" in ids


# ---------------------------------------------------------------------------
# Action invocation reads values from plugin_settings
# ---------------------------------------------------------------------------


def test_stamp_action_uses_default_text(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    assert "—Stamp—" in doc.text


def test_stamp_action_uses_configured_text(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    ctx.plugin_settings("stamp")["text"] = "★REVIEW★"
    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    assert "★REVIEW★" in doc.text


def test_stamp_action_repeats_count_times(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    ctx.plugin_settings("stamp")["text"] = "X"
    ctx.plugin_settings("stamp")["repeat"] = 5
    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    assert doc.text == "XXXXX"


def test_stamp_action_position_line_end(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    ctx.plugin_settings("stamp")["text"] = "END"
    ctx.plugin_settings("stamp")["position"] = "line-end"
    doc = _make_doc(qtbot, text="hello world")
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    assert doc.text.endswith("END")


def test_stamp_action_position_line_start(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    ctx.plugin_settings("stamp")["text"] = "TOP"
    ctx.plugin_settings("stamp")["position"] = "line-start"
    doc = _make_doc(qtbot, text="hello")
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    assert doc.text.startswith("TOP")


def test_stamp_action_includes_timestamp_when_enabled(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]

    ctx.plugin_settings("stamp")["text"] = "Note"
    ctx.plugin_settings("stamp")["include_timestamp"] = True
    doc = _make_doc(qtbot)
    plugin_api._set_active_document_provider(lambda: doc)

    action.callback()
    # Loose check: timestamp format is "YYYY-MM-DD HH:MM" - assert the
    # YYYY-MM-DD portion is present.
    assert "Note" in doc.text
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", doc.text), \
        f"expected timestamp in {doc.text!r}"


def test_stamp_action_no_active_document_is_noop(qtbot, ctx) -> None:
    load_all([(FIXTURES_DIR, PluginSource.USER)], user_disabled=set())
    [action] = [a for a in plugin_api._REGISTRY.actions() if a.id == "stamp.insert"]
    plugin_api._set_active_document_provider(lambda: None)

    action.callback()  # must not raise

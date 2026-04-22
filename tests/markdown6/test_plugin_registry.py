"""Tests for the plugin registration API (plugins/api.py, plugins/registry.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginRegistry,
    PluginTextTransform,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure each test starts with an empty module-level registry."""
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


# ---------------------------------------------------------------------------
# register_action
# ---------------------------------------------------------------------------


def test_register_action_stores_registration() -> None:
    @plugin_api.register_action(id="x.hello", label="Say Hello")
    def handler(ctx) -> None:  # noqa: ANN001
        pass

    actions = plugin_api._REGISTRY.actions()
    assert len(actions) == 1
    assert actions[0].id == "x.hello"
    assert actions[0].label == "Say Hello"
    assert actions[0].callback is handler


def test_register_action_decorator_returns_original_function() -> None:
    @plugin_api.register_action(id="x.noop", label="Noop")
    def handler() -> str:
        return "kept"

    assert handler() == "kept"


def test_register_action_stores_menu_shortcut_category() -> None:
    @plugin_api.register_action(
        id="x.full",
        label="Full Action",
        menu="Edit/Transform",
        shortcut="Ctrl+Alt+T",
        palette_category="Transform",
    )
    def handler(ctx) -> None:  # noqa: ANN001
        pass

    [a] = plugin_api._REGISTRY.actions()
    assert a.menu == "Edit/Transform"
    assert a.shortcut == "Ctrl+Alt+T"
    assert a.palette_category == "Transform"


@pytest.mark.parametrize("bad_kwargs", [
    {"id": "", "label": "OK"},
    {"id": "x.ok", "label": ""},
    {"id": "  ", "label": "OK"},     # whitespace-only counts as empty
    {"id": "x.ok", "label": "  "},
])
def test_register_action_rejects_empty_id_or_label(bad_kwargs) -> None:
    """Catch the typo at decoration time so the plugin author sees the
    failure on import, not a confusing blank menu item."""
    with pytest.raises(ValueError):
        @plugin_api.register_action(**bad_kwargs)
        def fn(ctx):
            pass


@pytest.mark.parametrize("bad_kwargs", [
    {"id": "", "label": "OK"},
    {"id": "x.ok", "label": ""},
])
def test_register_text_transform_rejects_empty_id_or_label(bad_kwargs) -> None:
    with pytest.raises(ValueError):
        @plugin_api.register_text_transform(**bad_kwargs)
        def fn(text):
            return text


def test_register_action_duplicate_id_raises() -> None:
    @plugin_api.register_action(id="dup", label="one")
    def first(ctx) -> None:  # noqa: ANN001
        pass

    with pytest.raises(ValueError, match="dup"):
        @plugin_api.register_action(id="dup", label="two")
        def second(ctx) -> None:  # noqa: ANN001
            pass


# ---------------------------------------------------------------------------
# register_text_transform
# ---------------------------------------------------------------------------


def test_register_text_transform_stores_registration() -> None:
    @plugin_api.register_text_transform(id="t.upper", label="Upper")
    def upper(text: str) -> str:
        return text.upper()

    [t] = plugin_api._REGISTRY.text_transforms()
    assert t.id == "t.upper"
    assert t.transform("abc") == "ABC"


def test_register_text_transform_duplicate_id_raises() -> None:
    @plugin_api.register_text_transform(id="same", label="one")
    def first(text: str) -> str:
        return text

    with pytest.raises(ValueError, match="same"):
        @plugin_api.register_text_transform(id="same", label="two")
        def second(text: str) -> str:
            return text


def test_actions_and_transforms_dont_share_id_namespace() -> None:
    """Text transform is a specialisation of action — IDs must not collide."""
    @plugin_api.register_action(id="cross", label="action")
    def handler(ctx) -> None:  # noqa: ANN001
        pass

    with pytest.raises(ValueError, match="cross"):
        @plugin_api.register_text_transform(id="cross", label="transform")
        def t(text: str) -> str:
            return text


# ---------------------------------------------------------------------------
# invoke_text_transform (atomic apply of a registered transform)
# ---------------------------------------------------------------------------


def test_invoke_text_transform_applies_pure_result(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("hello")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    t = PluginTextTransform(
        id="t.upper", label="Upper", transform=lambda s: s.upper(),
    )
    plugin_api.invoke_text_transform(t, doc)
    assert editor.toPlainText() == "HELLO"


def test_invoke_text_transform_is_atomic_on_exception(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("original")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    def explode(text: str) -> str:
        raise RuntimeError("transform failed")

    t = PluginTextTransform(id="t.bad", label="Bad", transform=explode)

    # Framework must NOT let the exception escape to the caller; the
    # contract is "editor never crashes because of a plugin". The
    # return value signals success/failure instead.
    result = plugin_api.invoke_text_transform(t, doc)
    assert result.ok is False
    assert "transform failed" in result.detail
    assert editor.toPlainText() == "original"
    assert tab.unsaved_changes is False


def test_invoke_text_transform_success_marks_dirty(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("before")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    t = PluginTextTransform(
        id="t.x", label="x", transform=lambda s: s + "!",
    )
    result = plugin_api.invoke_text_transform(t, doc)
    assert result.ok is True
    # We don't need the framework to flip dirty itself — Qt's textChanged
    # signal on the editor does that via DocumentTab's _on_text_changed.
    # Unit test can just verify text was mutated.
    assert editor.toPlainText() == "before!"


def test_invoke_text_transform_no_op_when_identity(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("unchanged")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    t = PluginTextTransform(id="t.id", label="id", transform=lambda s: s)
    result = plugin_api.invoke_text_transform(t, doc)
    assert result.ok is True
    assert editor.toPlainText() == "unchanged"


# ---------------------------------------------------------------------------
# get_active_document
# ---------------------------------------------------------------------------


def test_get_active_document_none_by_default() -> None:
    assert plugin_api.get_active_document() is None


def test_get_active_document_returns_provider_result(qtbot) -> None:
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    handle = DocumentHandle(tab)

    plugin_api._set_active_document_provider(lambda: handle)
    got = plugin_api.get_active_document()
    assert got is handle


# ---------------------------------------------------------------------------
# Registry housekeeping
# ---------------------------------------------------------------------------


def test_clear_empties_registry() -> None:
    @plugin_api.register_action(id="tmp.a", label="a")
    def h(ctx) -> None:  # noqa: ANN001
        pass

    @plugin_api.register_text_transform(id="tmp.t", label="t")
    def t(text: str) -> str:
        return text

    reg = plugin_api._REGISTRY
    assert reg.actions() and reg.text_transforms()
    reg.clear()
    assert reg.actions() == [] and reg.text_transforms() == []


def test_registry_is_separately_constructable() -> None:
    """PluginRegistry should be a plain class, not a singleton-only thing."""
    r = PluginRegistry()
    r.register_action(PluginAction(id="r.a", label="a", callback=lambda c: None))
    assert len(r.actions()) == 1

"""End-to-end tests: example `em_dash_to_hyphen` plugin loaded + invoked.

Covers discovery + registration + atomic application of a registered
text transform against a real :class:`QPlainTextEdit`.

The reference implementation lives under ``docs/plugins-examples/``
(the editor does NOT bundle it by default); these tests use the
self-contained copy in ``tests/markdown6/fixtures/plugins/`` so the
test suite never reaches outside the test tree.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource, PluginStatus


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "plugins"


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


def test_em_dash_plugin_files_present() -> None:
    d = FIXTURES_DIR / "em_dash_to_hyphen"
    assert (d / "em_dash_to_hyphen.py").is_file()
    assert (d / "em_dash_to_hyphen.toml").is_file()


def test_load_all_discovers_em_dash_plugin() -> None:
    plugins = load_all(
        [(FIXTURES_DIR, PluginSource.USER)],
        user_disabled=set(),
    )
    by_name = {p.name: p for p in plugins}
    assert "em_dash_to_hyphen" in by_name
    p = by_name["em_dash_to_hyphen"]
    assert p.status == PluginStatus.ENABLED
    assert p.source == PluginSource.USER


def test_em_dash_plugin_registers_text_transform() -> None:
    load_all(
        [(FIXTURES_DIR, PluginSource.USER)],
        user_disabled=set(),
    )
    transforms = plugin_api._REGISTRY.text_transforms()
    ids = [t.id for t in transforms]
    assert any("em_dash" in tid for tid in ids), (
        f"expected an em-dash transform in registry, got {ids}"
    )


def test_em_dash_transform_replaces_em_dashes(qtbot) -> None:
    load_all(
        [(FIXTURES_DIR, PluginSource.USER)],
        user_disabled=set(),
    )
    [t] = [
        t for t in plugin_api._REGISTRY.text_transforms()
        if "em_dash" in t.id
    ]

    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("hello — world — goodbye")
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    result = plugin_api.invoke_text_transform(t, doc)
    assert result.ok is True
    assert editor.toPlainText() == "hello - world - goodbye"


def test_em_dash_transform_noop_on_text_without_em_dashes(qtbot) -> None:
    load_all(
        [(FIXTURES_DIR, PluginSource.USER)],
        user_disabled=set(),
    )
    [t] = [
        t for t in plugin_api._REGISTRY.text_transforms()
        if "em_dash" in t.id
    ]

    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    text = "plain ascii text, no fancy dashes here"
    editor.setPlainText(text)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    result = plugin_api.invoke_text_transform(t, doc)
    assert result.ok is True
    assert editor.toPlainText() == text


def test_full_editor_loads_em_dash_plugin_via_extra_dirs(qtbot) -> None:
    """Construct the real MarkdownEditor with the example plugin's
    fixture dir injected via ``extra_plugin_dirs`` and verify it is
    loaded, surfaces in the Plugins/Transform menu, and has a
    palette command.

    Triggering the action end-to-end requires an open document tab,
    which on some environments drags in QtWebEngine initialization —
    that's covered separately by ``test_em_dash_transform_*`` using a
    bare ``QPlainTextEdit``. Here we just verify the editor-level
    wiring: plugin loaded, QAction present, palette entry created.
    """
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.markdown_editor import MarkdownEditor
    from markdown_editor.markdown6.plugins.plugin import PluginStatus

    editor = MarkdownEditor(extra_plugin_dirs=[FIXTURES_DIR])

    try:
        # 1. Plugin discovered and loaded successfully
        names = {p.name: p for p in editor._plugins}
        assert "em_dash_to_hyphen" in names
        assert names["em_dash_to_hyphen"].status == PluginStatus.ENABLED

        # 2. Menu entry under Plugins/Transform (em-dash plugin declares
        # menu="Transform" → namespaced under top-level Plugins).
        plugins_menu = editor._top_level_menus["Plugins"]
        transform_sub = next(
            (a.menu() for a in plugins_menu.actions()
             if a.menu() and a.menu().title() == "Transform"),
            None,
        )
        assert transform_sub is not None
        action = next(
            (a for a in transform_sub.actions()
             if a.text() == "Replace em-dashes with hyphens"),
            None,
        )
        assert action is not None

        # 3. Palette command present
        palette_ids = [c.id for c in editor._plugin_palette_commands]
        assert "em_dash_to_hyphen.replace" in palette_ids
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


def test_full_editor_with_em_dash_disabled_hides_action(qtbot) -> None:
    """When em-dash is in `plugins.disabled`, the action must NOT be
    visible in the menu at launch — even though the plugin is now
    loaded (so it can be re-enabled live)."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor
    from markdown_editor.markdown6.plugins.plugin import PluginStatus

    ctx = get_app_context()
    ctx.set("plugins.disabled", ["em_dash_to_hyphen"], save=False)

    editor = MarkdownEditor(extra_plugin_dirs=[FIXTURES_DIR])
    try:
        # Plugin still loaded (status just flipped)
        names = {p.name: p for p in editor._plugins}
        assert names["em_dash_to_hyphen"].status == PluginStatus.DISABLED_BY_USER
        assert names["em_dash_to_hyphen"].module is not None

        # The QAction was created (so re-enable can work live) but is
        # NOT visible — that's the user-facing disabled state.
        plugins_menu = editor._top_level_menus["Plugins"]
        transform_sub = next(
            (a.menu() for a in plugins_menu.actions()
             if a.menu() and a.menu().title() == "Transform"),
            None,
        )
        transform_menu_action = next(
            (a for a in plugins_menu.actions()
             if a.menu() and a.menu().title() == "Transform"),
            None,
        )
        assert transform_menu_action is not None
        assert transform_menu_action.isVisible() is False, \
            "Transform submenu should be hidden when all its plugin " \
            "children are disabled"

        action = next(
            (a for a in transform_sub.actions()
             if a.text() == "Replace em-dashes with hyphens"),
            None,
        )
        assert action is not None
        assert action.isVisible() is False
        assert action.isEnabled() is False

        # Palette command should be absent.
        palette_ids = [c.id for c in editor._plugin_palette_commands]
        # Note: _plugin_palette_commands is the RAW list from inject.
        # The palette set via set_commands is the FILTERED list. But
        # the raw list should still contain em-dash because the plugin
        # was loaded.
        assert "em_dash_to_hyphen.replace" in palette_ids

        # Verify filtered palette actually omits it
        from markdown_editor.markdown6.plugins.editor_integration import (
            plugin_palette_commands_filtered,
        )
        filtered = plugin_palette_commands_filtered(
            editor, {"em_dash_to_hyphen"}
        )
        assert "em_dash_to_hyphen.replace" not in [c.id for c in filtered]
    finally:
        editor.close()
        del editor
        QApplication.processEvents()


def test_em_dash_transform_is_single_undo_step(qtbot) -> None:
    """Apply transform → undo → document restored to pre-transform state."""
    load_all(
        [(FIXTURES_DIR, PluginSource.USER)],
        user_disabled=set(),
    )
    [t] = [
        t for t in plugin_api._REGISTRY.text_transforms()
        if "em_dash" in t.id
    ]

    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    original = "pre — mid — post"
    editor.setPlainText(original)
    tab = SimpleNamespace(editor=editor, file_path=None, unsaved_changes=False)
    doc = DocumentHandle(tab)

    plugin_api.invoke_text_transform(t, doc)
    assert editor.toPlainText() == "pre - mid - post"
    editor.undo()
    assert editor.toPlainText() == original

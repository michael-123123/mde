"""End-to-end tests: bundled builtin plugins discovered + loaded + invoked.

Covers the full Phase 1 happy path:

1. The loader's builtin root points at a directory containing a plugin.
2. Discovery + import succeed; the plugin registers a text transform.
3. ``invoke_text_transform`` applies the transform atomically to a
   :class:`DocumentHandle` wrapping a real :class:`QPlainTextEdit`.
4. Constructing a full :class:`MarkdownEditor` loads the plugin, wires
   the QAction into ``Edit/Transform``, and registers the palette
   command.

**QtWebEngine hang caveat (read before adding tests here):** tests that
construct ``MarkdownEditor()`` must NOT call ``editor.new_tab()``,
``editor.open_file()``, or trigger any action that creates a
``DocumentTab``. Under pytest-xvfb, the first ``QWebEngineView``
initialization inside a ``DocumentTab`` hangs indefinitely (zygote
subprocesses never complete against the minimal xvfb display) — even
``pytest-timeout --signal`` doesn't reliably cut through it.

For action-triggering end-to-end verification, use a bare
``QPlainTextEdit`` + ``SimpleNamespace`` stand-in for the tab, as
``test_em_dash_transform_*`` below does. The full-editor test here
(``test_full_editor_loads_em_dash_plugin``) deliberately stops at
attribute inspection — it verifies wiring, not runtime behavior.

We use the ``em_dash_to_hyphen`` builtin (the reference plugin shipped
in-tree) as the fixture. If this test ever needs to exercise plugin
*discovery failures* end-to-end, add a separate test module with
fixtures under ``tests/markdown6/fixtures/plugins/`` — don't pollute
the bundled builtins for test scaffolding.
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


BUILTIN_PLUGINS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "markdown_editor"
    / "markdown6"
    / "builtin_plugins"
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


def test_builtin_plugins_dir_exists() -> None:
    """The builtin plugin dir must exist and be a package-relative path
    so wheels include it."""
    assert BUILTIN_PLUGINS_DIR.is_dir()


def test_em_dash_plugin_files_present() -> None:
    d = BUILTIN_PLUGINS_DIR / "em_dash_to_hyphen"
    assert (d / "em_dash_to_hyphen.py").is_file()
    assert (d / "em_dash_to_hyphen.toml").is_file()


def test_load_all_discovers_em_dash_plugin() -> None:
    plugins = load_all(
        [(BUILTIN_PLUGINS_DIR, PluginSource.BUILTIN)],
        user_disabled=set(),
    )
    by_name = {p.name: p for p in plugins}
    assert "em_dash_to_hyphen" in by_name
    p = by_name["em_dash_to_hyphen"]
    assert p.status == PluginStatus.ENABLED
    assert p.source == PluginSource.BUILTIN


def test_em_dash_plugin_registers_text_transform() -> None:
    load_all(
        [(BUILTIN_PLUGINS_DIR, PluginSource.BUILTIN)],
        user_disabled=set(),
    )
    transforms = plugin_api._REGISTRY.text_transforms()
    ids = [t.id for t in transforms]
    assert any("em_dash" in tid for tid in ids), (
        f"expected an em-dash transform in registry, got {ids}"
    )


def test_em_dash_transform_replaces_em_dashes(qtbot) -> None:
    load_all(
        [(BUILTIN_PLUGINS_DIR, PluginSource.BUILTIN)],
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
        [(BUILTIN_PLUGINS_DIR, PluginSource.BUILTIN)],
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


def test_full_editor_loads_em_dash_plugin(qtbot) -> None:
    """Construct the real MarkdownEditor and verify the em-dash builtin
    plugin is loaded, surfaces in the Edit/Transform menu, and has a
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

    editor = MarkdownEditor()

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
    """Reproduces the user-reported bug: when em-dash is in
    `plugins.disabled`, the action must NOT be visible in the menu
    at launch — even though the plugin is now loaded (so it can be
    re-enabled live)."""
    from PySide6.QtWidgets import QApplication

    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor
    from markdown_editor.markdown6.plugins.plugin import PluginStatus

    ctx = get_app_context()
    ctx.set("plugins.disabled", ["em_dash_to_hyphen"], save=False)

    editor = MarkdownEditor()
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
        [(BUILTIN_PLUGINS_DIR, PluginSource.BUILTIN)],
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

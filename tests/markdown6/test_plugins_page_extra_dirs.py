"""Tests for the extra-plugin-dirs section of the Plugins settings page.

The page lets the user maintain a persistent list of additional plugin
directories (``plugins.extra_dirs``). The directories themselves are
scanned by :meth:`MarkdownEditor._plugin_roots`; this test focuses on
the UI's read/write contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugins_page import (
    PluginsSettingsPage,
)


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


def test_initial_extra_dirs_loaded_from_settings(qtbot, ctx, tmp_path: Path):
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    ctx.set("plugins.extra_dirs", [str(a), str(b)], save=False)

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.pending_extra_dirs() == [str(a), str(b)]


def test_add_extra_dir_appends_to_pending(qtbot, ctx, tmp_path: Path):
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.pending_extra_dirs() == []

    new_dir = tmp_path / "added"
    new_dir.mkdir()
    page.add_extra_dir(new_dir)
    assert page.pending_extra_dirs() == [str(new_dir)]


def test_add_duplicate_extra_dir_is_ignored(qtbot, ctx, tmp_path: Path):
    """Re-adding the same path is a no-op so the list stays unique."""
    d = tmp_path / "x"
    d.mkdir()
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(d)
    page.add_extra_dir(d)
    assert page.pending_extra_dirs() == [str(d)]


def test_remove_extra_dir_drops_from_pending(qtbot, ctx, tmp_path: Path):
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    ctx.set("plugins.extra_dirs", [str(a), str(b)], save=False)

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.remove_extra_dir(str(a))
    assert page.pending_extra_dirs() == [str(b)]


def test_apply_persists_extra_dirs_to_settings(qtbot, ctx, tmp_path: Path):
    d = tmp_path / "persisted"
    d.mkdir()

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(d)
    page.apply()

    assert ctx.get("plugins.extra_dirs") == [str(d)]


def test_apply_with_no_changes_keeps_existing_extra_dirs(
    qtbot, ctx, tmp_path: Path,
):
    """A user opening Settings → Plugins and clicking Apply without
    touching the extra-dirs list must not blow away what's already
    in settings."""
    a = tmp_path / "kept"
    a.mkdir()
    ctx.set("plugins.extra_dirs", [str(a)], save=False)

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.apply()

    assert ctx.get("plugins.extra_dirs") == [str(a)]

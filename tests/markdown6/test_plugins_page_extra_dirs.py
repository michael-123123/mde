"""Tests for the extra-plugin-dirs section of the Plugins settings page.

The page lets the user maintain a persistent list of additional plugin
directories (``plugins.extra_dirs``). The directories themselves are
scanned by :meth:`MarkdownEditor._plugin_roots`; this test focuses on
the UI's read/write contract.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugins_page import (
    PluginsSettingsPage,
)
from markdown_editor.markdown6.plugins.plugin import PluginSource


def _make_plugin_dir(root: Path, name: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.toml").write_text(textwrap.dedent(f"""
        [tool.mde.plugin]
        name = "{name}"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (d / f"{name}.py").write_text("", encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Size: the list must not monopolize vertical space
# ---------------------------------------------------------------------------


def test_extra_dirs_list_has_bounded_height(qtbot, ctx):
    """The QListWidget must have a maximum height so it doesn't
    dominate the Plugins page (the installed-plugin list is the main
    content)."""
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page._extra_dirs_list is not None
    # 150 is a generous cap — four to five rows is the expectation;
    # the current design is tighter than that.
    assert page._extra_dirs_list.maximumHeight() <= 150


# ---------------------------------------------------------------------------
# No Reload button — add/remove auto-discover, apply posts a warning
# ---------------------------------------------------------------------------


def test_reload_button_is_removed(qtbot, ctx):
    """The Reload button is gone. Auto-discover on Add/Remove replaces it."""
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.reload_button is None


def test_add_extra_dir_auto_detects_plugins_in_inline_label(
    qtbot, ctx, tmp_path: Path,
):
    """The moment the user adds a directory, the inline label must
    reflect what was detected in it — no Reload / Apply click needed."""
    extra = tmp_path / "extra"
    extra.mkdir()
    _make_plugin_dir(extra, "auto_detected")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(extra)

    status = page.reload_status_text()
    assert "auto_detected" in status


def test_remove_extra_dir_refreshes_inline_label(
    qtbot, ctx, tmp_path: Path,
):
    """Removing a dir must update the inline label to reflect the new
    pending scan set."""
    extra_a = tmp_path / "a"
    extra_a.mkdir()
    _make_plugin_dir(extra_a, "plug_a")
    extra_b = tmp_path / "b"
    extra_b.mkdir()
    _make_plugin_dir(extra_b, "plug_b")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(extra_a)
    page.add_extra_dir(extra_b)
    assert "plug_a" in page.reload_status_text()
    assert "plug_b" in page.reload_status_text()

    page.remove_extra_dir(str(extra_b))
    status = page.reload_status_text()
    assert "plug_a" in status
    assert "plug_b" not in status


def test_inline_label_carries_warning_symbol_after_detection(
    qtbot, ctx, tmp_path: Path,
):
    """The inline label includes a warning symbol so the user sees
    that a restart is required before the plugins actually load."""
    extra = tmp_path / "extra"
    extra.mkdir()
    _make_plugin_dir(extra, "needs_restart")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(extra)

    assert "⚠" in page.reload_status_text()
    assert "restart" in page.reload_status_text().lower()


def test_apply_with_changed_dirs_posts_warning_notification(
    qtbot, ctx, tmp_path: Path,
):
    """Apply / OK must surface the change in the notification area as
    a WARNING severity entry — the dialog is about to close, so the
    inline label is no longer visible."""
    from markdown_editor.markdown6.notifications import Severity

    extra = tmp_path / "extra"
    extra.mkdir()
    _make_plugin_dir(extra, "on_apply")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(extra)
    before = len(ctx.notifications.all())
    page.apply()
    after = ctx.notifications.all()
    assert len(after) == before + 1

    note = after[-1]
    assert note.severity == Severity.WARNING
    # Bold + warning symbol in the title; restart instruction in body.
    assert "⚠" in note.title
    assert "restart" in note.message.lower()


def test_second_removal_accumulates_in_removed_list(
    qtbot, ctx, tmp_path: Path,
):
    """Regression: removing two directories back-to-back must list
    both dirs' plugins as "Would be removed". The first removal used
    to show correctly but the second one wasn't accumulating."""
    from markdown_editor.markdown6.plugins.loader import discover_plugins

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    _make_plugin_dir(dir_a, "plug_a")
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    _make_plugin_dir(dir_b, "plug_b")

    loaded = discover_plugins([
        (dir_a, PluginSource.USER),
        (dir_b, PluginSource.USER),
    ])
    ctx.set_plugins(loaded)
    ctx.set("plugins.extra_dirs", [str(dir_a), str(dir_b)], save=False)

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    page.remove_extra_dir(str(dir_a))
    first = page.reload_status_text()
    assert "plug_a" in first, f"first remove should list plug_a; got {first!r}"

    page.remove_extra_dir(str(dir_b))
    second = page.reload_status_text()
    assert "plug_a" in second, f"second remove should still list plug_a; got {second!r}"
    assert "plug_b" in second, f"second remove should also list plug_b; got {second!r}"


def test_remove_directory_shows_plugins_that_will_be_removed(
    qtbot, ctx, tmp_path: Path,
):
    """Removing a directory that contained currently-loaded plugins
    surfaces them in the preview — user sees exactly which plugins
    will vanish after restart."""
    from markdown_editor.markdown6.plugins.loader import discover_plugins

    extra = tmp_path / "x"
    extra.mkdir()
    _make_plugin_dir(extra, "loaded_from_x")

    # Simulate the editor having already loaded this plugin at
    # startup: put it in ctx.plugins and in the persisted extra_dirs.
    loaded = discover_plugins([(extra, PluginSource.USER)])
    ctx.set_plugins(loaded)
    ctx.set("plugins.extra_dirs", [str(extra)], save=False)

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    # User removes the directory.
    page.remove_extra_dir(str(extra))

    status = page.reload_status_text().lower()
    assert "loaded_from_x" in status
    assert "remove" in status or "removed" in status or "gone" in status


def test_broken_plugin_in_added_dir_surfaces_in_preview(
    qtbot, ctx, tmp_path: Path,
):
    """If the new directory contains a plugin with a detectable
    problem (bad TOML, missing deps, API mismatch), the preview must
    call it out — the user shouldn't have to restart to find out
    something is wrong."""
    extra = tmp_path / "extra"
    extra.mkdir()

    # Plugin whose directory name doesn't match its TOML [tool.mde.plugin].name
    # → discover_plugins marks it METADATA_ERROR with a clear reason.
    broken = extra / "broken_dir"
    broken.mkdir()
    (broken / "broken_dir.toml").write_text(
        textwrap.dedent("""
            [tool.mde.plugin]
            name = "mismatched"
            version = "1.0"
        """).lstrip(), encoding="utf-8",
    )
    (broken / "broken_dir.py").write_text("", encoding="utf-8")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.add_extra_dir(extra)

    status = page.reload_status_text()
    # Plugin name and error keyword must both be in the preview.
    assert "broken_dir" in status
    assert "metadata_error" in status.lower() or "error" in status.lower()


def test_apply_with_unchanged_dirs_posts_no_notification(
    qtbot, ctx,
):
    """If the user didn't touch the extra-dirs list, Apply must not
    post a warning notification."""
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    before = len(ctx.notifications.all())
    page.apply()
    after = ctx.notifications.all()
    assert len(after) == before

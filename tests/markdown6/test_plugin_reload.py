"""Tests for the "Reload plugins" command (discover-only refresh).

Re-runs discovery on the same plugin roots, diffs against the
in-process plugin list, and posts a NotificationCenter entry listing
what's new on disk vs. what's been removed. Does NOT hot-reload
existing plugins (their code stays as-is in memory) - that's why the
notification recommends a restart for changes to take effect.

This v1 scope honestly reflects what we can safely do without
unwiring connected QActions, panel widgets, signal handlers, etc.
The full hot-reload story is a Phase N concern.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.notifications import Severity
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource
from markdown_editor.markdown6.plugins.reload import reload_plugins


@pytest.fixture
def ctx(tmp_path: Path):
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(config_dir=tmp_path, ephemeral=False)
    yield c
    ctx_mod._app_context = None


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


def _make_plugin_dir(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.toml").write_text(textwrap.dedent(f"""
        [tool.mde.plugin]
        name = "{name}"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (d / f"{name}.py").write_text("# clean\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# No changes on disk
# ---------------------------------------------------------------------------


def test_reload_no_changes_posts_neutral_notification(ctx, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _make_plugin_dir(plugins_root, "p1")

    initial = load_all([(plugins_root, PluginSource.USER)], user_disabled=set())
    ctx.set_plugins(initial)

    diff = reload_plugins(ctx, [(plugins_root, PluginSource.USER)])
    assert diff.added == []
    assert diff.removed == []

    [n] = ctx.notifications.all()
    assert n.severity is Severity.INFO
    assert "no" in n.title.lower() or "no" in n.message.lower()


# ---------------------------------------------------------------------------
# New plugin on disk
# ---------------------------------------------------------------------------


def test_reload_detects_new_plugin(ctx, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _make_plugin_dir(plugins_root, "old_one")

    initial = load_all([(plugins_root, PluginSource.USER)], user_disabled=set())
    ctx.set_plugins(initial)

    # Drop a new plugin onto disk after the editor "started"
    _make_plugin_dir(plugins_root, "new_one")

    diff = reload_plugins(ctx, [(plugins_root, PluginSource.USER)])
    assert diff.added == ["new_one"]
    assert diff.removed == []

    [n] = ctx.notifications.all()
    assert "new_one" in n.message
    assert "restart" in n.message.lower()


def test_reload_lists_multiple_new_plugins(ctx, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    ctx.set_plugins([])    # editor started with nothing

    _make_plugin_dir(plugins_root, "alpha")
    _make_plugin_dir(plugins_root, "beta")
    _make_plugin_dir(plugins_root, "gamma")

    diff = reload_plugins(ctx, [(plugins_root, PluginSource.USER)])
    assert sorted(diff.added) == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# Plugin removed from disk
# ---------------------------------------------------------------------------


def test_reload_detects_removed_plugin(ctx, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _make_plugin_dir(plugins_root, "going_away")

    initial = load_all([(plugins_root, PluginSource.USER)], user_disabled=set())
    ctx.set_plugins(initial)

    # Remove from disk after the editor "started"
    import shutil
    shutil.rmtree(plugins_root / "going_away")

    diff = reload_plugins(ctx, [(plugins_root, PluginSource.USER)])
    assert diff.added == []
    assert diff.removed == ["going_away"]

    [n] = ctx.notifications.all()
    assert "going_away" in n.message


def test_reload_both_added_and_removed(ctx, tmp_path: Path) -> None:
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _make_plugin_dir(plugins_root, "stays")
    _make_plugin_dir(plugins_root, "going")

    initial = load_all([(plugins_root, PluginSource.USER)], user_disabled=set())
    ctx.set_plugins(initial)

    import shutil
    shutil.rmtree(plugins_root / "going")
    _make_plugin_dir(plugins_root, "arriving")

    diff = reload_plugins(ctx, [(plugins_root, PluginSource.USER)])
    assert diff.added == ["arriving"]
    assert diff.removed == ["going"]


# ---------------------------------------------------------------------------
# Builtin plugins are never reported as removed
# ---------------------------------------------------------------------------


def test_reload_does_not_report_builtins_as_removed(ctx, tmp_path: Path) -> None:
    """If the user plugin root is empty but the editor has builtin
    plugins loaded, reload must not falsely report builtins as removed."""
    user_root = tmp_path / "user_plugins"
    user_root.mkdir()
    builtin_root = tmp_path / "builtin_plugins"
    builtin_root.mkdir()
    _make_plugin_dir(builtin_root, "bundled")

    initial = load_all(
        [(builtin_root, PluginSource.BUILTIN),
         (user_root, PluginSource.USER)],
        user_disabled=set(),
    )
    ctx.set_plugins(initial)

    diff = reload_plugins(
        ctx,
        [(builtin_root, PluginSource.BUILTIN),
         (user_root, PluginSource.USER)],
    )
    assert "bundled" not in diff.removed


# ---------------------------------------------------------------------------
# In-process state isn't disturbed by reload
# ---------------------------------------------------------------------------


def test_reload_does_not_modify_editor_plugins_list(ctx, tmp_path: Path) -> None:
    """Discover-only contract: reload does NOT swap out editor._plugins.
    Existing plugins keep their state; reload only reports diff."""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _make_plugin_dir(plugins_root, "alive")

    initial = load_all([(plugins_root, PluginSource.USER)], user_disabled=set())
    ctx.set_plugins(initial)
    initial_id = id(initial[0])

    _make_plugin_dir(plugins_root, "fresh")
    reload_plugins(ctx, [(plugins_root, PluginSource.USER)])

    # editor._plugins should still hold the SAME objects we set initially
    after = ctx.get_plugins()
    assert len(after) == 1
    assert id(after[0]) == initial_id

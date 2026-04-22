"""Tests for the action buttons at the top of Settings → Plugins.

Covers the page-level controls (not per-plugin row controls):
* "Open plugins folder" — reveals the user plugin dir in the OS file
  manager via QDesktopServices, creating it on demand if needed.
* "Reload plugins" — re-runs discovery so newly-dropped plugin dirs
  are picked up without an editor restart (within limits — see the
  palette-command test).
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugins_page import PluginsSettingsPage
from markdown_editor.markdown6.plugins.metadata import PluginMetadata
from markdown_editor.markdown6.plugins.plugin import (Plugin, PluginSource,
                                                       PluginStatus)


@pytest.fixture
def ctx(tmp_path: Path):
    """Use a tmp_path-rooted, non-ephemeral context so the
    open-plugins-folder test can verify dir creation against a real
    filesystem path without polluting the user's real config dir."""
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(config_dir=tmp_path, ephemeral=False)
    yield c
    ctx_mod._app_context = None


def _stub_plugin(name: str = "p") -> Plugin:
    return Plugin(
        name=name,
        source=PluginSource.BUILTIN,
        directory=Path(f"/fake/{name}"),
        metadata=PluginMetadata(name=name, version="1.0"),
        status=PluginStatus.ENABLED,
    )


# ---------------------------------------------------------------------------
# Open plugins folder
# ---------------------------------------------------------------------------


def test_open_plugins_folder_button_exists(qtbot, ctx) -> None:
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.open_folder_button is not None
    assert page.open_folder_button.isEnabled() is True


def test_open_plugins_folder_creates_dir_if_missing(qtbot, ctx, tmp_path: Path) -> None:
    """Clicking Open Folder should create the plugin dir if a user
    has never installed a plugin before — saves them a confusing
    "folder doesn't exist" error from the file manager."""
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    expected = tmp_path / "plugins"
    assert not expected.exists()    # baseline: dir not yet created

    with mock.patch(
        "markdown_editor.markdown6.components.plugins_page.QDesktopServices",
    ) as mock_dsk:
        page.open_folder_button.click()

    assert expected.is_dir()
    mock_dsk.openUrl.assert_called_once()


def test_open_plugins_folder_passes_correct_path(qtbot, ctx, tmp_path: Path) -> None:
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    with mock.patch(
        "markdown_editor.markdown6.components.plugins_page.QDesktopServices",
    ) as mock_dsk:
        page.open_folder_button.click()

    [call] = mock_dsk.openUrl.call_args_list
    qurl = call.args[0]
    # QUrl has toLocalFile() — the local path it opens
    assert qurl.toLocalFile() == str(tmp_path / "plugins")


def test_open_plugins_folder_with_existing_dir_just_opens(qtbot, ctx, tmp_path: Path) -> None:
    """If the dir already exists, the button must not error or recreate it."""
    (tmp_path / "plugins").mkdir()
    sentinel = tmp_path / "plugins" / "sentinel.txt"
    sentinel.write_text("don't delete me")

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    with mock.patch(
        "markdown_editor.markdown6.components.plugins_page.QDesktopServices",
    ):
        page.open_folder_button.click()

    assert sentinel.exists()    # dir not recreated; sentinel survived


# ---------------------------------------------------------------------------
# Page renders even when no plugins are installed (page-action buttons
# are first-class regardless of plugin count)
# ---------------------------------------------------------------------------


def test_open_folder_button_present_with_no_plugins(qtbot, ctx) -> None:
    ctx.set_plugins([])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.open_folder_button is not None
    assert page.row_count() == 0


def test_open_folder_button_present_with_plugins(qtbot, ctx) -> None:
    ctx.set_plugins([_stub_plugin("a"), _stub_plugin("b")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.open_folder_button is not None


# ---------------------------------------------------------------------------
# Reload plugins
# ---------------------------------------------------------------------------


def test_reload_plugins_button_exists(qtbot, ctx) -> None:
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.reload_button is not None
    assert page.reload_button.isEnabled() is True


def test_reload_button_emits_reload_requested_signal(qtbot, ctx) -> None:
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    received: list[bool] = []
    page.reload_requested.connect(lambda: received.append(True))
    page.reload_button.click()
    assert received == [True]


def test_palette_has_reload_plugins_command() -> None:
    """The PALETTE_ONLY registry must include a reload-plugins entry
    so users can find it via Ctrl+Shift+P without opening Settings."""
    from markdown_editor.markdown6.actions import PALETTE_ONLY
    ids = [a.id for a in PALETTE_ONLY]
    assert "plugins.reload" in ids
    [reload_def] = [a for a in PALETTE_ONLY if a.id == "plugins.reload"]
    assert reload_def.method == "_reload_plugins"
    assert "reload" in reload_def.palette_name.lower()

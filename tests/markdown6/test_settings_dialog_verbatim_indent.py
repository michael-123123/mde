"""Round-trip test for the new ``editor.auto_indent_in_verbatim`` setting.

The Editor → Behavior section has a new checkbox "Auto-indent inside code
blocks and math". It must load the current setting and write it back when
the user clicks OK.
"""

from __future__ import annotations

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.settings_dialog import SettingsDialog


@pytest.fixture
def settings_dialog(qtbot):
    ctx = init_app_context(ephemeral=True)
    dlg = SettingsDialog(ctx)
    qtbot.addWidget(dlg)
    return dlg


def test_checkbox_exists(settings_dialog):
    """The dialog exposes an `auto_indent_in_verbatim` checkbox."""
    assert hasattr(settings_dialog, "auto_indent_in_verbatim")


def test_checkbox_loads_current_setting(settings_dialog):
    """The checkbox initial state matches the setting (defaults True)."""
    assert settings_dialog.auto_indent_in_verbatim.isChecked() is True


def test_checkbox_round_trips_to_setting(settings_dialog):
    """Toggle the checkbox + apply; the setting flips."""
    settings_dialog.auto_indent_in_verbatim.setChecked(False)
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.auto_indent_in_verbatim") is False

    settings_dialog.auto_indent_in_verbatim.setChecked(True)
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.auto_indent_in_verbatim") is True


# ── Image paste toggle + folder ────────────────────────────────────


def test_paste_image_widgets_exist(settings_dialog):
    """The dialog exposes the paste-image controls."""
    assert hasattr(settings_dialog, "paste_image_to_disk")
    assert hasattr(settings_dialog, "paste_image_dir")
    assert hasattr(settings_dialog, "paste_image_dir_browse")


def test_paste_image_defaults_loaded(settings_dialog):
    """Defaults: toggle on, folder empty."""
    assert settings_dialog.paste_image_to_disk.isChecked() is True
    assert settings_dialog.paste_image_dir.text() == ""


def test_paste_image_toggle_round_trips(settings_dialog):
    settings_dialog.paste_image_to_disk.setChecked(False)
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.paste_image_to_disk") is False
    settings_dialog.paste_image_to_disk.setChecked(True)
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.paste_image_to_disk") is True


def test_paste_image_dir_round_trips(settings_dialog, tmp_path):
    settings_dialog.paste_image_dir.setText(str(tmp_path))
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.paste_image_dir") == str(tmp_path)


def test_paste_image_dir_disabled_when_toggle_off(settings_dialog):
    """Folder controls grey out when the master toggle is off."""
    settings_dialog.paste_image_to_disk.setChecked(False)
    assert settings_dialog.paste_image_dir.isEnabled() is False
    assert settings_dialog.paste_image_dir_browse.isEnabled() is False
    settings_dialog.paste_image_to_disk.setChecked(True)
    assert settings_dialog.paste_image_dir.isEnabled() is True
    assert settings_dialog.paste_image_dir_browse.isEnabled() is True

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

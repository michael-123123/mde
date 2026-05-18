"""Settings → Diagnostics page (log level + future diagnostics knobs).

Closes a CLI/GUI parity gap: ``--log-level`` and ``MDE_LOG_LEVEL``
existed but had no GUI surface. This page is the third corner of the
unification - users can change log verbosity without touching shell
config.

Diagnostics is intentionally its own page rather than a tucked-into-
Files or External-Tools entry: it's a developer / power-user concern,
and the page is the natural home for future things like log-file
location, verbose-error-messages toggle, etc.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from markdown_editor.markdown6.components.settings_dialog import (
    SettingsDialog,
)


@pytest.fixture
def dialog(qtbot):
    from markdown_editor.markdown6.app_context import get_app_context
    d = SettingsDialog(get_app_context())
    qtbot.addWidget(d)
    QApplication.processEvents()
    return d


@pytest.mark.timeout(15, method="thread")
def test_diagnostics_page_has_log_level_dropdown(dialog):
    """The Diagnostics page exposes a log-level combo box wired to
    the ``log.level`` settings key."""
    # The widget is created as `self.log_level_combo` on the dialog
    # so _load_settings / _apply can find it.
    assert hasattr(dialog, "log_level_combo")
    assert isinstance(dialog.log_level_combo, QComboBox)


@pytest.mark.timeout(15, method="thread")
def test_log_level_dropdown_has_four_levels(dialog):
    """debug / info / warning / error - same set the CLI flag accepts."""
    items = [
        dialog.log_level_combo.itemText(i)
        for i in range(dialog.log_level_combo.count())
    ]
    assert set(items) == {"debug", "info", "warning", "error"}


@pytest.mark.timeout(15, method="thread")
def test_log_level_dropdown_loads_current_setting(qtbot):
    """The dropdown reflects the persisted ``log.level`` when the
    dialog opens."""
    from markdown_editor.markdown6.app_context import get_app_context
    ctx = get_app_context()
    ctx.set("log.level", "warning")
    d = SettingsDialog(ctx)
    qtbot.addWidget(d)
    assert d.log_level_combo.currentText() == "warning"


@pytest.mark.timeout(15, method="thread")
def test_diagnostics_page_in_category_list(dialog):
    """The page must be reachable from the category list - otherwise
    the dropdown exists in the stacked widget but no user can navigate
    to it."""
    items = [
        dialog.category_list.item(i).text()
        for i in range(dialog.category_list.count())
    ]
    assert "Diagnostics" in items


@pytest.mark.timeout(15, method="thread")
def test_applying_dialog_persists_log_level(dialog):
    """Selecting a level and clicking Apply writes through to
    ``log.level``."""
    dialog.log_level_combo.setCurrentText("debug")
    dialog._apply()
    assert dialog.ctx.get("log.level") == "debug"

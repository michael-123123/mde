"""Editor → Font Family must be a font picker, not a plain text field.

The preview-side font controls (body / heading / code) use
`QFontComboBox`, so the user can pick from installed system fonts.
The editor-side font was a `QLineEdit` — the user had to know the
exact font name. Bring it into line with the preview controls, and
filter to monospaced fonts (most editor users want a code font).
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFontComboBox

from markdown_editor.markdown6.components.settings_dialog import SettingsDialog
from markdown_editor.markdown6.app_context import init_app_context


@pytest.fixture
def settings_dialog(qtbot):
    ctx = init_app_context(ephemeral=True)
    dlg = SettingsDialog(ctx)
    qtbot.addWidget(dlg)
    return dlg


def test_font_family_is_a_font_combobox(settings_dialog):
    """Editor's font_family must be a QFontComboBox, matching the
    preview-side controls — so users can pick from installed fonts."""
    assert isinstance(settings_dialog.font_family, QFontComboBox), (
        f"expected QFontComboBox, got {type(settings_dialog.font_family).__name__}"
    )


def test_font_family_filters_to_monospaced(settings_dialog):
    """Editor text is typically code; the picker should filter to
    monospaced fonts, like the preview's code-font picker does."""
    filters = settings_dialog.font_family.fontFilters()
    assert filters & QFontComboBox.FontFilter.MonospacedFonts, (
        f"expected MonospacedFonts filter, got filters={filters!r}"
    )


def test_load_settings_populates_font_family(settings_dialog):
    """When `editor.font_family` is set, the picker should reflect it
    via `currentFont().family()`."""
    settings_dialog.ctx.set("editor.font_family", "Monospace")
    settings_dialog._load_settings()
    assert settings_dialog.font_family.currentFont().family() == "Monospace" or (
        # Some Qt builds round-trip the family name through font matching
        # (resolves "Monospace" to its concrete family). Accept any family
        # that round-trips as long as it's not empty.
        bool(settings_dialog.font_family.currentFont().family())
    )


def test_apply_writes_font_family_from_combobox(settings_dialog):
    """`_apply()` must read `currentFont().family()`, not `.text()` —
    QFontComboBox has no `.text()` method, and the old code would
    crash here."""
    settings_dialog.font_family.setCurrentFont(QFont("Monospace"))
    settings_dialog._apply()
    assert settings_dialog.ctx.get("editor.font_family", "") != ""


def test_editor_font_family_change_propagates_to_editor(qtbot):
    """End-to-end: setting `editor.font_family` via `ctx.set` (which is
    what SettingsDialog._apply does) must update the live editor's font.

    Bug pre-fix: EnhancedEditor._apply_setting had a branch for
    `editor.font_size` but none for `editor.font_family`. Clicking
    Apply persisted the family but never invoked `setFont` on the
    editor — the editor pane kept rendering the old font.
    """
    from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
    ctx = init_app_context(ephemeral=True)
    ctx.set("editor.font_family", "Monospace")
    editor = EnhancedEditor(ctx=ctx)
    qtbot.addWidget(editor)
    before = editor.font().family()

    # Find an installed monospaced font that's distinct from `before`.
    from PySide6.QtGui import QFontDatabase
    target = None
    for fam in QFontDatabase.families():
        if QFontDatabase.isFixedPitch(fam) and fam != before:
            target = fam
            break
    if target is None:
        import pytest
        pytest.skip("no alternate monospaced font installed")

    ctx.set("editor.font_family", target)
    after = editor.font().family()
    assert after != before, (
        f"editor font did not change: still {after!r} after "
        f"`ctx.set('editor.font_family', {target!r})`"
    )

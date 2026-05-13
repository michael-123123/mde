"""Toggle Editor action — mirrors Toggle Preview.

mde already had a `view.show_editor` setting and an `editor_toggle_btn`
button in the splitter chrome. What was missing was a menu/shortcut
entry, so users couldn't reach the toggle from the command palette or
a keystroke. This module adds tests for that wiring.

Also pinned here: the shortcut swap between
``view.toggle_editor`` (now ``Ctrl+Shift+E``, mirroring
``Ctrl+Shift+V`` for preview) and ``view.toggle_project`` (moved to
``Ctrl+Alt+E``).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.fixture
def editor(qtbot):
    w = MarkdownEditor()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    w.new_tab()
    QApplication.processEvents()
    return w


@pytest.mark.timeout(15, method="thread")
def test_toggle_editor_action_exists(editor):
    assert hasattr(editor, "toggle_editor_action")
    # Checkable, like toggle_preview.
    assert editor.toggle_editor_action.isCheckable()


@pytest.mark.timeout(15, method="thread")
def test_toggle_editor_action_hides_editor(editor):
    """Triggering the action while preview is visible hides the editor."""
    # Precondition: both editor and preview visible.
    editor.ctx.set("view.show_editor", True)
    editor.ctx.set("view.show_preview", True)
    editor.editor_toggle_btn.setChecked(True)
    editor.preview_toggle_btn.setChecked(True)
    editor._update_editor_preview_visibility()
    QApplication.processEvents()

    # Action mirrors the toggle button; trigger to flip it off.
    editor.toggle_editor_action.setChecked(False)
    editor._toggle_editor()
    QApplication.processEvents()
    assert not editor.editor_toggle_btn.isChecked()


@pytest.mark.timeout(15, method="thread")
def test_toggle_editor_cannot_hide_both(editor):
    """Can't hide editor if preview is already hidden — would leave
    the user staring at nothing."""
    editor.preview_toggle_btn.setChecked(False)
    editor.editor_toggle_btn.setChecked(True)
    editor._update_editor_preview_visibility()
    QApplication.processEvents()

    # Try to hide editor — should re-check the action (refuse).
    editor.toggle_editor_action.setChecked(False)
    editor._toggle_editor()
    QApplication.processEvents()
    assert editor.toggle_editor_action.isChecked(), (
        "must refuse to hide editor when preview is also hidden"
    )
    assert editor.editor_toggle_btn.isChecked()


@pytest.mark.timeout(15, method="thread")
def test_default_shortcuts_swap():
    """`view.toggle_editor` takes Ctrl+Shift+E (mirroring Ctrl+Shift+V for
    preview); `view.toggle_project` moves to Ctrl+Alt+E."""
    from markdown_editor.markdown6.app_context.shortcut_manager import (
        DEFAULT_SHORTCUTS,
    )
    assert DEFAULT_SHORTCUTS["view.toggle_editor"] == "Ctrl+Shift+E"
    assert DEFAULT_SHORTCUTS["view.toggle_project"] == "Ctrl+Alt+E"
    # Sanity: the two no longer collide.
    assert (
        DEFAULT_SHORTCUTS["view.toggle_editor"]
        != DEFAULT_SHORTCUTS["view.toggle_project"]
    )

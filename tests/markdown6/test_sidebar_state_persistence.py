"""The sidebar's collapsed state must persist across app launches.

Bug: `MarkdownEditor` saves `sidebar.collapsed` to the session state on
close (`_save_open_files`), and the value is correctly persisted to
`session.json`. But the restore code is INSIDE `restore_open_files`
*past* its early return:

    def restore_open_files(self):
        open_files = self.ctx.get("project.open_files", [])
        if not open_files:
            return                                            # ← bails

        # … 30 lines later …

        if self.ctx.get("sidebar.collapsed", False):          # ← never
            self.sidebar.setCollapsed(True, animated=False)   # ← reached

So the sidebar state isn't restored:
  - when the user closes with no open files,
  - when the user launches with CLI args (`mde foo.md` — different
    branch in `cmd_gui` that skips `restore_open_files`),
  - when the project doesn't match `last_path`.

Fix: sidebar state restore is its own concern, not tied to file
restore. Extract into a method called unconditionally during init.
"""

from __future__ import annotations

import pytest

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_sidebar_collapsed_state_restored_on_construction(qtbot):
    """If `sidebar.collapsed` is True in session state when a new
    MarkdownEditor is constructed, the sidebar must start collapsed —
    regardless of whether there are open files to restore."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    # Simulate a prior session that ended with the sidebar collapsed.
    editor.ctx.set("sidebar.collapsed", True)

    # New editor (fresh construction). It should pick up the persisted
    # state and start collapsed.
    next_editor = MarkdownEditor()
    qtbot.addWidget(next_editor)
    assert next_editor.sidebar.isCollapsed(), (
        "sidebar state was persisted but the new editor opened "
        "uncollapsed; the restore is gated behind `restore_open_files` "
        "and never runs in this path"
    )


@pytest.mark.timeout(15, method="thread")
def test_sidebar_expanded_state_default_when_no_session(qtbot):
    """Default — no persisted state — the sidebar starts expanded."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    # Sanity: ephemeral context starts with defaults.
    editor.ctx.set("sidebar.collapsed", False)

    next_editor = MarkdownEditor()
    qtbot.addWidget(next_editor)
    assert not next_editor.sidebar.isCollapsed()


@pytest.mark.timeout(15, method="thread")
def test_sidebar_active_panel_restored_on_construction(qtbot):
    """The selected panel index should also persist across launches."""
    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    # 1 is typically Outline; we set it through the same path the
    # close-time save uses.
    editor.ctx.set("sidebar.active_panel", 1)

    next_editor = MarkdownEditor()
    qtbot.addWidget(next_editor)
    assert next_editor.sidebar.activeIndex() == 1

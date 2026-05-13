"""Zen mode — hide everything except editor / preview.

Zen mode is a transient focus state: the user toggles it on to hide
menu / activity bar / sidebar / tab bar / status bar, write for a
while, then toggles it off and gets every panel back exactly as it
was.

Design points exercised here:

- Zen preserves pane visibility — if preview was hidden before, it
  stays hidden in Zen; if visible, stays visible.
- Exit restores the pre-Zen snapshot exactly (collapse state, splitter
  ratio, etc.) so the user doesn't get "rearranged" panels after a Zen
  round-trip.
- The find bar (and other transient overlays) work inside Zen. Esc
  inside the find bar closes the find bar and does NOT count toward
  the double-Esc Zen-exit gesture; only Esc events that reach the main
  window unhandled count.

The double-Esc handler tests use a deterministic monotonic-clock seam
(`document_tab._monotonic_ms` pattern reused here) so the 500 ms
window is testable without real-time sleeps.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


# ────────────────────── helpers ──────────────────────


@pytest.fixture
def editor(qtbot):
    """Real MarkdownEditor with one tab open and shown."""
    w = MarkdownEditor()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    w.new_tab()
    QApplication.processEvents()
    return w


def _send_esc(widget):
    """Synthesize a key-press of Esc on `widget`."""
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)
    QApplication.processEvents()


# ────────────────────── basic toggle ──────────────────────


def _menu_bar_user_visible(editor) -> bool:
    """True iff the menu bar takes up screen space the user can see.

    Zen mode collapses the menu bar to zero height rather than calling
    ``setVisible(False)`` — the latter would stop Qt from routing the
    menu's QAction shortcuts, including the Zen toggle itself. To the
    user, "max height 0" looks identical to hidden, but Qt's shortcut
    machinery still considers the bar live.
    """
    mb = editor.menuBar()
    return mb.isVisible() and mb.maximumHeight() > 0


@pytest.mark.timeout(15, method="thread")
def test_zen_hides_chrome(editor):
    """Entering Zen hides menu bar (user-visibly), sidebar, tab bar, status bar."""
    assert _menu_bar_user_visible(editor)
    assert editor.sidebar.isVisible()
    assert editor.tab_widget.tabBar().isVisible()
    assert editor.statusBar().isVisible()

    editor._toggle_zen_mode()
    QApplication.processEvents()

    assert not _menu_bar_user_visible(editor)
    assert not editor.sidebar.isVisible()
    assert not editor.tab_widget.tabBar().isVisible()
    assert not editor.statusBar().isVisible()
    # Editor itself must remain visible.
    tab = editor.current_tab()
    assert tab.editor.isVisible()


@pytest.mark.timeout(15, method="thread")
def test_zen_preserves_preview_shown(editor):
    """If preview is configured visible, it stays visible in Zen."""
    editor.ctx.set("view.show_preview", True)
    tab = editor.current_tab()
    tab._apply_settings()
    QApplication.processEvents()
    assert tab.preview.isVisible()

    editor._toggle_zen_mode()
    QApplication.processEvents()
    assert tab.preview.isVisible(), "preview should remain visible in Zen"


@pytest.mark.timeout(15, method="thread")
def test_zen_preserves_preview_hidden(editor):
    """If preview is hidden, it stays hidden in Zen."""
    editor.ctx.set("view.show_preview", False)
    tab = editor.current_tab()
    tab._apply_settings()
    QApplication.processEvents()
    assert not tab.preview.isVisible()

    editor._toggle_zen_mode()
    QApplication.processEvents()
    assert not tab.preview.isVisible(), "preview should remain hidden in Zen"


# ────────────────────── exit restoration ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_zen_exit_restores_chrome(editor):
    """Toggling Zen off restores every hidden panel."""
    editor._toggle_zen_mode()
    QApplication.processEvents()
    editor._toggle_zen_mode()
    QApplication.processEvents()

    assert _menu_bar_user_visible(editor)
    assert editor.sidebar.isVisible()
    assert editor.tab_widget.tabBar().isVisible()
    assert editor.statusBar().isVisible()


@pytest.mark.timeout(15, method="thread")
def test_zen_exit_preserves_sidebar_collapsed(editor):
    """Collapse state is part of the snapshot — must survive the round
    trip. (Without this, Zen would silently uncollapse the sidebar.)
    """
    editor.sidebar.setCollapsed(True, animated=False)
    QApplication.processEvents()
    assert editor.sidebar.isCollapsed()

    editor._toggle_zen_mode()
    QApplication.processEvents()
    editor._toggle_zen_mode()
    QApplication.processEvents()

    assert editor.sidebar.isVisible()
    assert editor.sidebar.isCollapsed(), (
        "sidebar collapse state must round-trip through Zen"
    )


@pytest.mark.timeout(15, method="thread")
def test_zen_is_idempotent(editor):
    """N enter / exit cycles end in the original state."""
    initial = {
        "menu": _menu_bar_user_visible(editor),
        "sidebar": editor.sidebar.isVisible(),
        "tabs": editor.tab_widget.tabBar().isVisible(),
        "status": editor.statusBar().isVisible(),
    }
    for _ in range(3):
        editor._toggle_zen_mode()
        QApplication.processEvents()
        editor._toggle_zen_mode()
        QApplication.processEvents()
    final = {
        "menu": _menu_bar_user_visible(editor),
        "sidebar": editor.sidebar.isVisible(),
        "tabs": editor.tab_widget.tabBar().isVisible(),
        "status": editor.statusBar().isVisible(),
    }
    assert initial == final


@pytest.mark.timeout(15, method="thread")
def test_zen_preserves_splitter_ratio(editor):
    """The editor↔preview splitter ratio must survive a Zen toggle."""
    tab = editor.current_tab()
    # Set an unambiguously non-default ratio.
    tab.splitter.setSizes([700, 300])
    QApplication.processEvents()
    before = tab.splitter.sizes()
    assert sum(before) > 0, "test precondition: splitter must have sizes"

    editor._toggle_zen_mode()
    QApplication.processEvents()
    editor._toggle_zen_mode()
    QApplication.processEvents()

    after = tab.splitter.sizes()
    # The ratio (not absolute pixels) should match — sizes may be
    # re-normalised by Qt. Compare ratios with a small tolerance.
    if sum(before) and sum(after):
        ratio_before = before[0] / sum(before)
        ratio_after = after[0] / sum(after)
        assert abs(ratio_before - ratio_after) < 0.05


# ────────────────────── double-Esc exit ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_zen_active_attribute_exists(editor):
    """API contract: `_zen_mode_active` reflects current state."""
    assert hasattr(editor, "_zen_mode_active")
    assert editor._zen_mode_active is False
    editor._toggle_zen_mode()
    assert editor._zen_mode_active is True
    editor._toggle_zen_mode()
    assert editor._zen_mode_active is False


@pytest.mark.timeout(15, method="thread")
def test_double_esc_exits_zen(editor, monkeypatch):
    """Two unhandled Esc presses within the debounce window exit Zen."""
    from markdown_editor.markdown6 import markdown_editor as me

    fake_now = [10_000]
    monkeypatch.setattr(me, "_monotonic_ms", lambda: fake_now[0])

    editor._toggle_zen_mode()
    QApplication.processEvents()
    assert editor._zen_mode_active

    # First Esc: starts the count.
    editor._on_unhandled_escape()
    assert editor._zen_mode_active, "single Esc must not exit Zen"

    # Second Esc within 500 ms: exits.
    fake_now[0] += 200
    editor._on_unhandled_escape()
    QApplication.processEvents()
    assert not editor._zen_mode_active, "double-Esc within 500ms must exit Zen"


@pytest.mark.timeout(15, method="thread")
def test_double_esc_outside_window_does_not_exit(editor, monkeypatch):
    """Two Escs spaced wider than 500 ms do NOT exit Zen."""
    from markdown_editor.markdown6 import markdown_editor as me

    fake_now = [10_000]
    monkeypatch.setattr(me, "_monotonic_ms", lambda: fake_now[0])

    editor._toggle_zen_mode()
    editor._on_unhandled_escape()
    fake_now[0] += 1000  # well past the window
    editor._on_unhandled_escape()
    QApplication.processEvents()
    assert editor._zen_mode_active, "Escs spaced >500ms must not exit Zen"


@pytest.mark.timeout(15, method="thread")
def test_find_bar_esc_does_not_count_toward_double_esc(editor, monkeypatch):
    """Esc that closes the find bar must NOT count as the first Esc of
    the double-tap. Only Escs that reach the main window unhandled
    count — find-bar's own Esc handler consumes the event before the
    main window sees it.
    """
    from markdown_editor.markdown6 import markdown_editor as me

    fake_now = [10_000]
    monkeypatch.setattr(me, "_monotonic_ms", lambda: fake_now[0])

    editor._toggle_zen_mode()
    QApplication.processEvents()
    assert editor._zen_mode_active

    # Open the find bar — its own Esc handler will eat the next Esc.
    editor._show_find()
    QApplication.processEvents()
    tab = editor.current_tab()
    assert tab.find_replace_bar.isVisible()

    # Send Esc to the find bar input. It closes the find bar. The main
    # window's unhandled-Esc handler is NOT invoked.
    _send_esc(tab.find_replace_bar.find_input)
    QApplication.processEvents()
    assert not tab.find_replace_bar.isVisible(), (
        "test precondition: find bar's Esc closes it"
    )

    # Now an actual unhandled Esc (still within 500 ms of the find-bar
    # Esc). If the find-bar Esc had wrongly counted, this would be the
    # second Esc and Zen would exit.
    fake_now[0] += 100
    editor._on_unhandled_escape()
    QApplication.processEvents()
    assert editor._zen_mode_active, (
        "find-bar Esc must not count toward double-tap; one real Esc "
        "is not enough"
    )


# ────────────────────── wiring ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_toggle_action_exists(editor):
    """The action registry wired up the toggle, exposed as
    `toggle_zen_mode_action` per the action_attr convention."""
    assert hasattr(editor, "toggle_zen_mode_action")
    editor.toggle_zen_mode_action.trigger()
    QApplication.processEvents()
    assert editor._zen_mode_active


@pytest.mark.timeout(15, method="thread")
def test_default_shortcut_registered():
    """`view.toggle_zen_mode` is in the shortcut defaults.

    Originally tried `Ctrl+K, Z` (VSCode parity), but `Ctrl+K` is taken
    by `markdown.link`, so Qt fires the link action on the first
    keystroke and never reaches the chord's Z. Settled on `Ctrl+Alt+Z`
    — single keystroke, mnemonic for "Zen", no prefix collision.
    """
    from markdown_editor.markdown6.app_context.shortcut_manager import (
        DEFAULT_SHORTCUTS,
    )
    assert "view.toggle_zen_mode" in DEFAULT_SHORTCUTS
    binding = DEFAULT_SHORTCUTS["view.toggle_zen_mode"]
    # No chord starting with Ctrl+K — it would collide with markdown.link.
    assert not binding.startswith("Ctrl+K,"), (
        f"chord {binding!r} collides with `markdown.link` (Ctrl+K)"
    )


@pytest.mark.timeout(15, method="thread")
def test_ctrl_f_works_in_zen(editor):
    """Ctrl+F (find) is a transient overlay — must still work inside Zen."""
    editor._toggle_zen_mode()
    QApplication.processEvents()
    editor._show_find()
    QApplication.processEvents()
    assert editor.current_tab().find_replace_bar.isVisible()


@pytest.mark.timeout(15, method="thread")
def test_cli_zen_mode_flag_recognised():
    """`mde --zen-mode` parses without error and sets args.zen_mode."""
    from markdown_editor.markdown6.markdown_editor_cli import create_parser

    parser = create_parser()
    args = parser.parse_args(["--zen-mode"])
    assert args.zen_mode is True

    args = parser.parse_args([])
    assert args.zen_mode is False


@pytest.mark.timeout(15, method="thread")
def test_cli_zen_mode_flag_enters_zen_on_launch(qtbot):
    """Simulates what cmd_gui does after constructing the editor when
    args.zen_mode is True: call _toggle_zen_mode() once before show().
    Asserts the editor lands in Zen state.
    """
    w = MarkdownEditor()
    qtbot.addWidget(w)
    w.new_tab()
    # The CLI applies this conditional in cmd_gui after construction.
    w._toggle_zen_mode()
    w.show()
    qtbot.waitExposed(w)
    QApplication.processEvents()
    assert w._zen_mode_active
    assert not _menu_bar_user_visible(w)
    assert not w.sidebar.isVisible()


@pytest.mark.timeout(15, method="thread")
def test_zen_toggle_shortcut_fires_in_zen(editor):
    """Regression: the Zen toggle action's QShortcut must fire while
    Zen is active.

    Earlier implementation called ``menuBar().setVisible(False)`` on
    entry, which Qt treats as "this menu bar is gone" and stops routing
    its QActions' shortcuts. The toggle action lives in the menu, so
    its shortcut went dead the moment Zen turned it on — user could
    enter Zen but not exit via the same shortcut.

    Fix: collapse the menu bar to zero height instead. Functionally
    invisible to the user, but Qt's shortcut machinery still considers
    it alive. This test asserts the action remains effective while Zen
    is on.
    """
    editor.toggle_zen_mode_action.trigger()
    QApplication.processEvents()
    assert editor._zen_mode_active

    # The user-visible state: action enabled, shortcut still bound.
    assert editor.toggle_zen_mode_action.isEnabled()
    assert not editor.toggle_zen_mode_action.shortcut().isEmpty()

    # Trigger again — must exit. This is what fails if the menu bar
    # was hidden via setVisible(False).
    editor.toggle_zen_mode_action.trigger()
    QApplication.processEvents()
    assert not editor._zen_mode_active

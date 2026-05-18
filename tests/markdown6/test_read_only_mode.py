"""Read-only mode — first-class app-level toggle.

The old `--read-only` CLI hack called `setReadOnly(True)` on the
single active tab's editor widget. New design is application-wide:
- All tabs typing-blocked.
- New tabs inherit.
- Save / save-as / reload / paste-to-disk all blocked via a function-
  level gate.
- Menu actions disabled.
- Mutations *can* still happen inside a `with editor.allow_mutation(op)`
  block via a one-shot MutationPermit. The permit is op-specific and
  in-band (must be passed to the call), so signal handlers firing
  during the same window cannot use it. This is the granularity
  property the previous broad context-manager design lacked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from markdown_editor.markdown6.markdown_editor import (
    MarkdownEditor,
    MutationPermit,
)


@pytest.fixture
def editor(qtbot):
    w = MarkdownEditor()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    QApplication.processEvents()
    return w


# ────────────────────── state + propagation ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_default_state_is_writable(editor):
    assert editor._read_only_mode is False


@pytest.mark.timeout(15, method="thread")
def test_set_read_only_propagates_to_all_open_tabs(editor):
    """Every editor widget becomes setReadOnly(True) when RO flips on."""
    editor.new_tab()
    editor.new_tab()
    assert editor.tab_widget.count() >= 2

    editor.set_read_only_mode(True)
    QApplication.processEvents()
    for i in range(editor.tab_widget.count()):
        assert editor.tab_widget.widget(i).editor.isReadOnly()


@pytest.mark.timeout(15, method="thread")
def test_new_tab_inherits_read_only_state(editor):
    """A tab created while RO is on starts read-only too."""
    editor.set_read_only_mode(True)
    tab = editor.new_tab()
    QApplication.processEvents()
    assert tab.editor.isReadOnly()


@pytest.mark.timeout(15, method="thread")
def test_toggle_off_restores_writable(editor):
    editor.set_read_only_mode(True)
    editor.set_read_only_mode(False)
    QApplication.processEvents()
    for i in range(editor.tab_widget.count()):
        assert not editor.tab_widget.widget(i).editor.isReadOnly()


@pytest.mark.timeout(15, method="thread")
def test_signal_fires_on_flip(editor):
    """The read_only_changed signal carries the new state."""
    seen = []
    editor.read_only_changed.connect(lambda v: seen.append(v))
    editor.set_read_only_mode(True)
    editor.set_read_only_mode(False)
    editor.set_read_only_mode(False)   # no-op; signal must NOT fire again
    assert seen == [True, False]


# ────────────────────── action gating (UX layer) ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_write_actions_disabled_when_read_only(editor):
    write_actions = ("save_action", "save_as_action")
    for name in write_actions:
        action = getattr(editor, name, None)
        assert action is not None, f"action {name} should exist"
        assert action.isEnabled()
    editor.set_read_only_mode(True)
    QApplication.processEvents()
    for name in write_actions:
        action = getattr(editor, name)
        assert not action.isEnabled(), f"{name} must be disabled in RO mode"


@pytest.mark.timeout(15, method="thread")
def test_write_actions_reenable_when_toggled_off(editor):
    editor.set_read_only_mode(True)
    editor.set_read_only_mode(False)
    QApplication.processEvents()
    assert editor.save_action.isEnabled()
    assert editor.save_as_action.isEnabled()


# ────────────────────── function gate (correctness layer) ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_save_file_without_permit_blocked_in_read_only(editor, tmp_path):
    """save_file() with no permit returns False while RO and does NOT
    write to disk."""
    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.setPlainText("modified")
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    result = editor.save_file()
    assert result is False
    assert f.read_text() == "original", "save must NOT have written"


@pytest.mark.timeout(15, method="thread")
def test_save_file_with_permit_succeeds_in_read_only(editor, tmp_path):
    """save_file(permit=permit) with a valid permit succeeds even while RO."""
    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.setPlainText("modified")
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    with editor.allow_mutation('save_file') as permit:
        result = editor.save_file(permit=permit)
    assert result is True
    assert f.read_text() == "modified"


# ────────────────────── permit semantics ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_permit_with_mismatched_op_is_rejected(editor, tmp_path):
    """Permit issued for 'paste_image' cannot authorize 'save_file'."""
    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.setPlainText("modified")
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    with editor.allow_mutation('paste_image') as permit:
        result = editor.save_file(permit=permit)
    assert result is False
    assert f.read_text() == "original"


@pytest.mark.timeout(15, method="thread")
def test_permit_is_one_shot(editor, tmp_path):
    """A permit used once cannot be used again."""
    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    editor.set_read_only_mode(True)

    permit = MutationPermit('save_file')
    assert permit.claim('save_file') is True
    # Second claim must fail — one-shot.
    assert permit.claim('save_file') is False


@pytest.mark.timeout(15, method="thread")
def test_permit_can_be_used_outside_with_block(editor):
    """Permit semantics are one-shot, NOT scoped to the with-block.
    A leaked permit is still valid for its single use. The `with`
    block is for ergonomics and the unused-permit warning, not for
    enforcement."""
    editor.set_read_only_mode(True)
    leaked = None
    with editor.allow_mutation('save_file') as permit:
        leaked = permit
    # Outside the block, the permit can still be claimed once.
    assert leaked.claim('save_file') is True


# ────────────────────── granularity (the critical test) ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_user_action_during_mutation_block_is_blocked(editor, tmp_path):
    """The headline property: while in `allow_mutation('paste_image')`,
    a user-triggered save (e.g. Ctrl+S during dialog.exec, or any
    signal handler that runs while the event loop spins) must NOT
    be authorized. Only the explicit call with the permit passes.
    """
    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.setPlainText("user typed here")
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    with editor.allow_mutation('paste_image'):
        # Simulate a user keystroke that triggers save during the block.
        # The action is disabled (Layer 3) AND the function would
        # bail anyway (Layer 2) because no permit was passed.
        result = editor.save_file()  # no permit arg
        assert result is False, "save_file without permit must NOT succeed"
        assert f.read_text() == "original"


# ────────────────────── persistence ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_state_is_not_persisted(editor):
    """RO is transient. It must never be read from or written to
    settings.json. Test by flipping it on and confirming the context
    doesn't have a `view.read_only` key (or whatever the obvious name
    would be) set."""
    editor.set_read_only_mode(True)
    # Common naming would be `view.read_only`. Either the key is
    # absent, or it's there but explicitly NOT True (i.e., not used
    # for persistence).
    assert editor.ctx.get("view.read_only", "MISSING") in ("MISSING", False)


# ────────────────────── CLI ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_cli_read_only_flag_calls_set_read_only_mode(qtbot, monkeypatch):
    """When --read-only is passed, cmd_gui calls set_read_only_mode(True).
    Simulates what the CLI does: construct editor, call setter."""
    w = MarkdownEditor()
    qtbot.addWidget(w)
    w.set_read_only_mode(True)
    QApplication.processEvents()
    assert w._read_only_mode is True


# ────────────────────── closeEvent escape ──────────────────────


@pytest.mark.timeout(15, method="thread")
def test_close_save_path_can_save_even_in_read_only(editor, tmp_path, monkeypatch):
    """closeEvent's save-on-exit path uses allow_mutation so save
    succeeds even when RO is on. We invoke the same `_check_tab_unsaved_changes`
    + save sequence the close handler uses, with the QMessageBox
    stubbed to return 'Save'."""
    from PySide6.QtWidgets import QMessageBox

    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.setPlainText("modified during writable")
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    # Stub the prompt to choose "Save".
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **kw: QMessageBox.StandardButton.Save,
    )
    ok = editor._check_tab_unsaved_changes(tab)
    assert ok, "save path during close must succeed"
    assert f.read_text() == "modified during writable", (
        "the close-handler save escape must write through"
    )


@pytest.mark.timeout(15, method="thread")
def test_close_cancel_keeps_read_only(editor, tmp_path, monkeypatch):
    """If user picks Cancel at the close prompt, RO stays on (close
    aborted, app continues in the locked state)."""
    from PySide6.QtWidgets import QMessageBox

    f = tmp_path / "x.md"
    f.write_text("original")
    editor.open_file(f)
    tab = editor.current_tab()
    tab.editor.document().setModified(True)

    editor.set_read_only_mode(True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **kw: QMessageBox.StandardButton.Cancel,
    )
    ok = editor._check_tab_unsaved_changes(tab)
    assert ok is False
    assert editor._read_only_mode is True, "cancel must not flip RO off"

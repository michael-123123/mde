"""Ctrl+S / Ctrl+Shift+S / Ctrl+Alt+S must not crash.

Reported by a user: pressing Ctrl+S crashed mde with::

    AttributeError: 'bool' object has no attribute 'claim'

at the ``_authorize`` call inside ``save_file``.

Root cause: ``QAction.triggered`` is a Qt signal that emits a single
``bool`` argument (the action's ``checked`` state, which is ``False``
for non-checkable actions). When the actions registry connects the
signal directly to ``editor.save_file`` (the no-args branch of
``_make_callback``), Qt passes that ``bool`` to the slot as the first
positional argument.

``save_file`` and friends gained a ``permit: MutationPermit | None =
None`` parameter for the read-only mode work. With the bool leaking
in, ``permit = False``, and ``_authorize`` then calls
``False.claim('save_file')`` - crash.

Same pattern affects Ctrl+Shift+S (``save_file_as``) and Ctrl+Alt+S
(``save_all``). Any future method registered through the actions
registry with a non-bool first positional argument will hit the
same trap.

The fix is in ``actions._make_callback``: always swallow extras from
the ``triggered`` signal so the registered method is always called
with the args declared in its ``ActionDef``.
"""

from __future__ import annotations

import pytest

from markdown_editor.markdown6.markdown_editor import MarkdownEditor


@pytest.mark.timeout(15, method="thread")
def test_save_action_trigger_does_not_crash(qtbot, tmp_path):
    """Triggering ``save_action`` (as Ctrl+S does) must save the file
    without crashing on ``'bool' object has no attribute 'claim'``."""
    f = tmp_path / "x.md"
    f.write_text("original")

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.open_file(str(f))
    tab = editor.current_tab()
    tab.editor.setPlainText("modified")
    tab.editor.document().setModified(True)

    editor.save_action.trigger()

    assert f.read_text() == "modified"


@pytest.mark.timeout(15, method="thread")
def test_save_all_action_trigger_does_not_crash(qtbot, tmp_path):
    """Same bug surfaces for Ctrl+Alt+S (save_all). save_all's
    ``permit`` kwarg defaults to ``None``; the QAction.triggered bool
    must not poison it."""
    f = tmp_path / "x.md"
    f.write_text("original")

    editor = MarkdownEditor()
    qtbot.addWidget(editor)
    editor.open_file(str(f))
    tab = editor.current_tab()
    tab.editor.setPlainText("modified")
    tab.editor.document().setModified(True)

    editor.save_all_action.trigger()

    assert f.read_text() == "modified"


@pytest.mark.timeout(15, method="thread")
def test_actions_callback_swallows_qaction_triggered_bool():
    """Direct unit test on ``_make_callback``: the callback returned
    for an ActionDef with no args must accept (and discard) the bool
    that ``QAction.triggered`` would emit. Tomorrow's developer adding
    a method with a non-bool first positional should not have to know
    Qt's signal signature."""
    from markdown_editor.markdown6.actions import _make_callback

    calls: list[tuple] = []

    class FakeEditor:
        def takes_no_args(self):
            calls.append(("noargs",))

    cb = _make_callback(FakeEditor(), "takes_no_args", ())
    # Qt emits `triggered(False)` for non-checkable actions.
    cb(False)
    assert calls == [("noargs",)]

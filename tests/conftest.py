"""Auto-dismiss blocking ``QMessageBox`` modals in tests.

Production code uses ``QMessageBox.question`` / ``.warning`` / ``.critical`` /
``.information`` as modal dialogs that run a nested Qt event loop and block
until the user clicks a button. In a test environment there is no user,
so any code path that reaches one of these calls hangs indefinitely
(``pytest-timeout --signal`` cannot interrupt a Qt nested event loop;
``--thread`` can at least print a traceback but the process still has to
be killed externally).

This autouse fixture replaces the four static methods on ``QMessageBox``
with non-blocking stubs that return a sensible default button without
ever creating a real dialog. That lets tests drive through code paths
that would otherwise prompt — notably ``MarkdownEditor.closeEvent``'s
"unsaved changes" prompt — without hanging.

Defaults chosen to keep tests moving forward rather than cancelling:

- ``question`` → ``Discard`` (proceed with close / delete / etc.).
- ``warning`` / ``critical`` / ``information`` → ``Ok`` (acknowledge).

If a future test needs to assert that a prompt was shown, it can
monkeypatch the specific method back to a custom stub in the test body
— the autouse fixture runs before any test-local monkeypatching.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def _auto_dismiss_qmessagebox(monkeypatch):
    """Replace blocking ``QMessageBox.*`` statics with non-blocking stubs."""
    defaults = {
        "question": QMessageBox.StandardButton.Discard,
        "warning": QMessageBox.StandardButton.Ok,
        "critical": QMessageBox.StandardButton.Ok,
        "information": QMessageBox.StandardButton.Ok,
    }

    def _make_stub(button):
        def stub(*_args, **_kwargs):
            return button
        return stub

    for method_name, return_button in defaults.items():
        monkeypatch.setattr(QMessageBox, method_name, _make_stub(return_button))

"""Pytest configuration for markdown6 tests.

This module ensures all tests use ephemeral app context to avoid
reading from or writing to the user's actual settings.
"""

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_xvfb_sockets():
    """Remove orphaned X11 sockets left by crashed Xvfb instances.

    When test runs are killed hard (SIGKILL, hang + Ctrl+C), Xvfb's
    atexit handler never fires and its Unix socket stays in /tmp/.X11-unix/.
    These accumulate and eventually exhaust all display numbers, preventing
    Xvfb (and pytest-xvfb) from starting.
    """
    x11_dir = Path("/tmp/.X11-unix")
    if not x11_dir.exists():
        return
    my_uid = os.getuid()
    display = os.environ.get("DISPLAY", "").lstrip(":")
    for sock in x11_dir.iterdir():
        # Never touch the real display or sockets owned by other users
        if sock.name == f"X{display}":
            continue
        try:
            if sock.stat().st_uid == my_uid:
                sock.unlink()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def ephemeral_settings():
    """Ensure all tests use ephemeral app context.

    This fixture runs automatically before each test to:
    1. Reset the global AppContext instance
    2. Initialize with ephemeral=True so no user settings are loaded or saved

    This prevents tests from:
    - Reading the user's actual settings
    - Writing to the user's settings files
    - Having test results depend on user configuration
    """
    import markdown_editor.markdown6.app_context as ctx_module

    # Reset global context before test
    ctx_module._app_context = None

    # Initialize ephemeral context
    ctx_module.init_app_context(ephemeral=True)

    yield

    # Reset after test to clean up
    ctx_module._app_context = None


def pytest_sessionfinish(session, exitstatus):
    """Flush pending widget deletions before Qt tears down profiles.

    ``deleteLater()`` posts a ``DeferredDelete`` event; plain
    ``processEvents()`` at shutdown doesn't reliably deliver those, so any
    subclassed ``QWebEnginePage`` (``DocumentTab.LinkInterceptPage``,
    ``GraphPreviewPage``) survives until the default
    ``QWebEngineProfile`` is destroyed, producing
    "Release of profile requested but WebEnginePage still not deleted."
    on stderr. Explicitly flushing ``DeferredDelete`` lets those pages
    tear down before the profile.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

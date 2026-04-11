"""Pytest configuration for markdown6 tests.

This module ensures all tests use ephemeral app context to avoid
reading from or writing to the user's actual settings.
"""

import pytest


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
    """Flush pending widget deletions before Qt tears down profiles."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.processEvents()

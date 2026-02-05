"""Pytest configuration for markdown6 tests.

This module ensures all tests use ephemeral settings to avoid
reading from or writing to the user's actual settings.
"""

import pytest


@pytest.fixture(autouse=True)
def ephemeral_settings():
    """Ensure all tests use ephemeral settings.

    This fixture runs automatically before each test to:
    1. Reset the global settings instance
    2. Initialize with ephemeral=True so no user settings are loaded or saved

    This prevents tests from:
    - Reading the user's actual settings
    - Writing to the user's settings files
    - Having test results depend on user configuration
    """
    import fun.markdown6.settings as settings_module

    # Reset global settings before test
    settings_module._settings = None

    # Initialize ephemeral settings
    settings_module.init_settings(ephemeral=True)

    yield

    # Reset after test to clean up
    settings_module._settings = None

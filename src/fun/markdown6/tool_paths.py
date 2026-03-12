"""Centralized external tool path resolution.

Uses configured paths from settings, falling back to system PATH lookup.
"""

import shutil
from pathlib import Path

from fun.markdown6.settings import get_settings


def _resolve(settings_key: str, default_cmd: str) -> str | None:
    """Resolve a tool path from settings or system PATH.

    Returns the full path string if found, None otherwise.
    """
    settings = get_settings()
    configured = settings.get(settings_key, "")

    if configured:
        # User configured a specific path
        path = Path(configured)
        if path.is_file():
            return str(path)
        # Maybe they typed just a command name — try which
        found = shutil.which(configured)
        return found

    # Fall back to system PATH
    return shutil.which(default_cmd)


def get_pandoc_path() -> str | None:
    """Get the pandoc executable path, or None if not found."""
    return _resolve("tools.pandoc_path", "pandoc")


def get_dot_path() -> str | None:
    """Get the graphviz dot executable path, or None if not found."""
    return _resolve("tools.dot_path", "dot")


def get_mmdc_path() -> str | None:
    """Get the mermaid CLI (mmdc) executable path, or None if not found."""
    return _resolve("tools.mmdc_path", "mmdc")


def has_pandoc() -> bool:
    return get_pandoc_path() is not None


def has_dot() -> bool:
    return get_dot_path() is not None


def has_mmdc() -> bool:
    return get_mmdc_path() is not None

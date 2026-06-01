"""Helpers shared across the cli/ subpackage subcommand handlers.

Stays Qt-free at module load: the app_context import that pulls Qt
in transitively is deferred to call time inside ``get_project_files``
so that subcommands which don't need it (``stats``, ``validate``,
plain CLI parsing) don't pay the Qt-load cost.
"""

from __future__ import annotations

import sys
from pathlib import Path


def read_stdin() -> str:
    """Read content from stdin if available."""
    try:
        if not sys.stdin.isatty():
            return sys.stdin.read()
    except OSError:
        # Handle pytest capture mode
        pass
    return ""


def get_project_files(project_path: Path) -> list[Path]:
    """Get all markdown files in a project."""
    from markdown_editor.markdown6.app_context import (
        get_project_markdown_files,
    )
    return get_project_markdown_files(project_path)

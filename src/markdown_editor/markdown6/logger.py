"""Logging configuration for the Markdown editor.

Call ``setup()`` once at application startup (before any getLogger calls
matter) to install the pretty console handler.  Every other module just does::

    import logging
    logger = logging.getLogger("mde.modulename")

and gets coloured, aligned output for free.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# Root logger name — all modules use "mde.<module>" children of this.
ROOT = "mde"

_RESET = "\033[0m"
_DIM = "\033[2m"
_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",      # cyan
    logging.INFO: "\033[32m",       # green
    logging.WARNING: "\033[33m",    # yellow
    logging.ERROR: "\033[31m",      # red
    logging.CRITICAL: "\033[1;31m", # bold red
}

# Standard format with fixed-width columns.
# The only reason for a custom Formatter subclass is per-level ANSI colouring —
# everything else (timestamps, alignment, exc_info) uses the stdlib machinery.
_FORMAT = "%(asctime)s %(levelname)-8s %(name)-20s %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class _ColorFormatter(logging.Formatter):
    """Wraps each log line in ANSI colour based on level. That's it."""

    def __init__(self):
        super().__init__(fmt=_FORMAT, datefmt=_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, "")
        return f"{color}{super().format(record)}{_RESET}"


def getLogger(module_name: str) -> logging.Logger:
    """Get a logger under the ``mde`` namespace.

    ``getLogger(__name__)`` in ``markdown_editor.markdown6.app_context``
    returns the logger ``mde.markdown_editor.markdown6.app_context``.
    """
    return logging.getLogger(f"{ROOT}.{module_name}")


def _log_file_path() -> Path | None:
    """Return the per-user log file path, or None if we can't determine one.

    Windows GUI launches have no parent stderr; without a file handler the
    log vanishes. Use %LOCALAPPDATA% on Windows, $XDG_STATE_HOME (or
    ~/.local/state) on Linux, and ~/Library/Logs on macOS.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            return None
        return Path(base) / "markdown-editor" / "logs" / "mde.log"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "markdown-editor" / "mde.log"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "markdown-editor" / "logs" / "mde.log"


def setup(level: int = logging.DEBUG) -> None:
    """Install the pretty handler on the ``mde`` root logger.

    Safe to call more than once (idempotent).

    Args:
        level: Minimum level for console output.  The root logger is set to
            DEBUG so per-module ``logger.setLevel()`` overrides still work;
            the *handler* applies the visible floor.
    """
    root = logging.getLogger(ROOT)

    # Avoid duplicate handlers on repeated calls.
    if any(isinstance(h, logging.StreamHandler) and
           isinstance(h.formatter, _ColorFormatter) for h in root.handlers):
        return

    root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(_ColorFormatter())
    root.addHandler(handler)

    log_path = _log_file_path()
    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
            root.addHandler(file_handler)
        except OSError:
            # Read-only home, locked-down sandbox, etc. Console handler still works.
            pass

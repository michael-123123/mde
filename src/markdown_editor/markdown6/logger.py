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


_LEVEL_NAMES = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


_external_capture_started = False


def capture_external_stderr() -> None:
    """Redirect OS-level ``fd 2`` writes through Python's logger.

    Native code embedded in mde (Chromium inside QtWebEngine, NSS,
    parts of Qt itself) writes directly to file descriptor 2, bypassing
    Python's ``sys.stderr``. The most common offender is::

        [ERROR:nss_util.cc(357)] After loading Root Certs, loaded==false
        : NSS error code: -8018

    That line is harmless (mde only loads local HTML in the preview,
    so root certs are never consulted) but it leaks to the terminal
    regardless of our ``--log-level`` setting. This function rewires
    fd 2 through a pipe, reads each line in a daemon thread, and
    re-emits via the ``mde.external`` logger at DEBUG. Default INFO
    level hides it; ``--log-level=debug`` surfaces it.

    Must be called BEFORE ``setup()`` so the StreamHandler attached
    to the ``mde`` root inherits the saved (still-real) stderr - if
    we redirected after, our own log lines would loop back into the
    capture pipe.

    Idempotent: re-calls are no-ops.

    Caveats:
    - Windows: ``os.dup2`` works on Windows but the GUI launcher has
      no console; this is a no-op there since fd 2 is already a sink.
    - The daemon thread blocks on ``read()``; on shutdown the GIL is
      released and the thread is torn down with the interpreter.
    """
    global _external_capture_started
    if _external_capture_started:
        return
    if sys.platform == "win32":
        # GUI launches on Windows have no console; native stderr already
        # vanishes. Skip the rewire rather than introduce a flaky pipe.
        _external_capture_started = True
        return

    try:
        saved_stderr_fd = os.dup(2)
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, 2)
        os.close(write_fd)
    except OSError:
        # If the OS refuses (sandbox, etc.), keep the noisy stderr —
        # better than crashing the launcher. Emits via Python's
        # lastResort handler since setup() hasn't run yet.
        logging.getLogger(ROOT).exception(
            "Could not redirect native stderr to logger",
        )
        return

    # Point Python's sys.stderr at the saved fd so the logger's
    # StreamHandler still reaches the terminal. If we left sys.stderr
    # pointing at the redirected fd 2, every log line would feed back
    # into the capture pipe and recurse.
    import io
    sys.stderr = io.TextIOWrapper(
        os.fdopen(saved_stderr_fd, "wb", buffering=0),
        encoding="utf-8",
        write_through=True,
    )

    external_logger = logging.getLogger(f"{ROOT}.external")

    def _reader():
        with os.fdopen(read_fd, "r", buffering=1, errors="replace") as pipe:
            for line in pipe:
                line = line.rstrip()
                if line:
                    external_logger.debug("%s", line)

    import threading
    t = threading.Thread(target=_reader, daemon=True, name="mde-external-stderr")
    t.start()
    _external_capture_started = True


def resolve_level(
    cli_value: str | None = None,
    *,
    settings_value: str | None = None,
    default: int = logging.INFO,
) -> int:
    """Pick a log level from the precedence chain:

        CLI flag → ``MDE_LOG_LEVEL`` env var → settings.log.level → default.

    Each layer accepts case-insensitive names (``debug`` / ``info`` /
    ``warning`` / ``error``, plus ``warn`` as alias for warning).
    Anything unrecognised at any layer falls through to the next -
    bad input never crashes the launch path.

    ``settings_value`` is the persisted ``log.level`` from
    ``SettingsManager``; pass ``None`` (or omit) when no persisted
    value applies (e.g. ephemeral / new-session launches).
    """
    for candidate in (
        cli_value,
        os.environ.get("MDE_LOG_LEVEL"),
        settings_value,
    ):
        if not candidate:
            continue
        lv = _LEVEL_NAMES.get(candidate.strip().lower())
        if lv is not None:
            return lv
    return default


def set_level(level: int) -> None:
    """Update the visible-log floor on every handler already installed
    by ``setup()``. Useful after settings are loaded: ``main()`` calls
    ``setup()`` early with the CLI / env / default chain, and once
    ``AppContext`` is up the caller re-applies the level with the
    persisted ``log.level`` factored in.

    Each handler's filter level rises or falls; the root logger stays
    at DEBUG so per-module overrides still work.
    """
    root = logging.getLogger(ROOT)
    for handler in root.handlers:
        handler.setLevel(level)


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
            # Read-only home, locked-down sandbox, etc. Console handler
            # still works; we just lose persistent log file rotation.
            root.exception("Could not attach log file handler at %s", log_path)

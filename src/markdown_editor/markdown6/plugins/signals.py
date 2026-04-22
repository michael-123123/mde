"""Plugin lifecycle-event dispatch.

Plugins subscribe to document lifecycle events via the decorators
:func:`on_save`, :func:`on_content_changed`, :func:`on_file_opened`,
and :func:`on_file_closed` exported from
:mod:`markdown_editor.markdown6.plugins.api`. Each decorator stores a
:class:`SignalHandler` record in the module-level
:class:`PluginRegistry`, stamped with the owning plugin's name so the
dispatcher can skip handlers belonging to disabled plugins.

The editor calls :func:`dispatch` at well-defined points in its own
code (after a successful save, on tab close, on file open, etc.) with
a :class:`DocumentHandle` for the affected document and the current
``plugins.disabled`` set. Dispatch:

* Skips handlers whose plugin is in ``disabled``.
* Calls each remaining handler with the handle as its single argument.
* Catches and logs exceptions from individual handlers - one bad
  plugin doesn't abort the dispatch loop or affect the editor.

Plugin handlers receive a Qt-free ``DocumentHandle`` - never a raw
``DocumentTab`` or ``QObject``. This keeps the documented API surface
free of Qt types per the core design invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle

logger = getLogger(__name__)


class SignalKind(Enum):
    """Lifecycle events plugins can subscribe to."""
    SAVE = "save"                       # after a file is written to disk
    CONTENT_CHANGED = "content_changed" # editor's textChanged event
    FILE_OPENED = "file_opened"         # a file is loaded into a tab
    FILE_CLOSED = "file_closed"         # a tab is closing


@dataclass
class SignalHandler:
    """One plugin's subscription to a lifecycle event."""
    kind: SignalKind
    callback: Callable[[DocumentHandle], None]
    plugin_name: str = ""


def dispatch(
    kind: SignalKind,
    doc: DocumentHandle,
    *,
    disabled: set[str],
) -> None:
    """Fan out a lifecycle event to every registered handler of ``kind``.

    Skips handlers whose ``plugin_name`` is in ``disabled``. Catches
    and logs any exception raised by an individual handler so the
    dispatch loop continues - one buggy plugin does not break the
    editor or starve other plugins.
    """
    # Imported here to avoid a circular import at module load time
    # (api → signals → registry → api).
    from markdown_editor.markdown6.plugins import api as _api

    handlers = _api._REGISTRY.signal_handlers(kind)
    for h in handlers:
        if h.plugin_name and h.plugin_name in disabled:
            continue
        try:
            with _api._current_plugin(h.plugin_name):
                h.callback(doc)
        except BaseException as exc:    # noqa: BLE001 - plugin code
            handler_name = getattr(h.callback, "__name__", repr(h.callback))
            logger.warning(
                "Plugin signal handler %r (kind=%s) raised: %s",
                handler_name, kind.value, exc, exc_info=True,
            )
            from markdown_editor.markdown6.notifications import (
                _post_plugin_error,
            )
            _post_plugin_error(
                h.plugin_name,
                f"Plugin {kind.value} handler failed: {handler_name}",
                f"{type(exc).__name__}: {exc}",
            )

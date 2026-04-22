"""Stable, plugin-facing API surface.

This module is what a plugin imports. It exposes the decorators plugins
use to register themselves, the :func:`get_active_document` accessor
that hands the plugin a :class:`DocumentHandle`, and a few escape
hatches for advanced use. Everything here is intended to be stable
across MDE minor versions once we hit 1.0.

The implementation keeps two pieces of module-level state:

* ``_REGISTRY`` — a :class:`PluginRegistry` that accumulates
  registrations as plugin modules are imported by the loader.
* ``_ACTIVE_DOCUMENT_PROVIDER`` — a callable set by the editor at
  startup, which returns the currently-active
  :class:`DocumentHandle`. Plugins reach the active document through
  this indirection so we never hand them a ``DocumentTab`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginRegistry,
    PluginTextTransform,
)

logger = getLogger(__name__)


# --- Module-level state ------------------------------------------------------

_REGISTRY: PluginRegistry = PluginRegistry()
_ACTIVE_DOCUMENT_PROVIDER: Callable[[], DocumentHandle | None] = lambda: None

# Name of the plugin currently being imported by the loader. Read by
# the registration decorators so each registration can be stamped with
# its owning plugin's name. Empty when no import is in progress (e.g.
# during tests that register directly).
_CURRENT_PLUGIN_NAME: str = ""


def _set_active_document_provider(
    provider: Callable[[], DocumentHandle | None],
) -> None:
    """Editor-internal: wire up the accessor used by :func:`get_active_document`.

    Called once by ``MarkdownEditor.__init__`` after the UI is built.
    """
    global _ACTIVE_DOCUMENT_PROVIDER
    _ACTIVE_DOCUMENT_PROVIDER = provider


def _set_current_plugin_name(name: str) -> None:
    """Loader-internal: set the name of the plugin whose module is about
    to be imported. Cleared back to "" once the import returns.
    """
    global _CURRENT_PLUGIN_NAME
    _CURRENT_PLUGIN_NAME = name


def get_registry() -> PluginRegistry:
    """Return the module-level registry (used by the editor to drain
    registrations after loading plugins)."""
    return _REGISTRY


# --- Registration decorators -------------------------------------------------


def register_action(
    *,
    id: str,
    label: str,
    menu: str = "",
    shortcut: str = "",
    palette_category: str = "",
    place: str = "",
) -> Callable[[Callable], Callable]:
    """Decorator: register a plugin command.

    Args:
        id: Globally unique identifier (e.g. ``"logseq.strip"``).
        label: Display label for menu items and palette entries.
        menu: Optional menu path. Plain paths are namespaced under the
            top-level "Plugins" menu (e.g. ``"Transform"`` →
            ``Plugins/Transform``). A leading ``"/"`` is the escape
            hatch into the editor's real menus (e.g. ``"/Edit/Find"``)
            and **requires** a ``place=`` argument.
        shortcut: Optional ``QKeySequence`` string, e.g. ``"Ctrl+Alt+T"``.
        palette_category: Category label in the command palette.
        place: Required when ``menu`` starts with ``"/"``. One of:
            ``"after:<id>"``, ``"before:<id>"`` (anchored to an editor
            action id), ``"start"``, or ``"end"``. Ignored for plain
            (Plugins-namespaced) paths.

    The decorated function may take any signature that makes sense for
    the plugin — the framework calls it with no arguments. Use
    :func:`get_active_document` inside to reach the current document.
    """
    _validate_place(id, menu, place)

    def decorator(fn: Callable) -> Callable:
        _REGISTRY.register_action(
            PluginAction(
                id=id,
                label=label,
                menu=menu,
                shortcut=shortcut,
                palette_category=palette_category,
                callback=fn,
                plugin_name=_CURRENT_PLUGIN_NAME,
                place=place,
            )
        )
        return fn
    return decorator


def _validate_place(action_id: str, menu: str, place: str) -> None:
    """Reject `/`-prefixed menu paths that don't carry a ``place=``.

    Called at decoration time so the error surfaces during plugin
    import — the loader records LOAD_FAILURE and the user sees a
    clear reason in Settings → Plugins.
    """
    if menu.startswith("/") and not place:
        raise ValueError(
            f"register: id={action_id!r} menu={menu!r} starts with '/' "
            "(escape hatch into the editor's top-level menus). You must "
            "also pass place= to specify where in the target menu the "
            "action should appear. Examples: place='after:edit.find', "
            "place='before:edit.preferences', place='start', place='end'."
        )


def register_text_transform(
    *,
    id: str,
    label: str,
    menu: str = "",
    shortcut: str = "",
    palette_category: str = "",
    place: str = "",
) -> Callable[[Callable[[str], str]], Callable[[str], str]]:
    """Decorator: register a pure ``(str) -> str`` transform as an atomic action.

    The framework reads the current document text, calls the decorated
    function, and applies the result atomically inside
    :meth:`DocumentHandle.atomic_edit`. If the transform raises, the
    document is restored byte-identically to its pre-call state and the
    error is reported through the notifications drawer (future) — the
    exception does not propagate.

    Use this for simple, stateless text rewrites. For anything cursor-
    aware or multi-step, use :func:`register_action` + manual mutators.

    See :func:`register_action` for the ``menu`` and ``place``
    semantics — they are identical.
    """
    _validate_place(id, menu, place)

    def decorator(fn: Callable[[str], str]) -> Callable[[str], str]:
        _REGISTRY.register_text_transform(
            PluginTextTransform(
                id=id,
                label=label,
                menu=menu,
                shortcut=shortcut,
                palette_category=palette_category,
                transform=fn,
                plugin_name=_CURRENT_PLUGIN_NAME,
                place=place,
            )
        )
        return fn
    return decorator


# --- Document access ---------------------------------------------------------


def get_active_document() -> DocumentHandle | None:
    """Return a :class:`DocumentHandle` for the active document, or ``None``.

    Plugins should tolerate ``None`` — actions may fire with no active
    tab (palette with an empty workspace, etc.).
    """
    return _ACTIVE_DOCUMENT_PROVIDER()


# --- Text-transform invocation -----------------------------------------------


@dataclass(frozen=True)
class InvocationResult:
    ok: bool
    detail: str = ""


def invoke_text_transform(
    transform: PluginTextTransform,
    doc: DocumentHandle,
) -> InvocationResult:
    """Apply ``transform`` to ``doc`` atomically.

    Contract:

    * If ``transform.transform(doc.text)`` raises, the document is
      restored to its pre-call state (byte-identical text, unchanged
      dirty flag) and a failed :class:`InvocationResult` is returned.
    * On success, the new text replaces the document content in a
      single undo step. A successful :class:`InvocationResult` is
      returned.

    The caller (editor or settings UI) decides what to do with the
    result — typically: post an entry to the notifications drawer on
    failure, otherwise nothing.
    """
    if transform.transform is None:
        return InvocationResult(ok=False, detail="transform has no callback")

    fn = transform.transform
    snapshot = doc.text
    try:
        with doc.atomic_edit():
            try:
                new_text = fn(snapshot)
            except BaseException as exc:   # noqa: BLE001 — plugin code
                logger.warning(
                    "Text transform %r raised: %s", transform.id, exc
                )
                # Re-raise inside atomic_edit so the context manager
                # rolls the document back to snapshot.
                raise
            if new_text != snapshot:
                doc.replace_all(new_text)
    except BaseException as exc:   # noqa: BLE001
        return InvocationResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
    return InvocationResult(ok=True)

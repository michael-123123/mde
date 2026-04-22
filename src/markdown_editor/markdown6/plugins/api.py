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
    Field,
    PluginAction,
    PluginExporter,
    PluginFence,
    PluginMarkdownExtension,
    PluginPanel,
    PluginRegistry,
    PluginSettingsSchema,
    PluginTextTransform,
)

logger = getLogger(__name__)


# --- Module-level state ------------------------------------------------------

_REGISTRY: PluginRegistry = PluginRegistry()
_ACTIVE_DOCUMENT_PROVIDER: Callable[[], DocumentHandle | None] = lambda: None
_ALL_DOCUMENTS_PROVIDER: Callable[[], list[DocumentHandle]] = lambda: []
_MAIN_WINDOW_PROVIDER: Callable[[], object] = lambda: None

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


def _set_all_documents_provider(
    provider: Callable[[], list[DocumentHandle]],
) -> None:
    """Editor-internal: wire up :func:`get_all_documents`."""
    global _ALL_DOCUMENTS_PROVIDER
    _ALL_DOCUMENTS_PROVIDER = provider


def _set_main_window_provider(provider: Callable[[], object]) -> None:
    """Editor-internal: wire up :func:`get_main_window` (escape hatch)."""
    global _MAIN_WINDOW_PROVIDER
    _MAIN_WINDOW_PROVIDER = provider


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
    _require_non_empty("register_action", id=id, label=label)
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


def _require_non_empty(decorator_name: str, **fields: str) -> None:
    """Reject empty / whitespace-only string fields at decoration time.

    A blank ``id`` would silently let a second plugin claim the same
    "" id (id-collision check would also catch it, but only on the
    second plugin); a blank ``label`` would render a blank menu item
    with no clue what plugin owns it. Either is almost certainly a
    plugin-author typo — fail loud so they see it on import.
    """
    for name, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{decorator_name}: {name}={value!r} must be a "
                "non-empty, non-whitespace string."
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
    _require_non_empty("register_text_transform", id=id, label=label)
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


# --- Exporters ---------------------------------------------------------------


def register_exporter(
    *,
    id: str,
    label: str,
    extensions: list[str],
):
    """Decorator: register an export format.

    The decorated function ``(doc: DocumentHandle, path: Path) -> None``
    is called with the active document and the user-chosen target
    path. The framework opens a save dialog filtered to the supplied
    file extensions before invoking the callback.

    Args:
        id: Unique identifier for the exporter (e.g. ``"jekyll"``).
        label: Display label shown in the menu and palette.
        extensions: Non-empty list of file extensions (no dot,
            e.g. ``["md"]`` or ``["txt", "html"]``) used to build
            the save dialog filter.

    Menu placement: each exporter lands at ``Plugins/Export/<label>``.
    Disabled plugins' exporters are hidden along with the rest of
    their menu entries.
    """
    _require_non_empty("register_exporter", id=id, label=label)
    if not extensions:
        raise ValueError(
            f"register_exporter(id={id!r}): extensions must be a "
            "non-empty list, e.g. extensions=['md']"
        )

    def decorator(fn):
        _REGISTRY.register_exporter(PluginExporter(
            id=id,
            label=label,
            extensions=tuple(extensions),
            callback=fn,
            plugin_name=_CURRENT_PLUGIN_NAME,
        ))
        return fn
    return decorator


# --- Sidebar panels ----------------------------------------------------------


def register_panel(
    *,
    id: str,
    label: str,
    icon: str,
    _plugin_name: str | None = None,
):
    """Decorator: register a sidebar panel.

    The decorated factory ``() -> QWidget`` is called once at editor
    startup and the returned widget is added to the sidebar. The
    framework also adds an activity-bar tab with the supplied
    ``icon`` (typically an emoji) and ``label`` (also used as the
    panel's header text).

    NOTE: this is the one extension point that necessarily exposes
    Qt — building UI is intrinsically Qt-tied. The framework keeps
    the *registration* surface Qt-free (no Qt types in
    ``register_panel``), but the factory's return value is a
    ``QWidget``.
    """
    _require_non_empty("register_panel", id=id, label=label)
    actual_name = _plugin_name if _plugin_name is not None else _CURRENT_PLUGIN_NAME

    def decorator(fn):
        _REGISTRY.register_panel(PluginPanel(
            id=id,
            label=label,
            icon=icon,
            factory=fn,
            plugin_name=actual_name,
        ))
        return fn
    return decorator


# --- Fenced code blocks ------------------------------------------------------


def register_fence(
    name: str,
    *,
    _plugin_name: str | None = None,
):
    """Decorator: register a custom fenced-code-block renderer.

    The decorated function ``(source: str) -> str`` receives the
    fence's body and returns HTML to embed in the rendered output.
    Same conceptual mechanism as the built-in ``mermaid`` /
    ``graphviz`` fences, just routed through plugins.

    Args:
        name: The language tag the fence will match (e.g. ``"plantuml"``).
            Must be non-empty and globally unique across plugins.
    """
    if not name:
        raise ValueError("register_fence: name must be non-empty")

    actual_name = _plugin_name if _plugin_name is not None else _CURRENT_PLUGIN_NAME

    def decorator(fn):
        _REGISTRY.register_fence(PluginFence(
            name=name,
            callback=fn,
            plugin_name=actual_name,
        ))
        return fn
    return decorator


# --- Markdown extensions -----------------------------------------------------


def register_markdown_extension(
    extension,
    *,
    _plugin_name: str | None = None,
) -> None:
    """Register a python-markdown ``Extension`` instance.

    The framework adds it (along with extensions from any other
    enabled plugins) to every ``markdown.Markdown`` instance the
    editor builds via :func:`build_markdown`. Both the live preview
    and the export pipeline pick it up automatically.

    Disabled plugins' extensions are excluded — a toggle in
    Settings → Plugins rebuilds the preview's converter so the
    change takes effect immediately.

    The keyword-only ``_plugin_name`` is escape hatch for unit tests
    that need to register without going through the loader. Real
    plugins should leave it unset and let the loader stamp it.
    """
    name = _plugin_name if _plugin_name is not None else _CURRENT_PLUGIN_NAME
    _REGISTRY.register_markdown_extension(
        PluginMarkdownExtension(extension=extension, plugin_name=name)
    )


# --- Lifecycle signal decorators --------------------------------------------


def on_save(fn: Callable) -> Callable:
    """Decorator: subscribe to "document was saved to disk".

    The handler receives a :class:`DocumentHandle` for the just-saved
    document. Multiple plugins may subscribe; all fire on every save.
    Exceptions are caught and logged — a buggy handler doesn't break
    the editor or starve other handlers.
    """
    return _register_signal(fn, _SignalKind.SAVE)


def on_content_changed(fn: Callable) -> Callable:
    """Decorator: subscribe to "document text changed".

    Fires on every editor textChanged event — that's after every
    keystroke. Plugins doing expensive work should debounce inside
    their handler.
    """
    return _register_signal(fn, _SignalKind.CONTENT_CHANGED)


def on_file_opened(fn: Callable) -> Callable:
    """Decorator: subscribe to "a file was loaded into a tab"."""
    return _register_signal(fn, _SignalKind.FILE_OPENED)


def on_file_closed(fn: Callable) -> Callable:
    """Decorator: subscribe to "a tab is being closed"."""
    return _register_signal(fn, _SignalKind.FILE_CLOSED)


def _register_signal(fn: Callable, kind) -> Callable:
    # Imported here to avoid a circular import at module load time.
    from markdown_editor.markdown6.plugins.signals import SignalHandler
    _REGISTRY.register_signal_handler(SignalHandler(
        kind=kind,
        callback=fn,
        plugin_name=_CURRENT_PLUGIN_NAME,
    ))
    return fn


# Lazily resolved so api.py can be imported before signals.py.
class _LazySignalKind:
    @property
    def SAVE(self):
        from markdown_editor.markdown6.plugins.signals import SignalKind
        return SignalKind.SAVE

    @property
    def CONTENT_CHANGED(self):
        from markdown_editor.markdown6.plugins.signals import SignalKind
        return SignalKind.CONTENT_CHANGED

    @property
    def FILE_OPENED(self):
        from markdown_editor.markdown6.plugins.signals import SignalKind
        return SignalKind.FILE_OPENED

    @property
    def FILE_CLOSED(self):
        from markdown_editor.markdown6.plugins.signals import SignalKind
        return SignalKind.FILE_CLOSED


_SignalKind = _LazySignalKind()


# --- Document access ---------------------------------------------------------


def get_active_document() -> DocumentHandle | None:
    """Return a :class:`DocumentHandle` for the active document, or ``None``.

    Plugins should tolerate ``None`` — actions may fire with no active
    tab (palette with an empty workspace, etc.).
    """
    return _ACTIVE_DOCUMENT_PROVIDER()


def get_all_documents() -> list[DocumentHandle]:
    """Return a :class:`DocumentHandle` for every open tab.

    Useful for cross-tab plugins (e.g. project-wide find, batch
    transforms). Returns an empty list if no tabs are open.
    """
    return list(_ALL_DOCUMENTS_PROVIDER())


# --- Escape hatches (explicitly opt-in; not stable across versions) --------


def get_app_context():
    """Return the editor's :class:`AppContext` (escape hatch).

    Lets plugins read editor settings, observe theme changes, etc.
    Documented as an unstable opt-in — the plugin author writes
    ``from markdown_editor.plugins import get_app_context`` to
    deliberately reach into the editor's internals.
    """
    from markdown_editor.markdown6.app_context import get_app_context as _get
    return _get()


def get_main_window():
    """Return the editor's ``QMainWindow`` (escape hatch), or ``None``
    if no editor is constructed (tests, CLI).

    Use sparingly — for parenting plugin-owned dialogs, popping
    custom toolbars, etc. Plugin authors who reach for this accept
    that internal QMainWindow refactors may break their plugin.
    """
    return _MAIN_WINDOW_PROVIDER()


# --- Plugin-authored notifications ------------------------------------------


def _notify(severity: str, title: str, message: str, source: str | None) -> None:
    """Internal helper: route a plugin-authored notification to the
    AppContext's NotificationCenter. Source defaults to
    ``"plugin:<current_plugin_name>"`` when called inside a loader-managed
    import; pass an explicit ``source=`` to override.
    """
    from markdown_editor.markdown6.app_context import get_app_context

    if source is None:
        source = f"plugin:{_CURRENT_PLUGIN_NAME}" if _CURRENT_PLUGIN_NAME else ""
    ctx = get_app_context()
    poster = getattr(ctx.notifications, f"post_{severity}")
    poster(title, message, source=source)


def notify_info(title: str, message: str = "", *, source: str | None = None) -> None:
    """Post an info-level notification to the editor's notification drawer.

    Use for non-error events the user might want to see: "Export
    finished", "Cache rebuilt", etc. ``source`` defaults to
    ``"plugin:<name>"`` when called inside a loader-managed plugin
    import; pass explicitly to override.
    """
    _notify("info", title, message, source)


def notify_warning(title: str, message: str = "", *, source: str | None = None) -> None:
    """Post a warning-level notification (yellow icon in the drawer)."""
    _notify("warning", title, message, source)


def notify_error(title: str, message: str = "", *, source: str | None = None) -> None:
    """Post an error-level notification.

    Note: the framework already auto-routes uncaught exceptions from
    plugin actions / transforms / exporters / signal handlers to the
    drawer — you only need this when reporting an error you handled
    yourself but still want to surface to the user.
    """
    _notify("error", title, message, source)


# --- Settings schema (auto-rendered Configure dialog) ----------------------


_SUPPORTED_FIELD_TYPES = (str, int, float, bool)


def register_settings_schema(
    *,
    fields: list[Field],
    plugin_id: str | None = None,
) -> None:
    """Register a user-editable config schema for a plugin.

    Settings → Plugins gains a "Configure…" button on the row for
    this plugin; clicking it opens a dialog auto-rendered from the
    schema. Values are stored under :func:`plugin_settings(plugin_id)`,
    same as programmatic plugin settings.

    Args:
        fields: Non-empty list of :class:`Field` descriptors.
        plugin_id: The plugin's id (must match its TOML ``[tool.mde.plugin].name``).
            When omitted and called inside a plugin's import
            (loader-managed context), defaults to the current plugin
            being loaded.

    Raises:
        ValueError: if ``fields`` is empty, ``plugin_id`` can't be
            determined, the plugin already has a registered schema,
            or any field uses an unsupported ``type``.
    """
    if not fields:
        raise ValueError("register_settings_schema: fields must be non-empty")

    actual_id = plugin_id or _CURRENT_PLUGIN_NAME
    if not actual_id:
        raise ValueError(
            "register_settings_schema: plugin_id must be provided "
            "when not called inside the plugin loader's import context"
        )

    for f in fields:
        if f.type not in _SUPPORTED_FIELD_TYPES:
            raise ValueError(
                f"register_settings_schema: field {f.key!r} uses "
                f"unsupported type {f.type.__name__!r}; supported "
                f"types are: {', '.join(t.__name__ for t in _SUPPORTED_FIELD_TYPES)}"
            )

    _REGISTRY.register_settings_schema(
        PluginSettingsSchema(plugin_id=actual_id, fields=tuple(fields))
    )


# --- Settings ---------------------------------------------------------------


def plugin_settings(plugin_id: str):
    """Return a dict-like façade for ``plugin_id``'s scoped settings.

    Reads/writes are namespaced under ``plugins.<plugin_id>.<key>`` in
    the editor's main settings file, so plugin storage:

    * persists across restarts (atomic-write semantics piggyback on the
      editor's existing settings save flow);
    * is isolated per plugin id (plugin ``a`` and plugin ``b`` may both
      use ``"target"`` without collision);
    * cannot leak into editor settings — a plugin storing
      ``editor.font_size`` actually writes
      ``plugins.<id>.editor.font_size``.

    Plain dict semantics: ``settings["key"] = value``,
    ``settings.get("key", default)``, ``"key" in settings``,
    ``del settings["key"]``, ``list(settings)``.
    """
    # Imported lazily so this module can be imported in CLI contexts
    # where AppContext hasn't been initialized.
    from markdown_editor.markdown6.app_context import get_app_context
    return get_app_context().plugin_settings(plugin_id)


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

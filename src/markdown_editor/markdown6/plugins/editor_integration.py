"""Wire registered plugin actions into the editor's menus and palette.

Called once by :class:`MarkdownEditor` after the static menu bar is
built and the plugin loader has run. Reads the current
:func:`markdown_editor.markdown6.plugins.api.get_registry` contents and,
for each registered :class:`PluginAction` / :class:`PluginTextTransform`,
adds a ``QAction`` to the appropriate menu, binds the shortcut, and
appends a :class:`Command` entry for the command palette.

Menu path resolution follows the ``"Top/Sub[/Subsub]"`` slash-separated
convention the plugin declares in its registration (e.g.
``menu="Edit/Transform"``). Missing intermediate menus are created on
demand. An empty / unspecified menu path falls back to a top-level
"Plugins" menu so plugins that don't care about placement still surface
somewhere predictable.

Invocation rules enforced here:

* Action callbacks are called with **no arguments**. Plugins reach the
  active document through :func:`get_active_document`. The framework
  never passes a ``QObject`` to plugin code.
* Any exception raised by a plugin action is caught and logged. The
  editor never propagates a plugin failure out of a Qt slot.
* Text transforms are applied through :func:`invoke_text_transform`
  which snapshots the document and rolls back on error — content is
  either fully transformed or left byte-identical.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu

from markdown_editor.markdown6.components.command_palette import Command
from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.plugins.api import (
    _current_plugin,
    get_active_document,
    invoke_text_transform,
)
from markdown_editor.markdown6.plugins.registry import (
    PluginAction,
    PluginExporter,
    PluginRegistry,
    PluginTextTransform,
)

logger = getLogger(__name__)


# ---------------------------------------------------------------------------
# Menu-path resolution
# ---------------------------------------------------------------------------

# Per-window cache of QMenu references, keyed by slash-separated path.
#
# PySide6 ownership quirk: ``QAction.menu()`` creates/returns a Python
# wrapper that PySide6 considers to own the C++ QMenu. When the
# wrapper dies, PySide6 destroys the underlying C++ menu — even though
# Qt's parent-child ownership would normally keep it alive. After
# that, other wrappers around the same C++ pointer raise "Internal
# C++ object already deleted" on any call.
#
# The robust way out, mirrored from the editor's own menu-building
# code in ``actions.py``, is to construct each QMenu with an explicit
# long-lived Qt parent (``QMenu(title, window)``), which transfers
# ownership to the window and makes the menu Qt-owned rather than
# Python-owned. We also maintain a ``{path: QMenu}`` cache on the
# window, both to speed lookups and to hold a strong Python reference
# to every menu we touch — so even the Python wrapper never gets GC'd
# while the window is alive.
_MENU_CACHE_ATTR = "_mde_plugin_menu_cache"
# Set of paths that resolve_menu_path CREATED (vs. pre-registered via
# register_existing_menu). Only these may be hidden by
# apply_disabled_set when all their plugin actions are invisible — a
# pre-existing editor menu like "Edit" must never be hidden.
_PLUGIN_CREATED_MENUS_ATTR = "_mde_plugin_created_menu_paths"


def register_existing_menu(
    window: QMainWindow,
    path: str,
    menu: QMenu,
) -> None:
    """Tell the plugin integration about a pre-existing menu.

    The real ``MarkdownEditor`` calls this for each top-level menu it
    builds from ``MENU_STRUCTURE`` so a plugin registering under
    ``menu="Edit/Transform"`` can find ``Edit``. Tests call it if they
    pre-create menus they want plugins to attach under.
    """
    cache = _menu_cache(window)
    cache[path] = menu


def _menu_cache(window: QMainWindow) -> dict[str, QMenu]:
    cache = getattr(window, _MENU_CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(window, _MENU_CACHE_ATTR, cache)
    return cache


def resolve_menu_path(window: QMainWindow, path: str) -> QMenu:
    """Resolve a plugin's ``menu="..."`` string to the target ``QMenu``.

    Path conventions:

    * ``""`` → top-level ``Plugins`` menu (everything plugin-related
      lives there by default).
    * ``"Foo"`` / ``"Foo/Bar"`` → ``Plugins/Foo[/Bar]`` (namespaced).
    * ``"/Foo"`` / ``"/Foo/Bar"`` → top-level ``Foo[/Bar]`` (escape
      hatch into the editor's real menu structure — used only by
      system-style plugins that need to live next to a built-in
      command). The escape hatch carries an ordering obligation:
      see :func:`api._validate_place`.

    Cached menus (previously registered via
    :func:`register_existing_menu` or created by an earlier call) are
    reused. Newly-created menus are given ``window`` as their Qt
    parent so PySide6 doesn't own them — that prevents the "Internal
    C++ object already deleted" failure mode that bites when Qt and
    Python disagree on QMenu lifetime.
    """
    escape_hatch = path.startswith("/")
    if escape_hatch:
        path = path[1:]
    parts = [p.strip() for p in path.split("/") if p.strip()]

    if not escape_hatch:
        # Default: namespace everything under top-level "Plugins".
        parts = ["Plugins"] + parts
    elif not parts:
        # Bare "/" — degenerate; fall back to Plugins so we don't
        # surface a no-op, but this isn't a real use case.
        parts = ["Plugins"]

    cache = _menu_cache(window)
    created: set[str] = getattr(
        window, _PLUGIN_CREATED_MENUS_ATTR, None,
    ) or set()
    if not created:
        setattr(window, _PLUGIN_CREATED_MENUS_ATTR, created)
    parent_widget: Any = window.menuBar()   # QMenuBar or QMenu
    key = ""
    for i, seg in enumerate(parts):
        key = seg if i == 0 else f"{key}/{seg}"
        existing = cache.get(key)
        if existing is not None:
            parent_widget = existing
            continue
        # Qt-parent = window, so the menu is owned by the window and
        # survives Python wrapper GC.
        new_menu = QMenu(seg, window)
        parent_widget.addMenu(new_menu)
        cache[key] = new_menu
        created.add(key)
        parent_widget = new_menu
    return parent_widget


# ---------------------------------------------------------------------------
# Action / transform injection
# ---------------------------------------------------------------------------


_ACTIONS_BY_NAME_ATTR = "_mde_plugin_actions_by_name"
_PALETTE_BY_NAME_ATTR = "_mde_plugin_palette_by_name"


def _actions_by_name(window: QMainWindow) -> dict[str, list]:
    groups = getattr(window, _ACTIONS_BY_NAME_ATTR, None)
    if groups is None:
        groups = {}
        setattr(window, _ACTIONS_BY_NAME_ATTR, groups)
    return groups


def _palette_by_name(window: QMainWindow) -> dict[str, list[Command]]:
    groups = getattr(window, _PALETTE_BY_NAME_ATTR, None)
    if groups is None:
        groups = {}
        setattr(window, _PALETTE_BY_NAME_ATTR, groups)
    return groups


def inject_plugin_actions(
    window: QMainWindow,
    registry: PluginRegistry,
    palette_commands: list[Command],
) -> None:
    """Add menu entries + palette commands for everything in ``registry``.

    ``palette_commands`` is appended to in-place (the caller later
    passes the full list to :meth:`CommandPalette.set_commands`).

    Side effect: populates ``window._mde_plugin_actions_by_name`` and
    ``window._mde_plugin_palette_by_name`` as ``{plugin_name: [...]}``
    so the editor can toggle plugins live (hide/show actions, filter
    palette) without a restart. See :func:`apply_disabled_set` and
    :func:`plugin_palette_commands_filtered`.
    """
    for action in registry.actions():
        _inject_action(window, action, palette_commands)

    for transform in registry.text_transforms():
        _inject_transform(window, transform, palette_commands)

    for exporter in registry.exporters():
        _inject_exporter(window, exporter, palette_commands)


def _inject_action(
    window: QMainWindow,
    action: PluginAction,
    palette_commands: list[Command],
) -> None:
    menu = resolve_menu_path(window, action.menu)
    qa = QAction(action.label, window)
    qa.setObjectName(action.id)
    if action.shortcut:
        qa.setShortcut(QKeySequence(action.shortcut))

    callback = _wrap_action_callback(action)
    qa.triggered.connect(lambda *_args, _cb=callback: _cb())

    if not _insert_with_placement(menu, qa, action.place):
        # Placement failed (unknown anchor, etc. — already logged).
        # Forgiving fallback: attach to the top-level Plugins menu so
        # the action still has a visible home. The alternative of
        # leaving the QAction orphaned (in the window but in no menu)
        # hides the action from users even though it's still wired up
        # for shortcut + palette.
        resolve_menu_path(window, "").addAction(qa)
    cmd = Command(
        id=action.id,
        name=action.label,
        shortcut=action.shortcut,
        callback=callback,
        category=action.palette_category or "Plugin",
    )
    palette_commands.append(cmd)

    name = action.plugin_name or "_unattributed_"
    _actions_by_name(window).setdefault(name, []).append(qa)
    _palette_by_name(window).setdefault(name, []).append(cmd)


def _inject_exporter(
    window: QMainWindow,
    exporter: PluginExporter,
    palette_commands: list[Command],
) -> None:
    """Add an exporter as a menu entry under Plugins/Export.

    Triggering the entry opens a save dialog filtered by the
    exporter's file extensions and (on a non-cancelled selection)
    invokes the plugin's callback with ``(doc, path)``. If there is
    no active document, the dialog is NOT opened — better UX than
    making the user click through a save dialog only to find nothing
    happened.
    """
    menu = resolve_menu_path(window, "Export")
    qa = QAction(exporter.label, window)
    qa.setObjectName(exporter.id)

    callback = _wrap_exporter_callback(window, exporter)
    qa.triggered.connect(lambda *_args, _cb=callback: _cb())
    menu.addAction(qa)

    cmd = Command(
        id=exporter.id,
        name=exporter.label,
        shortcut="",
        callback=callback,
        category="Plugin Export",
    )
    palette_commands.append(cmd)

    name = exporter.plugin_name or "_unattributed_"
    _actions_by_name(window).setdefault(name, []).append(qa)
    _palette_by_name(window).setdefault(name, []).append(cmd)


def _wrap_exporter_callback(window: QMainWindow, exporter: PluginExporter):
    """Return a zero-arg callable that drives the dialog → invoke flow."""
    fn = exporter.callback

    def invoke():
        if fn is None:
            return
        doc = get_active_document()
        if doc is None:
            logger.debug(
                "Plugin exporter %r invoked with no active document",
                exporter.id,
            )
            return

        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        ext_glob = " ".join(f"*.{ext}" for ext in exporter.extensions)
        filter_str = f"{exporter.label} ({ext_glob});;All Files (*)"
        path_str, _ = QFileDialog.getSaveFileName(
            window, f"Export as {exporter.label}", "", filter_str,
        )
        if not path_str:
            return   # user cancelled
        try:
            with _current_plugin(exporter.plugin_name):
                fn(doc, Path(path_str))
        except BaseException as exc:   # noqa: BLE001 — plugin code
            logger.warning(
                "Plugin exporter %r raised: %s", exporter.id, exc,
                exc_info=True,
            )
            from markdown_editor.markdown6.notifications import (
                _post_plugin_error,
            )
            _post_plugin_error(
                exporter.plugin_name,
                f"Plugin export failed: {exporter.label}",
                f"{type(exc).__name__}: {exc}",
            )

    return invoke


def _inject_transform(
    window: QMainWindow,
    transform: PluginTextTransform,
    palette_commands: list[Command],
) -> None:
    menu = resolve_menu_path(window, transform.menu)
    qa = QAction(transform.label, window)
    qa.setObjectName(transform.id)
    if transform.shortcut:
        qa.setShortcut(QKeySequence(transform.shortcut))

    callback = _wrap_transform_callback(transform)
    qa.triggered.connect(lambda *_args, _cb=callback: _cb())

    if not _insert_with_placement(menu, qa, transform.place):
        # Forgiving fallback: attach to the top-level Plugins menu so
        # the transform still has a visible home. See ``_inject_action``
        # above for the rationale.
        resolve_menu_path(window, "").addAction(qa)
    cmd = Command(
        id=transform.id,
        name=transform.label,
        shortcut=transform.shortcut,
        callback=callback,
        category=transform.palette_category or "Plugin",
    )
    palette_commands.append(cmd)

    name = transform.plugin_name or "_unattributed_"
    _actions_by_name(window).setdefault(name, []).append(qa)
    _palette_by_name(window).setdefault(name, []).append(cmd)


# ---------------------------------------------------------------------------
# Placement helper (post-menu-resolution)
# ---------------------------------------------------------------------------


_PLACE_PROPERTY = "mde_place"   # set on each plugin QAction so a later
                                # same-place insertion can find its cluster.


def _insert_with_placement(menu: QMenu, qa: QAction, place: str) -> bool:
    """Insert ``qa`` into ``menu`` according to ``place``.

    Returns True if the insertion happened, False if it was skipped
    (e.g. unknown anchor id). Skipped insertions are logged.

    Same-``place`` insertions cluster: the second plugin to claim
    ``after:edit.find`` lands immediately after the first one's
    plugin action, not adjacent to ``edit.find``. Implementation:
    each inserted QAction is tagged with the ``place`` string via
    ``qa.setProperty(_PLACE_PROPERTY, place)``; subsequent inserts
    walk through tagged neighbours and append at the cluster's end.
    """
    qa.setProperty(_PLACE_PROPERTY, place or "end")

    if not place or place == "end":
        menu.addAction(qa)
        return True

    if place == "start":
        actions = list(menu.actions())
        # Cluster of existing "start"-tagged actions at the top of the
        # menu — append after the last one to preserve load order.
        last_start = None
        for a in actions:
            if a.property(_PLACE_PROPERTY) == "start":
                last_start = a
            else:
                break
        if last_start is not None:
            idx = actions.index(last_start) + 1
            anchor = actions[idx] if idx < len(actions) else None
        else:
            anchor = actions[0] if actions else None
        if anchor is not None:
            menu.insertAction(anchor, qa)
        else:
            menu.addAction(qa)
        return True

    if place.startswith("after:"):
        anchor_id = place[len("after:"):]
        return _insert_relative(menu, qa, anchor_id, place, before=False)

    if place.startswith("before:"):
        anchor_id = place[len("before:"):]
        return _insert_relative(menu, qa, anchor_id, place, before=True)

    logger.error(
        "plugin action %r in menu %r: unknown place= form %r — "
        "expected one of: 'after:<id>', 'before:<id>', 'start', 'end'.",
        qa.text(), menu.title(), place,
    )
    return False


def _insert_relative(
    menu: QMenu,
    qa: QAction,
    anchor_id: str,
    place: str,
    *,
    before: bool,
) -> bool:
    anchor = _find_action_by_id(menu, anchor_id)
    if anchor is None:
        logger.error(
            "plugin action %r in menu %r: place=%r references unknown "
            "anchor id %r — anchor not found in this menu. Action will "
            "not be inserted; the palette entry still works.",
            qa.text(), menu.title(), place, anchor_id,
        )
        return False

    actions = list(menu.actions())
    anchor_idx = actions.index(anchor)
    if before:
        # Each new before:X insertion goes immediately before X.
        # Existing same-place cluster members are pushed further left,
        # which preserves load order: earlier plugins end up further
        # from the anchor, latest plugin is closest to it.
        menu.insertAction(anchor, qa)
    else:
        # after: walk forward past any same-place cluster and insert
        # right at the cluster's end. Each new insertion lands further
        # from X, preserving load order (earliest plugin closest to X).
        last = anchor_idx
        for i in range(anchor_idx + 1, len(actions)):
            if actions[i].property(_PLACE_PROPERTY) == place:
                last = i
            else:
                break
        next_idx = last + 1
        if next_idx < len(actions):
            menu.insertAction(actions[next_idx], qa)
        else:
            menu.addAction(qa)
    return True


def _find_action_by_id(menu: QMenu, action_id: str) -> QAction | None:
    for a in menu.actions():
        if a.objectName() == action_id:
            return a
    return None


def apply_disabled_set(window: QMainWindow, disabled: set[str]) -> None:
    """Hide plugin menu entries for ``disabled`` plugin names; show the rest.

    Called by the editor at startup and again whenever
    ``plugins.disabled`` changes. Disabled actions are both
    ``setVisible(False)`` and ``setEnabled(False)`` — the former hides
    them from the menu, the latter blocks shortcut dispatch and
    explicit ``.trigger()`` calls.

    After the per-plugin visibility pass, any menu that was created
    by :func:`resolve_menu_path` (i.e. a plugin-created submenu, not
    a pre-existing editor menu) is hidden if all its child actions
    are now invisible — no empty dropdowns.
    """
    groups = _actions_by_name(window)
    for name, actions in groups.items():
        on = name not in disabled
        for qa in actions:
            qa.setVisible(on)
            qa.setEnabled(on)

    # Collapse empty plugin-created submenus (but never editor builtins).
    _hide_empty_plugin_menus(window)


def _hide_empty_plugin_menus(window: QMainWindow) -> None:
    cache = _menu_cache(window)
    created: set[str] = getattr(window, _PLUGIN_CREATED_MENUS_ATTR, None) or set()
    # Longest paths first — a parent's visibility check uses the
    # already-updated child visibility.
    for path in sorted(created, key=lambda p: -p.count("/")):
        menu = cache.get(path)
        if menu is None:
            continue
        any_visible = any(a.isVisible() for a in menu.actions())
        # `menuAction()` is the QAction that represents this submenu
        # in its parent menu; hiding it hides the submenu node.
        menu.menuAction().setVisible(any_visible)


def plugin_palette_commands_filtered(
    window: QMainWindow, disabled: set[str],
) -> list[Command]:
    """Return palette commands for all loaded plugins except disabled ones."""
    groups = _palette_by_name(window)
    out: list[Command] = []
    for name, cmds in groups.items():
        if name in disabled:
            continue
        out.extend(cmds)
    return out


# ---------------------------------------------------------------------------
# Plugin panel installation
# ---------------------------------------------------------------------------


_PANEL_INDEX_BY_NAME_ATTR = "_mde_plugin_panel_index_by_name"


def _panel_index_by_name(sidebar) -> dict[str, list[int]]:
    groups = getattr(sidebar, _PANEL_INDEX_BY_NAME_ATTR, None)
    if groups is None:
        groups = {}
        setattr(sidebar, _PANEL_INDEX_BY_NAME_ATTR, groups)
    return groups


def install_plugin_panels(sidebar, registry: PluginRegistry, *, disabled: set[str]) -> None:
    """Materialize each registered plugin panel into ``sidebar``.

    Calls each plugin's factory once, validates the return is a
    ``QWidget``, and adds it to the sidebar. Tracks the activity-bar
    index keyed by ``plugin_name`` (in the new
    ``_mde_plugin_panel_index_by_name`` attr on the sidebar) so the
    editor can later toggle visibility on
    ``plugins.disabled`` change. Disabled panels are still installed
    (their factory runs, the widget exists in the stack) but their
    activity-bar tab is hidden — this is what enables live re-enable
    without restart.

    Plugin factory exceptions are caught + logged; the panel is
    skipped. Factories returning non-``QWidget`` values are also
    rejected with a clear log entry.
    """
    from PySide6.QtWidgets import QWidget

    groups = _panel_index_by_name(sidebar)
    for panel in registry.panels():
        try:
            widget = panel.factory()
        except BaseException as exc:    # noqa: BLE001 — plugin code
            logger.warning(
                "Plugin panel %r factory raised: %s", panel.id, exc,
                exc_info=True,
            )
            continue
        if not isinstance(widget, QWidget):
            logger.warning(
                "Plugin panel %r factory returned %r — must return a "
                "QWidget; panel skipped.",
                panel.id, type(widget).__name__,
            )
            continue
        idx = sidebar.addPanel(panel.label, panel.icon, widget)
        groups.setdefault(panel.plugin_name or "_unattributed_", []).append(idx)
        if panel.plugin_name and panel.plugin_name in disabled:
            sidebar.setPanelVisible(idx, False)


def apply_panel_disabled_set(sidebar, disabled: set[str]) -> None:
    """Toggle visibility for installed plugin panels based on
    ``disabled``. Counterpart to :func:`apply_disabled_set` for the
    sidebar half of the editor."""
    groups = _panel_index_by_name(sidebar)
    for name, indices in groups.items():
        on = name not in disabled
        for idx in indices:
            sidebar.setPanelVisible(idx, on)


# ---------------------------------------------------------------------------
# Callback wrappers (enforce the "editor never crashes" contract)
# ---------------------------------------------------------------------------


def _wrap_action_callback(action: PluginAction):
    cb = action.callback

    def invoke():
        if cb is None:
            return
        try:
            with _current_plugin(action.plugin_name):
                cb()
        except BaseException as exc:   # noqa: BLE001 — plugin code
            logger.warning(
                "Plugin action %r raised: %s", action.id, exc,
                exc_info=True,
            )
            from markdown_editor.markdown6.notifications import (
                _post_plugin_error,
            )
            _post_plugin_error(
                action.plugin_name,
                f"Plugin action failed: {action.label}",
                f"{type(exc).__name__}: {exc}",
            )

    return invoke


def _wrap_transform_callback(transform: PluginTextTransform):
    def invoke():
        doc = get_active_document()
        if doc is None:
            logger.debug(
                "Text transform %r invoked with no active document",
                transform.id,
            )
            return
        with _current_plugin(transform.plugin_name):
            result = invoke_text_transform(transform, doc)
        if not result.ok:
            logger.warning(
                "Text transform %r failed: %s",
                transform.id, result.detail,
            )
            from markdown_editor.markdown6.notifications import (
                _post_plugin_error,
            )
            _post_plugin_error(
                transform.plugin_name,
                f"Plugin transform failed: {transform.label}",
                result.detail,
            )

    return invoke

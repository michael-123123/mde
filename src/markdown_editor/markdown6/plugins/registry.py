"""Records produced by plugin registration calls.

The loader imports plugin modules; those modules call
``register_action`` / ``register_text_transform`` / … from
:mod:`markdown_editor.markdown6.plugins.api`. Each call appends one of
the records defined here into the module-level registry, which the
editor drains after ``load_all`` returns.

These dataclasses are deliberately small, Qt-free, and independently
constructable so unit tests can build them directly without going
through the decorator path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class PluginAction:
    """An arbitrary plugin-provided command."""

    id: str
    label: str
    menu: str = ""                  # see resolve_menu_path docstring; default lands under top-level "Plugins"
    shortcut: str = ""              # QKeySequence string, optional
    palette_category: str = ""      # category in the command palette
    callback: Callable | None = None   # receives () or (ctx,) — we call w/o args and let plugin call get_active_document()
    plugin_name: str = ""           # owning plugin's name; stamped by the loader so the editor can toggle it live without a restart
    place: str = ""                 # required when menu starts with '/'; one of "after:ID", "before:ID", "start", "end"


@dataclass
class PluginTextTransform:
    """A pure ``(str) -> str`` transform surfaced as an atomic action."""

    id: str
    label: str
    menu: str = ""
    shortcut: str = ""
    palette_category: str = ""
    transform: Callable[[str], str] | None = None
    plugin_name: str = ""           # owning plugin's name; stamped by the loader so the editor can toggle it live without a restart
    place: str = ""                 # required when menu starts with '/'; same forms as PluginAction.place


class PluginRegistry:
    """Accumulates plugin registrations as the loader imports plugins."""

    def __init__(self) -> None:
        self._actions: list[PluginAction] = []
        self._transforms: list[PluginTextTransform] = []
        self._ids: set[str] = set()

    def register_action(self, action: PluginAction) -> None:
        self._require_unique_id(action.id)
        self._actions.append(action)
        self._ids.add(action.id)

    def register_text_transform(self, transform: PluginTextTransform) -> None:
        self._require_unique_id(transform.id)
        self._transforms.append(transform)
        self._ids.add(transform.id)

    def actions(self) -> list[PluginAction]:
        return list(self._actions)

    def text_transforms(self) -> list[PluginTextTransform]:
        return list(self._transforms)

    def clear(self) -> None:
        self._actions.clear()
        self._transforms.clear()
        self._ids.clear()

    def _require_unique_id(self, pid: str) -> None:
        if pid in self._ids:
            raise ValueError(
                f"plugin id {pid!r} is already registered — actions and "
                f"text transforms share an id namespace"
            )

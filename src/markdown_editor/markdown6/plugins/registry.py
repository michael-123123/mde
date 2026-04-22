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
    callback: Callable | None = None   # receives () or (ctx,) - we call w/o args and let plugin call get_active_document()
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


@dataclass
class PluginMarkdownExtension:
    """A plugin-supplied ``markdown.Extension`` instance."""
    extension: object   # markdown.Extension subclass instance
    plugin_name: str = ""


@dataclass
class PluginExporter:
    """A plugin-supplied export format.

    The framework adds a ``Plugins/Export/<label>`` menu item that
    opens a save dialog filtered to ``extensions`` and invokes
    ``callback(doc, path)`` with the chosen path on success.
    """
    id: str
    label: str
    extensions: tuple[str, ...]   # file extensions, e.g. ("md", "txt")
    callback: Callable | None = None
    plugin_name: str = ""


@dataclass
class PluginFence:
    """A plugin-supplied fenced-code-block renderer.

    When a fenced block with language tag ``name`` appears in the
    markdown source, the framework calls ``callback(source)`` and
    embeds the returned HTML in the rendered output.
    """
    name: str
    callback: Callable[[str], str] | None = None
    plugin_name: str = ""


@dataclass
class PluginPanel:
    """A plugin-supplied sidebar panel.

    The plugin's factory returns a ``QWidget`` to live in the
    sidebar's stacked widget. The framework adds an activity-bar tab
    with the supplied ``icon`` and ``label`` (also used as the panel
    header text).
    """
    id: str
    label: str
    icon: str
    factory: Callable | None = None    # () -> QWidget
    plugin_name: str = ""


@dataclass(frozen=True)
class Field:
    """One user-editable field in a plugin's config schema.

    The framework auto-renders these in a per-plugin Configure dialog
    accessible from Settings → Plugins. Storage routes through
    :func:`plugin_settings(plugin_id)`; the schema is just metadata
    describing which keys are user-editable and how to render them.
    """
    key: str
    label: str
    type: type = str
    default: object = None
    description: str = ""
    choices: tuple[str, ...] | None = None
    min: int | float | None = None
    max: int | float | None = None
    widget: str = ""    # "" (default), "path", "multiline" (str-only hints)


@dataclass
class PluginSettingsSchema:
    """A plugin's full user-editable config schema."""
    plugin_id: str
    fields: tuple[Field, ...]


class PluginRegistry:
    """Accumulates plugin registrations as the loader imports plugins."""

    def __init__(self) -> None:
        self._actions: list[PluginAction] = []
        self._transforms: list[PluginTextTransform] = []
        self._ids: set[str] = set()
        # Lifecycle-event subscriptions, keyed by SignalKind. Stored
        # as Any to avoid a circular dependency with signals.py.
        self._signal_handlers: dict = {}
        self._markdown_extensions: list[PluginMarkdownExtension] = []
        self._exporters: list[PluginExporter] = []
        self._fences: dict[str, PluginFence] = {}
        self._panels: list[PluginPanel] = []
        self._settings_schemas: dict[str, PluginSettingsSchema] = {}

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

    def register_signal_handler(self, handler) -> None:
        """Append ``handler`` to the list for its ``kind``. Multiple
        plugins may subscribe to the same signal; all fire on dispatch."""
        self._signal_handlers.setdefault(handler.kind, []).append(handler)

    def signal_handlers(self, kind) -> list:
        return list(self._signal_handlers.get(kind, []))

    def register_markdown_extension(
        self, ext: PluginMarkdownExtension,
    ) -> None:
        """Append a plugin-supplied python-markdown Extension to the
        list consumed by ``build_markdown(extra_extensions=...)``."""
        self._markdown_extensions.append(ext)

    def markdown_extensions(self) -> list[PluginMarkdownExtension]:
        return list(self._markdown_extensions)

    def active_markdown_extensions(self, *, disabled: set[str]) -> list:
        """Return the underlying ``markdown.Extension`` instances for
        every registered plugin whose name is NOT in ``disabled``.
        Suitable for passing directly to ``build_markdown``.
        """
        return [
            rec.extension for rec in self._markdown_extensions
            if not rec.plugin_name or rec.plugin_name not in disabled
        ]

    def register_exporter(self, exporter: PluginExporter) -> None:
        self._require_unique_id(exporter.id)
        self._exporters.append(exporter)
        self._ids.add(exporter.id)

    def exporters(self) -> list[PluginExporter]:
        return list(self._exporters)

    def register_fence(self, fence: PluginFence) -> None:
        if fence.name in self._fences:
            raise ValueError(
                f"plugin fence name {fence.name!r} is already registered"
            )
        self._fences[fence.name] = fence

    def fences(self) -> list[PluginFence]:
        return list(self._fences.values())

    def get_fence(self, name: str) -> PluginFence | None:
        return self._fences.get(name)

    def register_panel(self, panel: PluginPanel) -> None:
        self._require_unique_id(panel.id)
        self._panels.append(panel)
        self._ids.add(panel.id)

    def panels(self) -> list[PluginPanel]:
        return list(self._panels)

    def register_settings_schema(self, schema: PluginSettingsSchema) -> None:
        if schema.plugin_id in self._settings_schemas:
            raise ValueError(
                f"plugin {schema.plugin_id!r} already has a settings "
                "schema registered"
            )
        self._settings_schemas[schema.plugin_id] = schema

    def get_settings_schema(self, plugin_id: str) -> PluginSettingsSchema | None:
        return self._settings_schemas.get(plugin_id)

    def settings_schemas(self) -> list[PluginSettingsSchema]:
        return list(self._settings_schemas.values())

    def clear(self) -> None:
        self._actions.clear()
        self._transforms.clear()
        self._ids.clear()
        self._signal_handlers.clear()
        self._markdown_extensions.clear()
        self._exporters.clear()
        self._fences.clear()
        self._panels.clear()
        self._settings_schemas.clear()

    def _require_unique_id(self, pid: str) -> None:
        if pid in self._ids:
            raise ValueError(
                f"plugin id {pid!r} is already registered — actions and "
                f"text transforms share an id namespace"
            )

"""Per-plugin scoped settings storage.

Each plugin gets a dict-like façade via
:meth:`AppContext.plugin_settings(plugin_id)`. Reads and writes are
namespaced under ``plugins.<plugin_id>.<key>`` in the main settings
file, so plugin storage:

* persists alongside the editor's own settings (one config file, atomic
  writes via the existing :class:`SettingsManager`);
* is isolated per plugin id (plugin A and plugin B can both have a
  ``"shared_key"`` without colliding);
* never leaks into the editor's own settings (a plugin writing
  ``"editor.font_size"`` actually writes ``"plugins.<id>.editor.font_size"``).

This is the **internal/programmatic** layer - plugins use it to remember
state across runs (last-used path, cached tokens, counters). A separate
schema-driven layer (planned, not yet built) sits on top and auto-renders
a user-facing config UI from a plugin-supplied field list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from markdown_editor.markdown6.app_context import AppContext


class PluginSettings:
    """Dict-like view over the main settings, scoped to one plugin id."""

    def __init__(self, ctx: "AppContext", plugin_id: str) -> None:
        if not plugin_id:
            raise ValueError("plugin_id must be a non-empty string")
        if "." in plugin_id:
            raise ValueError(
                f"plugin_id {plugin_id!r} must not contain '.' — that's "
                "the namespace separator, and using it would let one "
                "plugin write into another plugin's namespace."
            )
        self._ctx = ctx
        self._plugin_id = plugin_id
        self._prefix = f"plugins.{plugin_id}."

    # ------------------------------------------------------------------
    # Mapping protocol
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        sentinel = object()
        val = self._ctx.get(self._prefix + key, sentinel)
        if val is sentinel:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        self._ctx.set(self._prefix + key, value)

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        # Underlying SettingsManager has no public delete; pop from the
        # internal dict and persist.
        manager = self._ctx._settings_manager
        manager._settings.pop(self._prefix + key, None)
        manager.save()

    def __contains__(self, key: str) -> bool:
        return self._has_real(self._prefix + key)

    def __iter__(self) -> Iterator[str]:
        manager = self._ctx._settings_manager
        for full_key in manager._settings:
            if full_key.startswith(self._prefix):
                yield full_key[len(self._prefix):]

    def __len__(self) -> int:
        return sum(1 for _ in self)

    # ------------------------------------------------------------------
    # dict-style helpers
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        return default

    def keys(self) -> list[str]:
        return list(iter(self))

    def items(self) -> list[tuple[str, Any]]:
        return [(k, self[k]) for k in self]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _has_real(self, full_key: str) -> bool:
        """Membership test that distinguishes "key was explicitly set"
        from "key is missing but ctx.get returned its default of None."
        Direct lookup against the underlying settings dict avoids the
        DEFAULT_SETTINGS layer entirely (plugin keys aren't in defaults).
        """
        return full_key in self._ctx._settings_manager._settings

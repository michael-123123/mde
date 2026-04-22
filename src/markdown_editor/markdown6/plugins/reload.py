"""Discover-only plugin reload.

The editor's "Reload plugins" command (palette + button on the Plugins
settings page) routes here. The current scope is **discovery-only**:
re-runs ``discover_plugins`` on the same roots the editor used at
startup, diffs against the in-process plugin list, and posts a
NotificationCenter entry summarizing what's new on disk vs. what's
been removed. The user is told to restart for changes to take effect.

Why not actually hot-reload?

True hot-reload would have to tear down every plugin-injected QAction
(currently connected to slots), every plugin sidebar panel widget,
every plugin signal handler, every plugin markdown extension wired
into the live ``self.md`` converter, etc. Doing that safely is its
own project. Discover-only is honest about the limitation while
still being useful — most of the time the user just wants to know
"did my new plugin get picked up?" and discovery answers that.

Future hot-reload work would build on top of this: add an actual
swap-and-rebuild path while keeping discover-only as the safe
default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from markdown_editor.markdown6.plugins.loader import discover_plugins
from markdown_editor.markdown6.plugins.plugin import PluginSource


@dataclass
class ReloadDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def reload_plugins(
    ctx,
    roots: list[tuple[Path, PluginSource]],
) -> ReloadDiff:
    """Re-run discovery on ``roots`` and post a notification with the diff.

    Returns a :class:`ReloadDiff` listing names added/removed compared
    to ``ctx.get_plugins()``. The notification text is also keyed off
    the diff so the user sees the same info in the bell drawer.
    """
    discovered = discover_plugins(roots)
    discovered_names = {p.name for p in discovered}
    current_names = {p.name for p in ctx.get_plugins()}

    added = sorted(discovered_names - current_names)
    removed = sorted(current_names - discovered_names)

    diff = ReloadDiff(added=added, removed=removed)

    if not added and not removed:
        ctx.notifications.post_info(
            "Reload plugins: no changes",
            "Plugin directories on disk match the currently-loaded set.",
            source="system",
        )
        return diff

    parts = []
    if added:
        parts.append(f"new on disk: {', '.join(added)}")
    if removed:
        parts.append(f"removed from disk: {', '.join(removed)}")
    summary = "; ".join(parts)

    ctx.notifications.post_info(
        "Reload plugins: changes detected",
        f"{summary}. Restart the editor to apply changes.",
        source="system",
    )
    return diff

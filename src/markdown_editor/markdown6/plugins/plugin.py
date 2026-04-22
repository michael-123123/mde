"""Plugin record types — data carried around by the loader.

The loader returns a list of :class:`Plugin` records. Each has a
:class:`PluginStatus` explaining why it is (or isn't) active, plus a
human-readable ``detail`` string for the Settings → Plugins tab to
display.

These types are deliberately free of any Qt dependency so they can be
used from unit tests that don't spin up a QApplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import ModuleType

from markdown_editor.markdown6.plugins.metadata import PluginMetadata


class PluginSource(Enum):
    """Where a plugin was discovered from.

    Only two variants: plugins are either shipped with the editor
    (``BUILTIN``) or installed / pointed at by the end user
    (``USER``). Plugins contributed by ``--plugins-dir`` on the CLI
    or by the ``plugins.extra_dirs`` setting are all tagged ``USER``
    — they're user-controlled, just via different entry points.
    Collapsing those into one variant keeps the enum focused on
    "is this a ship-with-the-app plugin?" (the only distinction any
    consumer currently cares about — builtin plugins ship
    guaranteed-compatible, user plugins may not). If a later UX
    decision needs to surface "which entry point" separately (e.g.
    "added via CLI in this session"), add a sibling field on the
    ``Plugin`` record rather than expanding this enum.
    """
    BUILTIN = "builtin"
    USER = "user"


class PluginStatus(Enum):
    ENABLED = "enabled"
    DISABLED_BY_USER = "disabled_by_user"
    LOAD_FAILURE = "load_failure"
    MISSING_DEPS = "missing_deps"
    METADATA_ERROR = "metadata_error"
    API_MISMATCH = "api_mismatch"


@dataclass
class Plugin:
    """One discovered plugin. Mutated in-place by the loader as it
    advances through discovery → dep check → import."""

    name: str
    source: "PluginSource"
    directory: Path
    metadata: PluginMetadata | None = None
    module: ModuleType | None = None
    status: PluginStatus = PluginStatus.ENABLED
    detail: str = ""
    missing_deps: tuple[str, ...] = field(default_factory=tuple)
    # Populated by discovery if the plugin's directory contains a
    # README.md. Read by the Settings → Plugins info dialog.
    readme_path: Path | None = None

    @property
    def is_errored(self) -> bool:
        """True if the plugin cannot run (and the user can't re-enable it)."""
        return self.status in (
            PluginStatus.LOAD_FAILURE,
            PluginStatus.MISSING_DEPS,
            PluginStatus.METADATA_ERROR,
            PluginStatus.API_MISMATCH,
        )

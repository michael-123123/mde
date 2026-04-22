"""Plugin discovery and import pipeline.

The editor calls :func:`load_all` once at startup with a list of
``(root_dir, source)`` pairs (typically the builtin plugin dir and the
user config plugin dir). The returned list contains one :class:`Plugin`
record per discovered plugin, with a :class:`PluginStatus` explaining
whether it loaded successfully.

Pipeline, per plugin directory ``<root>/<name>/``:

1. **Discovery** — require ``<name>/<name>.py`` and ``<name>/<name>.toml``.
   Missing or mismatched filenames yield a :class:`PluginStatus.LOAD_FAILURE`
   or :class:`PluginStatus.METADATA_ERROR` record; the loader does not
   raise.
2. **Metadata** — parse the TOML. Any :class:`MetadataError` becomes a
   :class:`PluginStatus.METADATA_ERROR` record.
3. **User disable check** — if the plugin's name is in ``user_disabled``,
   mark it :class:`PluginStatus.DISABLED_BY_USER` and skip import. This is
   also how we guarantee an errored plugin that the user already toggled
   off doesn't keep raising on startup.
4. **API version check** — post-1.0, reject plugins whose major API
   version differs from :data:`MDE_API_VERSION`. Pre-1.0 (current), the
   check is skipped (the API is explicitly unstable).
5. **Dependency check** — for each declared python dependency, try
   :func:`importlib.util.find_spec`. Any miss records
   :class:`PluginStatus.MISSING_DEPS` with the missing module names and
   skips import.
6. **Import** — finally, :func:`importlib.util.spec_from_file_location`
   + :meth:`exec_module` to run the plugin's top-level code. Any
   exception becomes :class:`PluginStatus.LOAD_FAILURE`. The plugin's
   registration calls (``register_action`` etc.) run as side-effects of
   this import.

The loader is designed so **nothing the user can put in the plugin
directory can crash the editor**. All failure modes are recorded as
statuses.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import traceback
from pathlib import Path

from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.plugins.metadata import (
    MetadataError,
    load_metadata,
)
from markdown_editor.markdown6.plugins.plugin import (
    Plugin,
    PluginSource,
    PluginStatus,
)

logger = getLogger(__name__)


# Major-version component of the plugin API. Pre-1.0 (= "0") the API is
# explicitly unstable and mismatch checks are skipped. Once we hit
# v1.0.0 of mde, this becomes the MDE major and plugins declare their
# compatibility by setting `mde_api_version` to the same string.
MDE_API_VERSION = "0"


# Splits "requests>=2.0" / "requests == 1.0" / "requests[extras]" /
# "requests ; sys_platform=='linux'" etc. into just the module name.
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)")


def _module_name_from_requirement(req: str) -> str:
    m = _REQ_NAME_RE.match(req)
    return m.group(1) if m else req.strip()


def discover_plugins(
    roots: list[tuple[Path, PluginSource]],
) -> list[Plugin]:
    """Scan each ``(root, source)`` pair and return one :class:`Plugin`
    record per subdirectory of ``root``.

    Non-existent or non-directory ``root`` paths are silently skipped —
    on a fresh install the user plugin dir may not exist yet, and that's
    fine.

    This step reads and validates metadata, but does NOT import the
    plugin module. Records with a non-default status (METADATA_ERROR,
    LOAD_FAILURE from missing files) are returned as-is; callers should
    treat them like any other plugin and display the detail string.
    """
    seen_names: dict[str, Plugin] = {}
    plugins: list[Plugin] = []

    for root, source in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                # Skip dunder dirs (e.g. __pycache__) and hidden dirs.
                continue

            name = entry.name
            py_file = entry / f"{name}.py"
            toml_file = entry / f"{name}.toml"

            plugin = Plugin(name=name, source=source, directory=entry)

            if not py_file.is_file():
                plugin.status = PluginStatus.LOAD_FAILURE
                plugin.detail = (
                    f"expected entry-point file not found: {py_file.name} "
                    f"(the plugin's .py file must match the directory name)"
                )
            elif not toml_file.is_file():
                plugin.status = PluginStatus.METADATA_ERROR
                plugin.detail = (
                    f"expected metadata file not found: {toml_file.name}"
                )
            else:
                try:
                    plugin.metadata = load_metadata(toml_file)
                except MetadataError as exc:
                    plugin.status = PluginStatus.METADATA_ERROR
                    plugin.detail = str(exc)

                # The TOML's [tool.mde.plugin].name MUST match the
                # directory name. Otherwise the plugin's internal
                # identity disagrees silently with how it's referenced
                # in plugins.disabled, plugin_settings(id), the schema
                # registry, etc. — a recipe for hard-to-debug bugs.
                if (
                    plugin.metadata is not None
                    and plugin.metadata.name != plugin.name
                ):
                    plugin.status = PluginStatus.METADATA_ERROR
                    plugin.detail = (
                        f"TOML [tool.mde.plugin].name = "
                        f"{plugin.metadata.name!r} does not match "
                        f"plugin directory name {plugin.name!r}; they "
                        f"must match."
                    )

            # Optional README.md alongside the plugin's .py / .toml.
            # Read by the Settings → Plugins info dialog.
            readme = entry / "README.md"
            if readme.is_file():
                plugin.readme_path = readme

            # Name collision: user plugin overrides builtin with the
            # same name. Record and skip the duplicate so we don't double-
            # register.
            existing = seen_names.get(name)
            if existing is not None:
                if existing.source == PluginSource.BUILTIN and source == PluginSource.USER:
                    # User version wins; drop the builtin.
                    plugins.remove(existing)
                else:
                    logger.warning(
                        "Duplicate plugin name %r (ignoring %s %s)",
                        name, source.value, entry,
                    )
                    continue
            seen_names[name] = plugin
            plugins.append(plugin)

    return plugins


def load_plugin(plugin: Plugin, *, user_disabled: set[str]) -> Plugin:
    """Finish loading a single discovered plugin.

    Mutates ``plugin`` in place. Never raises — every failure mode is
    recorded in :attr:`Plugin.status` and :attr:`Plugin.detail`.

    A plugin in ``user_disabled`` is still imported and has its code
    loaded into memory — only its status is set to
    :attr:`PluginStatus.DISABLED_BY_USER` after a successful import.
    This is what allows the editor to re-enable a previously-disabled
    plugin without a restart: its ``QAction`` is already created, just
    hidden, so toggling visibility flips it back on instantly.
    """
    # If discovery already marked it as errored (bad layout, bad
    # metadata), don't try to import.
    if plugin.is_errored:
        return plugin

    assert plugin.metadata is not None  # discovery populated it

    # --- API version check (post-1.0 only) -----------------------------------
    if MDE_API_VERSION != "0":
        if plugin.metadata.mde_api_version.split(".")[0] != MDE_API_VERSION:
            plugin.status = PluginStatus.API_MISMATCH
            plugin.detail = (
                f"plugin declares mde_api_version "
                f"'{plugin.metadata.mde_api_version}', editor provides "
                f"'{MDE_API_VERSION}'"
            )
            return plugin

    # --- Dependency check -----------------------------------------------------
    missing: list[str] = []
    for req in plugin.metadata.dependencies:
        mod_name = _module_name_from_requirement(req)
        try:
            spec = importlib.util.find_spec(mod_name)
        except (ValueError, ModuleNotFoundError, ImportError):
            spec = None
        if spec is None:
            missing.append(mod_name)
    if missing:
        plugin.status = PluginStatus.MISSING_DEPS
        plugin.detail = "missing python modules: " + ", ".join(missing)
        plugin.missing_deps = tuple(missing)
        return plugin

    # --- Import ---------------------------------------------------------------
    py_file = plugin.directory / f"{plugin.name}.py"
    mod_qualname = f"mde_plugin__{plugin.source.value}__{plugin.name}"
    spec = importlib.util.spec_from_file_location(mod_qualname, py_file)
    if spec is None or spec.loader is None:
        plugin.status = PluginStatus.LOAD_FAILURE
        plugin.detail = f"could not build import spec for {py_file}"
        return plugin

    module = importlib.util.module_from_spec(spec)
    # Insert before exec so intra-plugin imports by name resolve.
    sys.modules[mod_qualname] = module
    # Tell the registration decorators which plugin is currently being
    # imported so their records can be stamped with plugin.name. Done
    # inline (not via contextmanager) so a raise during exec_module
    # still clears the global in the finally block.
    from markdown_editor.markdown6.plugins import api as _api
    _api._set_current_plugin_name(plugin.name)
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:   # noqa: BLE001 — plugin code runs arbitrary Python
        # Remove the half-initialized module so a later "Reload plugins"
        # doesn't find a ghost entry.
        sys.modules.pop(mod_qualname, None)
        plugin.status = PluginStatus.LOAD_FAILURE
        plugin.detail = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Plugin %r failed to load:\n%s",
            plugin.name,
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
        return plugin
    finally:
        _api._set_current_plugin_name("")

    plugin.module = module
    if plugin.name in user_disabled:
        plugin.status = PluginStatus.DISABLED_BY_USER
        plugin.detail = "disabled by user"
    else:
        plugin.status = PluginStatus.ENABLED
    return plugin


def load_all(
    roots: list[tuple[Path, PluginSource]],
    *,
    user_disabled: set[str] | None = None,
) -> list[Plugin]:
    """Discover and load every plugin under ``roots``.

    Thin convenience wrapper around :func:`discover_plugins` +
    :func:`load_plugin`. Designed to be called exactly once at editor
    startup; returned list is authoritative for the lifetime of the
    process.
    """
    user_disabled = user_disabled or set()
    plugins = discover_plugins(roots)
    for plugin in plugins:
        load_plugin(plugin, user_disabled=user_disabled)
    return plugins

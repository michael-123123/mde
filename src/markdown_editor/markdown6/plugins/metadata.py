"""Plugin metadata (``<name>.toml``) parsing and validation.

Each plugin ships a sibling TOML file declaring its name, version, and
optional dependencies. The loader reads this file BEFORE importing the
plugin module, so any declared dependencies can be verified up-front and
the plugin can be disabled with a clear reason instead of crashing at
import time with an obscure ImportError.

Section name: ``[tool.mde.plugin]``. The ``[tool.<name>]`` prefix is
the pyproject.toml convention (every tool nests under ``tool``), which
means a plugin's metadata file can also live as a slice of a wider
``pyproject.toml`` without conflicting with anything else.

Schema (all under the ``[tool.mde.plugin]`` table):

    name             str, required, non-empty; MUST match dir name
    version          str, required
    description      str, optional
    author           str, optional
    mde_api_version  str, optional, defaults to "0" (pre-stable)

    [tool.mde.plugin.dependencies]
    python           list[str], optional — importable module names or
                     pip-style requirements (only the module-name part
                     is actually checked at load time; version specs
                     are advisory and will be handled in a later phase)

Unknown keys and unknown subtables are tolerated to keep forward-
compatibility cheap: a plugin written against a future editor can still
load on an older editor, as long as its required fields are present.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MetadataError(ValueError):
    """Raised when a plugin's metadata file is missing or invalid."""


@dataclass(frozen=True)
class PluginMetadata:
    name: str
    version: str
    description: str = ""
    author: str = ""
    mde_api_version: str = "0"
    dependencies: tuple[str, ...] = ()


def load_metadata(toml_path: Path) -> PluginMetadata:
    """Parse a plugin's ``<name>.toml`` file.

    Raises :class:`MetadataError` if the file is missing, unparseable,
    or fails schema validation. Never raises any other exception type —
    the loader relies on that to record a clean "bad metadata" status
    for the plugin.
    """
    if not toml_path.is_file():
        raise MetadataError(f"metadata file not found: {toml_path}")

    try:
        with toml_path.open("rb") as fh:
            raw: dict[str, Any] = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise MetadataError(f"could not parse {toml_path}: {exc}") from exc
    except OSError as exc:
        raise MetadataError(f"could not read {toml_path}: {exc}") from exc

    # Walk raw["tool"]["mde"]["plugin"] — pyproject-style namespacing
    # so the same TOML body can also live inside a project's
    # pyproject.toml without colliding with [tool.<other>] sections.
    plugin_tbl: Any = raw.get("tool", {}).get("mde", {}).get("plugin")
    if not isinstance(plugin_tbl, dict):
        raise MetadataError(
            f"{toml_path}: missing required [tool.mde.plugin] table"
        )

    name = _require_str(plugin_tbl, "name", toml_path, allow_empty=False)
    version = _require_str(plugin_tbl, "version", toml_path, allow_empty=False)
    description = _optional_str(plugin_tbl, "description", toml_path)
    author = _optional_str(plugin_tbl, "author", toml_path)
    api = _optional_str(plugin_tbl, "mde_api_version", toml_path) or "0"

    dependencies = _parse_dependencies(
        plugin_tbl.get("dependencies"), toml_path
    )

    return PluginMetadata(
        name=name,
        version=version,
        description=description,
        author=author,
        mde_api_version=api,
        dependencies=dependencies,
    )


def _require_str(
    table: dict[str, Any],
    key: str,
    path: Path,
    *,
    allow_empty: bool,
) -> str:
    if key not in table:
        raise MetadataError(f"{path}: [tool.mde.plugin] is missing required key '{key}'")
    val = table[key]
    if not isinstance(val, str):
        raise MetadataError(
            f"{path}: [tool.mde.plugin].{key} must be a string, got {type(val).__name__}"
        )
    if not allow_empty and not val.strip():
        raise MetadataError(f"{path}: [tool.mde.plugin].{key} must be non-empty")
    return val


def _optional_str(table: dict[str, Any], key: str, path: Path) -> str:
    if key not in table:
        return ""
    val = table[key]
    if not isinstance(val, str):
        raise MetadataError(
            f"{path}: [tool.mde.plugin].{key} must be a string, got {type(val).__name__}"
        )
    return val


def _parse_dependencies(
    deps_tbl: Any,
    path: Path,
) -> tuple[str, ...]:
    if deps_tbl is None:
        return ()
    if not isinstance(deps_tbl, dict):
        raise MetadataError(
            f"{path}: [tool.mde.plugin.dependencies] must be a table"
        )

    python = deps_tbl.get("python")
    if python is None:
        return ()
    if not isinstance(python, list):
        raise MetadataError(
            f"{path}: [tool.mde.plugin.dependencies].python must be a list, "
            f"got {type(python).__name__}"
        )
    for i, item in enumerate(python):
        if not isinstance(item, str):
            raise MetadataError(
                f"{path}: [tool.mde.plugin.dependencies].python[{i}] must be a string, "
                f"got {type(item).__name__}"
            )
    return tuple(python)

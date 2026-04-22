"""Tests for plugin metadata parsing (plugins/metadata.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.plugins.metadata import (
    MetadataError,
    PluginMetadata,
    load_metadata,
)


def _write_toml(tmp_path: Path, content: str, name: str = "plugin.toml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimal_valid(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "hello"
        version = "1.0.0"
    """)
    m = load_metadata(toml)
    assert isinstance(m, PluginMetadata)
    assert m.name == "hello"
    assert m.version == "1.0.0"
    assert m.description == ""
    assert m.author == ""
    assert m.dependencies == ()


def test_full_valid(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "full"
        version = "2.3.4"
        description = "a full plugin"
        author = "Me"
        mde_api_version = "1"

        [tool.mde.plugin.dependencies]
        python = ["requests>=2.0", "tomli"]
    """)
    m = load_metadata(toml)
    assert m.name == "full"
    assert m.version == "2.3.4"
    assert m.description == "a full plugin"
    assert m.author == "Me"
    assert m.mde_api_version == "1"
    assert m.dependencies == ("requests>=2.0", "tomli")


def test_unknown_keys_tolerated(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "x"
        version = "0.1"
        future_feature = "whatever"

        [tool.mde.plugin.future_subtable]
        key = "value"

        [some.other.tool]
        key = "value"
    """)
    # Unknown keys + unknown subtables + sibling [tool.<other>] sections
    # must not cause MetadataError - forward compatibility / coexistence
    # with embedding in a wider pyproject-style TOML.
    m = load_metadata(toml)
    assert m.name == "x"


def test_no_dependencies_section_means_empty(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "nodeps"
        version = "0.1"
    """)
    m = load_metadata(toml)
    assert m.dependencies == ()


def test_empty_python_deps_list(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "nodeps"
        version = "0.1"

        [tool.mde.plugin.dependencies]
        python = []
    """)
    m = load_metadata(toml)
    assert m.dependencies == ()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(MetadataError, match="not found"):
        load_metadata(tmp_path / "does_not_exist.toml")


def test_malformed_toml(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool
        name = "bad"
    """)
    with pytest.raises(MetadataError, match="parse"):
        load_metadata(toml)


def test_missing_plugin_table(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        name = "hello"
        version = "1.0.0"
    """)
    with pytest.raises(MetadataError, match=r"\[tool\.mde\.plugin\]"):
        load_metadata(toml)


def test_missing_name(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        version = "1.0.0"
    """)
    with pytest.raises(MetadataError, match="name"):
        load_metadata(toml)


def test_missing_version(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "hello"
    """)
    with pytest.raises(MetadataError, match="version"):
        load_metadata(toml)


def test_name_wrong_type(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = 123
        version = "1.0"
    """)
    with pytest.raises(MetadataError, match="name"):
        load_metadata(toml)


def test_version_wrong_type(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "x"
        version = 1
    """)
    with pytest.raises(MetadataError, match="version"):
        load_metadata(toml)


def test_dependencies_wrong_type(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "x"
        version = "0.1"

        [tool.mde.plugin.dependencies]
        python = "requests"
    """)
    with pytest.raises(MetadataError, match="dependencies"):
        load_metadata(toml)


def test_dependency_item_wrong_type(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "x"
        version = "0.1"

        [tool.mde.plugin.dependencies]
        python = ["ok", 42]
    """)
    with pytest.raises(MetadataError, match="dependencies"):
        load_metadata(toml)


def test_empty_name_rejected(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = ""
        version = "0.1"
    """)
    with pytest.raises(MetadataError, match="name"):
        load_metadata(toml)


# ---------------------------------------------------------------------------
# API version helpers
# ---------------------------------------------------------------------------


def test_api_version_defaults_to_zero_when_omitted(tmp_path: Path) -> None:
    """Pre-1.0: declaring api version is optional, defaults to '0' (pre-stable)."""
    toml = _write_toml(tmp_path, """
        [tool.mde.plugin]
        name = "x"
        version = "0.1"
    """)
    m = load_metadata(toml)
    assert m.mde_api_version == "0"

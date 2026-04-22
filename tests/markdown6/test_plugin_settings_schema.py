"""Tests for the schema-driven user-facing plugin config layer.

A plugin declares a list of :class:`Field` records describing each
configurable setting (key, type, label, default, optional choices /
min / max / widget hint). Registering the schema lets the framework
auto-render a ``Configure…`` dialog from Settings → Plugins, with no
plugin Qt code required.

Storage routes through the same :func:`plugin_settings(id)` façade
used for programmatic plugin storage - the schema is just metadata
about which keys are user-editable.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    yield
    plugin_api._REGISTRY.clear()


# ---------------------------------------------------------------------------
# Field dataclass
# ---------------------------------------------------------------------------


def test_field_minimal_construction() -> None:
    f = plugin_api.Field(key="foo", label="Foo")
    assert f.key == "foo"
    assert f.label == "Foo"
    assert f.type is str
    assert f.default is None
    assert f.choices is None
    assert f.min is None
    assert f.max is None
    assert f.widget == ""


def test_field_full_construction() -> None:
    f = plugin_api.Field(
        key="model", label="Model", type=str,
        default="gpt-4", choices=("gpt-4", "gpt-3.5"),
        description="Which model to use",
    )
    assert f.choices == ("gpt-4", "gpt-3.5")
    assert f.description == "Which model to use"


def test_field_int_with_bounds() -> None:
    f = plugin_api.Field(key="n", label="N", type=int, default=10, min=1, max=100)
    assert f.type is int
    assert f.min == 1
    assert f.max == 100


# ---------------------------------------------------------------------------
# Schema registration
# ---------------------------------------------------------------------------


def test_register_settings_schema_stores_record() -> None:
    fields = [
        plugin_api.Field("api_key", "API Key"),
        plugin_api.Field("max_n", "Max", type=int, default=10),
    ]
    plugin_api.register_settings_schema(fields=fields, plugin_id="myplug")

    schema = plugin_api._REGISTRY.get_settings_schema("myplug")
    assert schema is not None
    assert schema.plugin_id == "myplug"
    assert len(schema.fields) == 2
    assert schema.fields[0].key == "api_key"


def test_register_settings_schema_auto_detects_plugin_id_from_loader(tmp_path: Path) -> None:
    """When called inside a plugin's import (loader sets _CURRENT_PLUGIN_NAME),
    the schema's plugin_id is taken from that context."""
    (tmp_path / "schemap").mkdir()
    (tmp_path / "schemap" / "schemap.toml").write_text(textwrap.dedent("""
        [tool.mde.plugin]
        name = "schemap"
        version = "1.0"
    """).lstrip(), encoding="utf-8")
    (tmp_path / "schemap" / "schemap.py").write_text(textwrap.dedent("""
        from markdown_editor.markdown6.plugins.api import register_settings_schema, Field
        register_settings_schema(fields=[
            Field("name", "Name", default="World"),
        ])
    """), encoding="utf-8")
    load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    schema = plugin_api._REGISTRY.get_settings_schema("schemap")
    assert schema is not None
    assert schema.plugin_id == "schemap"


def test_register_settings_schema_requires_plugin_id_outside_loader() -> None:
    """Outside a loader-managed import, the auto-detect context is empty
    and explicit plugin_id is required."""
    with pytest.raises(ValueError, match="plugin_id"):
        plugin_api.register_settings_schema(
            fields=[plugin_api.Field("x", "X")],
        )


def test_register_settings_schema_rejects_empty_fields() -> None:
    with pytest.raises(ValueError, match="fields"):
        plugin_api.register_settings_schema(fields=[], plugin_id="p")


def test_get_settings_schema_returns_none_for_unregistered() -> None:
    assert plugin_api._REGISTRY.get_settings_schema("never") is None


def test_register_settings_schema_duplicate_plugin_id_raises() -> None:
    plugin_api.register_settings_schema(
        fields=[plugin_api.Field("a", "A")], plugin_id="dup",
    )
    with pytest.raises(ValueError, match="dup"):
        plugin_api.register_settings_schema(
            fields=[plugin_api.Field("b", "B")], plugin_id="dup",
        )


# ---------------------------------------------------------------------------
# Field type coverage - supported types only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_type", [str, int, float, bool])
def test_supported_field_types(field_type: type) -> None:
    f = plugin_api.Field(key="x", label="X", type=field_type, default=field_type())
    plugin_api.register_settings_schema(fields=[f], plugin_id=f"p_{field_type.__name__}")


def test_unsupported_field_type_rejected() -> None:
    """Catch typos and unsupported types at registration time so the
    plugin author sees the failure on import, not when the user opens
    the Configure dialog."""
    with pytest.raises(ValueError, match="type"):
        plugin_api.register_settings_schema(
            fields=[plugin_api.Field("x", "X", type=list, default=[])],
            plugin_id="bad",
        )


# ---------------------------------------------------------------------------
# Shim re-exports
# ---------------------------------------------------------------------------


def test_shim_exports_field_and_register_settings_schema() -> None:
    import markdown_editor.plugins as shim
    assert hasattr(shim, "Field")
    assert hasattr(shim, "register_settings_schema")
    assert "Field" in shim.__all__
    assert "register_settings_schema" in shim.__all__

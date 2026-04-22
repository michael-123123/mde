"""Tests for per-plugin scoped settings.

Plugins get their own namespaced storage via ``ctx.plugin_settings(id)``,
which returns a dict-like façade backed by the main settings file under
``plugins.<id>.<key>``. Two plugins can use the same key name without
collision; their values are isolated by namespace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import init_app_context


@pytest.fixture
def ctx():
    """Fresh ephemeral AppContext, isolated per-test."""
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


@pytest.fixture
def persistent_ctx(tmp_path: Path):
    """Non-ephemeral AppContext rooted at tmp_path so we can verify
    persistence across reload."""
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(config_dir=tmp_path, ephemeral=False)
    yield c
    ctx_mod._app_context = None


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


def test_set_then_get_roundtrip(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    s["api_key"] = "sk-abc"
    assert s["api_key"] == "sk-abc"


def test_get_with_default_for_missing_key(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    assert s.get("nope", "fallback") == "fallback"
    assert s.get("nope") is None


def test_contains_check(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    assert "x" not in s
    s["x"] = 1
    assert "x" in s


def test_getitem_missing_raises_keyerror(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    with pytest.raises(KeyError):
        _ = s["never_set"]


def test_delete(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    s["x"] = 1
    del s["x"]
    assert "x" not in s
    assert s.get("x") is None


def test_delete_missing_raises_keyerror(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    with pytest.raises(KeyError):
        del s["never_set"]


# ---------------------------------------------------------------------------
# Type preservation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [
    "string",
    42,
    3.14,
    True,
    False,
    None,
    [1, 2, 3],
    {"nested": "dict", "with": [1, 2]},
])
def test_type_round_trip(ctx, value) -> None:
    s = ctx.plugin_settings("myplug")
    s["key"] = value
    assert s["key"] == value


# ---------------------------------------------------------------------------
# Namespace isolation
# ---------------------------------------------------------------------------


def test_two_plugins_have_isolated_namespaces(ctx) -> None:
    a = ctx.plugin_settings("plugin_a")
    b = ctx.plugin_settings("plugin_b")
    a["shared_key"] = "from_a"
    b["shared_key"] = "from_b"
    assert a["shared_key"] == "from_a"
    assert b["shared_key"] == "from_b"


def test_plugin_settings_does_not_leak_into_main_settings(ctx) -> None:
    """Plugin keys must not collide with regular ctx.get() keys."""
    s = ctx.plugin_settings("myplug")
    s["editor.font_size"] = "definitely_not_a_number"
    # The real editor.font_size setting is unaffected
    assert isinstance(ctx.get("editor.font_size"), int)


def test_main_settings_do_not_leak_into_plugin_settings(ctx) -> None:
    s = ctx.plugin_settings("myplug")
    # editor.font_size exists in the main settings; the plugin facade
    # must not see it as "its own" value.
    assert "editor.font_size" not in s
    assert s.get("editor.font_size", "DEFAULT") == "DEFAULT"


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------


def test_iter_yields_only_keys_for_this_plugin(ctx) -> None:
    a = ctx.plugin_settings("plugin_a")
    b = ctx.plugin_settings("plugin_b")
    a["x"] = 1
    a["y"] = 2
    b["z"] = 3
    assert set(a) == {"x", "y"}
    assert set(b) == {"z"}


def test_keys_items(ctx) -> None:
    s = ctx.plugin_settings("p")
    s["foo"] = 10
    s["bar"] = "hello"
    assert set(s.keys()) == {"foo", "bar"}
    assert dict(s.items()) == {"foo": 10, "bar": "hello"}


def test_len(ctx) -> None:
    s = ctx.plugin_settings("p")
    assert len(s) == 0
    s["a"] = 1
    s["b"] = 2
    assert len(s) == 2


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_settings_persist_across_appcontext_reload(persistent_ctx, tmp_path: Path) -> None:
    s = persistent_ctx.plugin_settings("myplug")
    s["api_key"] = "sk-xyz"
    s["count"] = 7

    # Reset the global and re-init pointing at the same config dir
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    ctx2 = init_app_context(config_dir=tmp_path, ephemeral=False)

    s2 = ctx2.plugin_settings("myplug")
    assert s2["api_key"] == "sk-xyz"
    assert s2["count"] == 7


# ---------------------------------------------------------------------------
# Validation: plugin id must be valid
# ---------------------------------------------------------------------------


def test_empty_plugin_id_rejected(ctx) -> None:
    with pytest.raises(ValueError, match="plugin_id"):
        ctx.plugin_settings("")


def test_plugin_id_with_dot_rejected(ctx) -> None:
    """Plugin ids must not contain '.' - that's our namespace separator
    and would let one plugin write into another's namespace."""
    with pytest.raises(ValueError, match="\\."):
        ctx.plugin_settings("foo.bar")

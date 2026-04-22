"""End-to-end "broken plugin" failure-mode tests.

The individual failure modes are unit-tested in their respective
modules (loader, registry, signals, etc.). This file walks the full
chain — loader → AppContext.set_plugins → PluginsSettingsPage row →
Info dialog — for each failure mode so a regression in any link
surfaces here. Also covers a few cross-cutting cases that don't fit
cleanly into any single per-module test:

* ``plugins.disabled`` referencing a name that's no longer on disk.
* TOML ``[tool.mde.plugin].name`` not matching the plugin directory name.
* Two healthy plugins competing for the same fence / exporter id.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugin_info_dialog import (
    PluginInfoDialog,
)
from markdown_editor.markdown6.components.plugins_page import PluginsSettingsPage
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource, PluginStatus


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)
    yield
    plugin_api._REGISTRY.clear()
    plugin_api._set_active_document_provider(lambda: None)


def _make_plugin(
    root: Path, name: str, *,
    py_body: str = "# clean\n",
    toml_body: str | None = None,
) -> Path:
    d = root / name
    d.mkdir(parents=True)
    if toml_body is None:
        toml_body = textwrap.dedent(f"""
            [tool.mde.plugin]
            name = "{name}"
            version = "1.0"
            description = "test fixture {name}"
        """).lstrip()
    (d / f"{name}.toml").write_text(toml_body, encoding="utf-8")
    (d / f"{name}.py").write_text(py_body, encoding="utf-8")
    return d


def _e2e_settings_row(qtbot, ctx, plugins) -> tuple:
    """Helper: install the loader's output into ctx and render the page.

    Returns (page, row) for the first (and usually only) plugin."""
    ctx.set_plugins(plugins)
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    return page, page.row_for(plugins[0].name)


# ---------------------------------------------------------------------------
# 1. End-to-end broken plugin sad path — each load-failure mode walks the
# full chain (loader → settings page → Info dialog) without crashing.
# ---------------------------------------------------------------------------


def test_e2e_plugin_import_raises(qtbot, ctx, tmp_path: Path) -> None:
    _make_plugin(tmp_path, "kaboom", py_body='raise RuntimeError("intentional bad import")\n')
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    assert p.status is PluginStatus.LOAD_FAILURE
    assert "intentional bad import" in p.detail

    page, row = _e2e_settings_row(qtbot, ctx, [p])
    assert row.checkbox.isEnabled() is False
    assert "Error" in row.status_label.text()

    info = PluginInfoDialog(p)
    qtbot.addWidget(info)
    all_text = "\n".join(lbl.text() for lbl in info.findChildren(QLabel))
    assert "intentional bad import" in all_text


def test_e2e_plugin_missing_dependency(qtbot, ctx, tmp_path: Path) -> None:
    _make_plugin(
        tmp_path, "needsmissing",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "needsmissing"
            version = "1.0"

            [tool.mde.plugin.dependencies]
            python = ["definitely_not_a_real_module_xyz123"]
        """).lstrip(),
    )
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    assert p.status is PluginStatus.MISSING_DEPS
    assert "definitely_not_a_real_module_xyz123" in p.detail
    assert p.missing_deps == ("definitely_not_a_real_module_xyz123",)

    _, row = _e2e_settings_row(qtbot, ctx, [p])
    assert row.checkbox.isEnabled() is False
    assert "missing" in row.status_label.text().lower()


def test_e2e_plugin_bad_toml(qtbot, ctx, tmp_path: Path) -> None:
    _make_plugin(
        tmp_path, "badmeta",
        toml_body='[tool\nname = "badmeta"\n',   # malformed TOML (unclosed table)
    )
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    assert p.status is PluginStatus.METADATA_ERROR
    assert p.metadata is None

    _, row = _e2e_settings_row(qtbot, ctx, [p])
    assert row.checkbox.isEnabled() is False


def test_e2e_plugin_api_version_mismatch(qtbot, ctx, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markdown_editor.markdown6.plugins.loader.MDE_API_VERSION", "2",
    )
    _make_plugin(
        tmp_path, "oldapi",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "oldapi"
            version = "1.0"
            mde_api_version = "1"
        """).lstrip(),
    )
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())

    assert p.status is PluginStatus.API_MISMATCH
    _, row = _e2e_settings_row(qtbot, ctx, [p])
    assert row.checkbox.isEnabled() is False
    assert "api" in row.status_label.text().lower() or \
           "version" in row.status_label.text().lower()


def test_e2e_one_broken_one_healthy_coexist(qtbot, ctx, tmp_path: Path) -> None:
    """A single broken plugin must not prevent healthy plugins from loading."""
    _make_plugin(tmp_path, "kaboom",
                 py_body='raise RuntimeError("bad")\n')
    _make_plugin(tmp_path, "ok",
                 py_body='# clean module\n')

    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    by_name = {p.name: p for p in plugins}

    assert by_name["kaboom"].status is PluginStatus.LOAD_FAILURE
    assert by_name["ok"].status is PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# 2. plugins.disabled referencing a name that's no longer on disk
# ---------------------------------------------------------------------------


def test_orphan_disabled_name_does_not_crash(tmp_path: Path) -> None:
    """User had plugin X installed and disabled; later removed it from
    disk. The orphan name in plugins.disabled should be silently
    ignored — not crash, not error any other plugin."""
    _make_plugin(tmp_path, "still_here")
    plugins = load_all(
        [(tmp_path, PluginSource.USER)],
        user_disabled={"still_here", "removed_long_ago", "another_orphan"},
    )
    by_name = {p.name: p for p in plugins}
    # The plugin that exists is correctly marked disabled
    assert by_name["still_here"].status is PluginStatus.DISABLED_BY_USER
    # The orphans are simply absent — no entries created for them
    assert "removed_long_ago" not in by_name
    assert "another_orphan" not in by_name


def test_orphan_disabled_does_not_block_healthy_plugin(tmp_path: Path) -> None:
    _make_plugin(tmp_path, "alive")
    plugins = load_all(
        [(tmp_path, PluginSource.USER)],
        user_disabled={"ghost_a", "ghost_b"},
    )
    [p] = plugins
    assert p.name == "alive"
    assert p.status is PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# 3. TOML [tool.mde.plugin].name vs directory name mismatch
# ---------------------------------------------------------------------------


def test_toml_name_must_match_directory_name(tmp_path: Path) -> None:
    """The TOML [tool.mde.plugin].name field must match the directory name —
    otherwise plugin authors can publish a plugin whose internal name
    silently disagrees with how it's referenced in plugins.disabled,
    plugin_settings, etc."""
    _make_plugin(
        tmp_path, "real_dir",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "different_name"
            version = "1.0"
        """).lstrip(),
    )
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    assert p.status is PluginStatus.METADATA_ERROR
    assert "different_name" in p.detail
    assert "real_dir" in p.detail


def test_toml_name_matching_directory_name_loads_clean(tmp_path: Path) -> None:
    """Sanity baseline: when names match, the plugin loads as ENABLED."""
    _make_plugin(tmp_path, "matching")
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    assert p.status is PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# 4. Two plugins competing for the same fence / exporter id
# ---------------------------------------------------------------------------


def test_two_plugins_same_fence_name_second_load_fails(tmp_path: Path) -> None:
    """First plugin claims fence ``planuml``; second plugin claims it
    too. Second plugin's import fails with LOAD_FAILURE and the first
    keeps its registration intact."""
    _make_plugin(
        tmp_path, "first_fence_owner",
        py_body=textwrap.dedent("""
            from markdown_editor.plugins import register_fence
            @register_fence("plantuml")
            def render(src):
                return f"<svg>{src}</svg>"
        """),
    )
    _make_plugin(
        tmp_path, "second_fence_thief",
        py_body=textwrap.dedent("""
            from markdown_editor.plugins import register_fence
            @register_fence("plantuml")
            def render(src):
                return "<other/>"
        """),
    )
    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    by_name = {p.name: p for p in plugins}

    # First-installed (alphabetical) wins; second fails to load
    assert by_name["first_fence_owner"].status is PluginStatus.ENABLED
    assert by_name["second_fence_thief"].status is PluginStatus.LOAD_FAILURE
    assert "plantuml" in by_name["second_fence_thief"].detail

    # Registry has exactly one fence with that name (the first plugin's)
    [fence] = [f for f in plugin_api._REGISTRY.fences() if f.name == "plantuml"]
    assert fence.plugin_name == "first_fence_owner"


def test_two_plugins_same_exporter_id_second_load_fails(tmp_path: Path) -> None:
    """Exporter ids share the global plugin id namespace, so the second
    plugin's exporter registration raises ValueError → LOAD_FAILURE."""
    _make_plugin(
        tmp_path, "first_exporter_owner",
        py_body=textwrap.dedent("""
            from markdown_editor.plugins import register_exporter
            @register_exporter(id="jekyll", label="Jekyll", extensions=["md"])
            def fn(doc, path):
                pass
        """),
    )
    _make_plugin(
        tmp_path, "second_exporter_thief",
        py_body=textwrap.dedent("""
            from markdown_editor.plugins import register_exporter
            @register_exporter(id="jekyll", label="Jekyll Stolen", extensions=["md"])
            def fn(doc, path):
                pass
        """),
    )
    plugins = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    by_name = {p.name: p for p in plugins}

    assert by_name["first_exporter_owner"].status is PluginStatus.ENABLED
    assert by_name["second_exporter_thief"].status is PluginStatus.LOAD_FAILURE
    assert "jekyll" in by_name["second_exporter_thief"].detail.lower()

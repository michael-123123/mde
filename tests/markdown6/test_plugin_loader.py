"""Tests for plugin discovery + loading (plugins/loader.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from markdown_editor.markdown6.plugins.loader import (
    PluginSource,
    discover_plugins,
    load_all,
    load_plugin,
)
from markdown_editor.markdown6.plugins.plugin import Plugin, PluginStatus

# ---------------------------------------------------------------------------
# Fixture plugin construction helpers
# ---------------------------------------------------------------------------


def _make_plugin_dir(
    root: Path,
    name: str,
    *,
    toml_body: str | None = None,
    py_body: str | None = None,
    toml_filename: str | None = None,
    py_filename: str | None = None,
) -> Path:
    """Create a plugin directory <root>/<name>/ with sensible defaults.

    Overrides let individual tests break the structure in targeted ways.
    """
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    if toml_filename is None:
        toml_filename = f"{name}.toml"
    if py_filename is None:
        py_filename = f"{name}.py"
    if toml_body is None:
        toml_body = textwrap.dedent(f"""
            [tool.mde.plugin]
            name = "{name}"
            version = "1.0"
        """).lstrip()
    if py_body is None:
        py_body = "# empty plugin\n"
    (plugin_dir / toml_filename).write_text(toml_body, encoding="utf-8")
    (plugin_dir / py_filename).write_text(py_body, encoding="utf-8")
    return plugin_dir


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_empty_root(tmp_path: Path) -> None:
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert found == []


def test_discovery_nonexistent_root_is_skipped(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    found = discover_plugins([(missing, PluginSource.USER)])
    assert found == []


def test_discovery_finds_plugin(tmp_path: Path) -> None:
    _make_plugin_dir(tmp_path, "hello")
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert len(found) == 1
    p = found[0]
    assert p.name == "hello"
    assert p.source == PluginSource.USER
    assert p.directory == tmp_path / "hello"


def test_discovery_finds_multiple_and_tags_source(tmp_path: Path) -> None:
    builtin_root = tmp_path / "builtin"
    user_root = tmp_path / "user"
    builtin_root.mkdir()
    user_root.mkdir()
    _make_plugin_dir(builtin_root, "a")
    _make_plugin_dir(user_root, "b")
    _make_plugin_dir(user_root, "c")
    found = discover_plugins([
        (builtin_root, PluginSource.BUILTIN),
        (user_root, PluginSource.USER),
    ])
    by_name = {p.name: p for p in found}
    assert set(by_name) == {"a", "b", "c"}
    assert by_name["a"].source == PluginSource.BUILTIN
    assert by_name["b"].source == PluginSource.USER
    assert by_name["c"].source == PluginSource.USER


def test_discovery_skips_non_directory_entries(tmp_path: Path) -> None:
    _make_plugin_dir(tmp_path, "real")
    (tmp_path / "README.md").write_text("not a plugin", encoding="utf-8")
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    names = [p.name for p in found]
    assert names == ["real"]


def test_discovery_rejects_dir_without_py_file(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    (d / "broken.toml").write_text('[tool.mde.plugin]\nname="x"\nversion="0.1"\n')
    # No broken.py
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert len(found) == 1
    p = found[0]
    assert p.status == PluginStatus.LOAD_FAILURE
    assert "broken.py" in p.detail


def test_discovery_rejects_dir_without_toml_file(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    (d / "broken.py").write_text("# py only\n")
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert len(found) == 1
    assert found[0].status == PluginStatus.METADATA_ERROR
    assert "broken.toml" in found[0].detail


def test_discovery_rejects_mismatched_filename(tmp_path: Path) -> None:
    _make_plugin_dir(
        tmp_path, "mymod",
        py_filename="wrongname.py",
    )
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert len(found) == 1
    assert found[0].status == PluginStatus.LOAD_FAILURE


# ---------------------------------------------------------------------------
# Metadata failure during discovery
# ---------------------------------------------------------------------------


def test_discovery_records_metadata_error(tmp_path: Path) -> None:
    _make_plugin_dir(
        tmp_path,
        "bad_meta",
        toml_body='[tool\nname = "bad"\n',   # malformed TOML (unclosed table)
    )
    found = discover_plugins([(tmp_path, PluginSource.USER)])
    assert len(found) == 1
    p = found[0]
    assert p.status == PluginStatus.METADATA_ERROR
    assert p.metadata is None
    assert p.detail  # non-empty human-readable reason


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------


def test_load_plugin_missing_python_dep(tmp_path: Path) -> None:
    _make_plugin_dir(
        tmp_path,
        "needs_missing",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "needs_missing"
            version = "0.1"

            [tool.mde.plugin.dependencies]
            python = ["this_module_definitely_does_not_exist_xyz"]
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    assert p.status == PluginStatus.ENABLED   # discovery didn't disable yet
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.MISSING_DEPS
    assert "this_module_definitely_does_not_exist_xyz" in p.detail
    assert p.module is None


def test_load_plugin_present_dep_ok(tmp_path: Path) -> None:
    _make_plugin_dir(
        tmp_path,
        "needs_os",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "needs_os"
            version = "0.1"

            [tool.mde.plugin.dependencies]
            python = ["os", "sys"]
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.ENABLED
    assert p.module is not None


def test_load_plugin_version_spec_tolerated(tmp_path: Path) -> None:
    """Pip-style requirement strings like 'os>=1.0' should still work.

    Only the module-name part is checked for importability; the version
    spec is currently advisory (honouring it is future work).
    """
    _make_plugin_dir(
        tmp_path,
        "needs_versioned",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "needs_versioned"
            version = "0.1"

            [tool.mde.plugin.dependencies]
            python = ["os >= 1.0", "sys==1.0"]
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# Import failure
# ---------------------------------------------------------------------------


def test_load_plugin_import_raises(tmp_path: Path) -> None:
    _make_plugin_dir(
        tmp_path,
        "kaboom",
        py_body='raise RuntimeError("oh no")\n',
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.LOAD_FAILURE
    assert "oh no" in p.detail
    assert p.module is None


# ---------------------------------------------------------------------------
# User disable
# ---------------------------------------------------------------------------


def test_load_plugin_user_disabled_still_imports(tmp_path: Path) -> None:
    """A disabled plugin is imported like any other - but flagged
    DISABLED_BY_USER so the editor hides its actions. Keeping it in
    memory is what makes live re-enable possible without a restart.
    """
    _make_plugin_dir(
        tmp_path,
        "disme",
        py_body='MARKER = "imported"\n',
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled={"disme"})
    assert p.status == PluginStatus.DISABLED_BY_USER
    assert p.module is not None                  # imported despite being disabled
    assert getattr(p.module, "MARKER") == "imported"


def test_load_plugin_user_disabled_but_raising_becomes_load_failure(tmp_path: Path) -> None:
    """If a disabled plugin's import raises, user_disabled doesn't shield
    the user from the error - they still see it in Settings → Plugins
    so they know something's wrong with that plugin."""
    _make_plugin_dir(
        tmp_path,
        "broken_disme",
        py_body='raise RuntimeError("oh no")\n',
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled={"broken_disme"})
    assert p.status == PluginStatus.LOAD_FAILURE
    assert "oh no" in p.detail


def test_load_plugin_user_disabled_builtin(tmp_path: Path) -> None:
    """Users can disable builtin plugins too."""
    _make_plugin_dir(tmp_path, "bundled")
    [p] = discover_plugins([(tmp_path, PluginSource.BUILTIN)])
    load_plugin(p, user_disabled={"bundled"})
    assert p.status == PluginStatus.DISABLED_BY_USER


# ---------------------------------------------------------------------------
# API version mismatch
# ---------------------------------------------------------------------------


def test_api_version_mismatch_post_1_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Post-1.0, mismatched major version is a fatal error."""
    monkeypatch.setattr(
        "markdown_editor.markdown6.plugins.loader.MDE_API_VERSION", "2"
    )
    _make_plugin_dir(
        tmp_path,
        "oldplugin",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "oldplugin"
            version = "1.0"
            mde_api_version = "1"
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.API_MISMATCH
    assert "api" in p.detail.lower() or "version" in p.detail.lower()


def test_api_version_match_post_1_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markdown_editor.markdown6.plugins.loader.MDE_API_VERSION", "2"
    )
    _make_plugin_dir(
        tmp_path,
        "ok",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "ok"
            version = "1.0"
            mde_api_version = "2"
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.ENABLED


def test_api_version_pre_1_0_never_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-1.0 (API_VERSION == '0'), any declared api version is accepted."""
    monkeypatch.setattr(
        "markdown_editor.markdown6.plugins.loader.MDE_API_VERSION", "0"
    )
    _make_plugin_dir(
        tmp_path,
        "any",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "any"
            version = "1.0"
            mde_api_version = "42"
        """).lstrip(),
    )
    [p] = discover_plugins([(tmp_path, PluginSource.USER)])
    load_plugin(p, user_disabled=set())
    assert p.status == PluginStatus.ENABLED


# ---------------------------------------------------------------------------
# load_all integration
# ---------------------------------------------------------------------------


def test_load_all_combines_discover_and_load(tmp_path: Path) -> None:
    _make_plugin_dir(tmp_path, "good")
    _make_plugin_dir(
        tmp_path,
        "bad",
        py_body='raise ImportError("fail")\n',
    )
    _make_plugin_dir(
        tmp_path,
        "offlimits",
        toml_body=textwrap.dedent("""
            [tool.mde.plugin]
            name = "offlimits"
            version = "0.1"

            [tool.mde.plugin.dependencies]
            python = ["nonexistent_xyz_module"]
        """).lstrip(),
    )
    plugins = load_all(
        [(tmp_path, PluginSource.USER)],
        user_disabled=set(),
    )
    by_name = {p.name: p for p in plugins}
    assert by_name["good"].status == PluginStatus.ENABLED
    assert by_name["bad"].status == PluginStatus.LOAD_FAILURE
    assert by_name["offlimits"].status == PluginStatus.MISSING_DEPS
    # load_all never raises - errors only appear as statuses
    assert all(isinstance(p, Plugin) for p in plugins)


def test_load_all_disabled_clean_plugin_keeps_module(tmp_path: Path) -> None:
    """User-disabled plugins with clean imports stay loaded in memory
    - that's the prerequisite for live re-enable. Only their status
    becomes DISABLED_BY_USER.
    """
    _make_plugin_dir(tmp_path, "nope", py_body='# cleanly imports\n')
    plugins = load_all(
        [(tmp_path, PluginSource.USER)],
        user_disabled={"nope"},
    )
    assert plugins[0].status == PluginStatus.DISABLED_BY_USER
    assert plugins[0].module is not None

"""Tests for the per-plugin Info button + dialog in Settings → Plugins.

Each plugin row gets an Info (ℹ) button that opens a modal showing:

* Metadata: name, version, source (builtin/user), author
* Status + detail (especially useful for errored plugins)
* Description from the TOML
* README.md contents (if the plugin shipped one)

Plugin layout per the plan:
    <name>/
      <name>.py
      <name>.toml
      README.md       # optional
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugin_info_dialog import (
    PluginInfoDialog,
)
from markdown_editor.markdown6.components.plugins_page import (
    PluginsSettingsPage,
)
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.metadata import PluginMetadata
from markdown_editor.markdown6.plugins.plugin import (
    Plugin,
    PluginSource,
    PluginStatus,
)


def _visible_text(widget: QWidget) -> str:
    """All QLabel text in the widget tree, concatenated. Mirrors what a
    reader of the dialog would see."""
    return "\n".join(lbl.text() for lbl in widget.findChildren(QLabel))


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


def _make_plugin_dir(tmp_path: Path, name: str, *, readme: str | None = None) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / f"{name}.toml").write_text(textwrap.dedent(f"""
        [tool.mde.plugin]
        name = "{name}"
        version = "1.0"
        description = "A test plugin called {name}"
    """).lstrip(), encoding="utf-8")
    (d / f"{name}.py").write_text("# empty\n", encoding="utf-8")
    if readme is not None:
        (d / "README.md").write_text(readme, encoding="utf-8")
    return d


def _plugin_record(
    name: str = "p", *, status: PluginStatus = PluginStatus.ENABLED,
    description: str = "desc", detail: str = "",
    source: PluginSource = PluginSource.BUILTIN,
    directory: Path | None = None, version: str = "1.0", author: str = "",
) -> Plugin:
    return Plugin(
        name=name,
        source=source,
        directory=directory or Path(f"/fake/{name}"),
        metadata=PluginMetadata(
            name=name, version=version, description=description, author=author,
        ),
        status=status,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# README discovery
# ---------------------------------------------------------------------------


def test_loader_records_readme_path_when_present(tmp_path: Path) -> None:
    _make_plugin_dir(tmp_path, "withreadme", readme="# Hello\nThis is a README.")
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    assert p.readme_path is not None
    assert p.readme_path.name == "README.md"
    assert p.readme_path.read_text().startswith("# Hello")


def test_loader_leaves_readme_path_none_when_absent(tmp_path: Path) -> None:
    _make_plugin_dir(tmp_path, "noreadme")
    [p] = load_all([(tmp_path, PluginSource.USER)], user_disabled=set())
    assert p.readme_path is None


# ---------------------------------------------------------------------------
# Info dialog rendering
# ---------------------------------------------------------------------------


def test_info_dialog_shows_metadata(qtbot, ctx) -> None:
    p = _plugin_record(
        "test_plug", description="Friendly description",
        version="2.5", author="Someone",
    )
    dialog = PluginInfoDialog(p)
    qtbot.addWidget(dialog)
    text = _visible_text(dialog)
    assert "test_plug" in text
    assert "2.5" in text
    assert "Someone" in text
    assert "Friendly description" in text


def test_info_dialog_shows_status_and_detail_for_errored(qtbot, ctx) -> None:
    p = _plugin_record(
        "broken",
        status=PluginStatus.LOAD_FAILURE,
        detail="ImportError: missing module xyz",
    )
    dialog = PluginInfoDialog(p)
    qtbot.addWidget(dialog)
    text = _visible_text(dialog)
    assert "Error" in text or "load_failure" in text or "Failure" in text
    assert "missing module xyz" in text


def test_info_dialog_shows_readme_when_present(qtbot, ctx, tmp_path: Path) -> None:
    plugin_dir = _make_plugin_dir(tmp_path, "withreadme", readme="# README\n\nHello!")
    p = _plugin_record(
        "withreadme", directory=plugin_dir,
    )
    p.readme_path = plugin_dir / "README.md"

    dialog = PluginInfoDialog(p)
    qtbot.addWidget(dialog)
    readme = dialog.readme_text()
    assert "Hello!" in readme


def test_info_dialog_no_readme_section_when_absent(qtbot, ctx) -> None:
    p = _plugin_record("plain")
    p.readme_path = None
    dialog = PluginInfoDialog(p)
    qtbot.addWidget(dialog)
    assert dialog.has_readme() is False


def test_info_dialog_shows_source_label(qtbot, ctx) -> None:
    p_b = _plugin_record("a", source=PluginSource.BUILTIN)
    p_u = _plugin_record("b", source=PluginSource.USER)
    d_b = PluginInfoDialog(p_b)
    d_u = PluginInfoDialog(p_u)
    qtbot.addWidget(d_b)
    qtbot.addWidget(d_u)
    assert "builtin" in _visible_text(d_b).lower()
    assert "user" in _visible_text(d_u).lower()


# ---------------------------------------------------------------------------
# PluginsSettingsPage row gets an Info button
# ---------------------------------------------------------------------------


def test_settings_page_row_has_info_button(qtbot, ctx) -> None:
    ctx.set_plugins([_plugin_record("hi")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("hi")
    assert row.info_button is not None
    assert row.info_button.isEnabled() is True


def test_info_button_present_for_errored_plugin_too(qtbot, ctx) -> None:
    """Errored plugins especially benefit from the info dialog (it shows
    the failure detail in a more readable format than the inline label)."""
    ctx.set_plugins([_plugin_record(
        "broken", status=PluginStatus.LOAD_FAILURE, detail="big stack trace…",
    )])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("broken")
    assert row.info_button is not None
    assert row.info_button.isEnabled() is True

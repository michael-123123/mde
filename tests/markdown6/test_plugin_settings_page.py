"""Tests for the Settings → Plugins page widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugins_page import (
    PluginsSettingsPage,
)
from markdown_editor.markdown6.plugins.metadata import PluginMetadata
from markdown_editor.markdown6.plugins.plugin import (
    Plugin,
    PluginSource,
    PluginStatus,
)


def _plugin(
    name: str,
    *,
    status: PluginStatus = PluginStatus.ENABLED,
    source: PluginSource = PluginSource.BUILTIN,
    version: str = "1.0",
    description: str = "",
    detail: str = "",
) -> Plugin:
    return Plugin(
        name=name,
        source=source,
        directory=Path("/fake") / name,
        metadata=PluginMetadata(
            name=name, version=version, description=description,
        ),
        status=status,
        detail=detail,
    )


@pytest.fixture
def ctx():
    import markdown_editor.markdown6.app_context as ctx_mod
    ctx_mod._app_context = None
    c = init_app_context(ephemeral=True)
    yield c
    ctx_mod._app_context = None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_empty_plugins_list_renders_message(qtbot, ctx) -> None:
    ctx.set_plugins([])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.row_count() == 0
    # Should render a "no plugins" hint somewhere in the page
    assert "no plugins" in page.empty_message().lower()


def test_one_plugin_one_row(qtbot, ctx) -> None:
    ctx.set_plugins([_plugin("hello")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.row_count() == 1


def test_multiple_plugins_multiple_rows(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("a", source=PluginSource.BUILTIN),
        _plugin("b", source=PluginSource.USER),
        _plugin("c", source=PluginSource.USER),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.row_count() == 3


# ---------------------------------------------------------------------------
# Row contents
# ---------------------------------------------------------------------------


def test_row_shows_name_version_source(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("hello", version="2.5", source=PluginSource.USER),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("hello")
    assert row is not None
    assert "hello" in row.name_label.text()
    assert "2.5" in row.version_label.text()
    assert "user" in row.source_label.text().lower()


def test_row_shows_builtin_badge(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("built", source=PluginSource.BUILTIN),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("built")
    assert "builtin" in row.source_label.text().lower()


def test_row_shows_description(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("hi", description="A friendly plugin"),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("hi")
    assert "A friendly plugin" in row.detail_label.text()


# ---------------------------------------------------------------------------
# Status-driven checkbox state
# ---------------------------------------------------------------------------


def test_enabled_plugin_checkbox_checked_and_enabled(qtbot, ctx) -> None:
    ctx.set_plugins([_plugin("a", status=PluginStatus.ENABLED)])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("a")
    assert row.checkbox.isChecked() is True
    assert row.checkbox.isEnabled() is True


def test_user_disabled_plugin_checkbox_unchecked_and_enabled(qtbot, ctx) -> None:
    """Checkbox state is driven by the live plugins.disabled setting,
    not by the captured Plugin.status — that's what keeps the checkbox
    in sync with the menu when Settings is re-opened after a toggle."""
    ctx.set_plugins([_plugin("a", status=PluginStatus.ENABLED)])
    ctx.set("plugins.disabled", ["a"], save=False)
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("a")
    assert row.checkbox.isChecked() is False
    assert row.checkbox.isEnabled() is True   # user can re-enable


def test_checkbox_flips_when_disabled_setting_changes_between_renders(qtbot, ctx) -> None:
    """Re-opening the settings dialog after a toggle must reflect the
    new state. Regression for: toggle em-dash off, close Settings,
    re-open Settings → checkbox should still show 'off'.
    """
    ctx.set_plugins([_plugin("a", status=PluginStatus.ENABLED)])

    # First render: enabled
    page1 = PluginsSettingsPage(ctx)
    qtbot.addWidget(page1)
    assert page1.row_for("a").checkbox.isChecked() is True

    # User disables
    ctx.set("plugins.disabled", ["a"], save=False)

    # Second render: must show unchecked
    page2 = PluginsSettingsPage(ctx)
    qtbot.addWidget(page2)
    assert page2.row_for("a").checkbox.isChecked() is False


@pytest.mark.parametrize("status", [
    PluginStatus.LOAD_FAILURE,
    PluginStatus.MISSING_DEPS,
    PluginStatus.METADATA_ERROR,
    PluginStatus.API_MISMATCH,
])
def test_errored_plugin_checkbox_grayed_out(qtbot, ctx, status) -> None:
    ctx.set_plugins([_plugin("bad", status=status, detail="the reason")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("bad")
    assert row.checkbox.isEnabled() is False   # grayed — can't re-enable
    # Status text should mention the error reason somewhere visible
    assert "the reason" in row.status_label.text() or \
           "the reason" in row.detail_label.text()


# ---------------------------------------------------------------------------
# Apply — writing the disabled set back
# ---------------------------------------------------------------------------


def test_disabled_set_initially_matches_setting(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("a", status=PluginStatus.ENABLED),
        _plugin("b", status=PluginStatus.ENABLED),
    ])
    ctx.set("plugins.disabled", ["b"], save=False)
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    assert page.pending_disabled_set() == {"b"}


def test_toggling_enabled_to_disabled_updates_pending(qtbot, ctx) -> None:
    ctx.set_plugins([_plugin("a", status=PluginStatus.ENABLED)])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("a")
    row.checkbox.setChecked(False)
    assert page.pending_disabled_set() == {"a"}


def test_toggling_disabled_to_enabled_updates_pending(qtbot, ctx) -> None:
    ctx.set_plugins([_plugin("a", status=PluginStatus.ENABLED)])
    ctx.set("plugins.disabled", ["a"], save=False)
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("a")
    assert row.checkbox.isChecked() is False   # initial: reflects the live setting
    row.checkbox.setChecked(True)
    assert page.pending_disabled_set() == set()


def test_apply_persists_to_settings(qtbot, ctx) -> None:
    ctx.set_plugins([
        _plugin("keep", status=PluginStatus.ENABLED),
        _plugin("off", status=PluginStatus.ENABLED),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.row_for("off").checkbox.setChecked(False)
    page.apply()
    assert set(ctx.get("plugins.disabled", [])) == {"off"}


def test_configure_button_present_when_schema_registered(qtbot, ctx) -> None:
    """Plugins that registered a settings schema get a 'Configure…' button."""
    from markdown_editor.markdown6.plugins import api as plugin_api
    plugin_api._REGISTRY.clear()
    plugin_api.register_settings_schema(
        fields=[plugin_api.Field("k", "K", default="v")],
        plugin_id="hi",
    )
    ctx.set_plugins([_plugin("hi")])

    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)

    row = page.row_for("hi")
    assert row.configure_button is not None
    assert row.configure_button.isVisible() or row.configure_button.isEnabled()


def test_no_configure_button_when_no_schema(qtbot, ctx) -> None:
    """Plugins without a schema don't have a Configure… button at all
    — empty Configure dialogs would be confusing."""
    ctx.set_plugins([_plugin("plain")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("plain")
    assert row.configure_button is None


def test_configure_button_disabled_when_plugin_errored(qtbot, ctx) -> None:
    """An errored plugin's schema may not be loaded; Configure is disabled."""
    from markdown_editor.markdown6.plugins import api as plugin_api
    plugin_api._REGISTRY.clear()
    plugin_api.register_settings_schema(
        fields=[plugin_api.Field("k", "K")],
        plugin_id="broken",
    )
    ctx.set_plugins([_plugin("broken", status=PluginStatus.LOAD_FAILURE,
                             detail="kaboom")])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    row = page.row_for("broken")
    if row.configure_button is not None:
        assert not row.configure_button.isEnabled()


def test_apply_errored_plugins_not_added_to_disabled_set(qtbot, ctx) -> None:
    """An errored plugin is already unavailable — don't also write it
    into plugins.disabled (that'd stick even after fixing the error)."""
    ctx.set_plugins([
        _plugin("broken", status=PluginStatus.LOAD_FAILURE, detail="x"),
    ])
    page = PluginsSettingsPage(ctx)
    qtbot.addWidget(page)
    page.apply()
    assert "broken" not in set(ctx.get("plugins.disabled", []))

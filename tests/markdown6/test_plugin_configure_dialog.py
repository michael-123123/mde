"""Tests for the auto-rendered per-plugin Configure dialog."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit,
                               QSpinBox, QTextEdit)

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.plugin_configure_dialog import (
    PluginConfigureDialog,
)
from markdown_editor.markdown6.plugins import api as plugin_api


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
    yield
    plugin_api._REGISTRY.clear()


def _make_dialog(qtbot, ctx, fields, plugin_id="testplug"):
    plugin_api.register_settings_schema(fields=fields, plugin_id=plugin_id)
    schema = plugin_api._REGISTRY.get_settings_schema(plugin_id)
    dialog = PluginConfigureDialog(ctx, schema)
    qtbot.addWidget(dialog)
    return dialog


# ---------------------------------------------------------------------------
# Widget mapping
# ---------------------------------------------------------------------------


def test_str_field_renders_line_edit(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
    ])
    w = dialog.widget_for("name")
    assert isinstance(w, QLineEdit)
    assert w.text() == "World"


def test_str_field_with_choices_renders_combo_box(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("style", "Style",
                         default="casual", choices=("formal", "casual", "shouty")),
    ])
    w = dialog.widget_for("style")
    assert isinstance(w, QComboBox)
    assert [w.itemText(i) for i in range(w.count())] == ["formal", "casual", "shouty"]
    assert w.currentText() == "casual"


def test_str_field_multiline_widget_renders_text_edit(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("note", "Note", default="line one\nline two", widget="multiline"),
    ])
    w = dialog.widget_for("note")
    assert isinstance(w, QTextEdit)
    assert "line one" in w.toPlainText()


def test_int_field_renders_spin_box_with_bounds(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("n", "N", type=int, default=5, min=1, max=10),
    ])
    w = dialog.widget_for("n")
    assert isinstance(w, QSpinBox)
    assert w.value() == 5
    assert w.minimum() == 1
    assert w.maximum() == 10


def test_float_field_renders_double_spin_box(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("ratio", "Ratio", type=float, default=1.5),
    ])
    w = dialog.widget_for("ratio")
    assert isinstance(w, QDoubleSpinBox)
    assert w.value() == pytest.approx(1.5)


def test_bool_field_renders_check_box(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("enabled", "Enabled", type=bool, default=True),
    ])
    w = dialog.widget_for("enabled")
    assert isinstance(w, QCheckBox)
    assert w.isChecked() is True


# ---------------------------------------------------------------------------
# Initial values: come from plugin_settings, fall back to default
# ---------------------------------------------------------------------------


def test_initial_value_from_plugin_settings(qtbot, ctx) -> None:
    ctx.plugin_settings("testplug")["name"] = "Saved"
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
    ])
    assert dialog.widget_for("name").text() == "Saved"


def test_initial_value_falls_back_to_field_default(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
    ])
    assert dialog.widget_for("name").text() == "World"


def test_initial_value_for_unset_with_no_default(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name"),
    ])
    # Empty string for str type when no default
    assert dialog.widget_for("name").text() == ""


# ---------------------------------------------------------------------------
# OK / Cancel persistence
# ---------------------------------------------------------------------------


def test_apply_writes_to_plugin_settings(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
        plugin_api.Field("count", "Count", type=int, default=1, min=0, max=99),
        plugin_api.Field("enabled", "Enabled", type=bool, default=False),
    ])
    dialog.widget_for("name").setText("Universe")
    dialog.widget_for("count").setValue(7)
    dialog.widget_for("enabled").setChecked(True)
    dialog.apply()

    s = ctx.plugin_settings("testplug")
    assert s["name"] == "Universe"
    assert s["count"] == 7
    assert s["enabled"] is True


def test_apply_with_combo_box_writes_chosen_value(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("style", "Style",
                         default="casual", choices=("formal", "casual")),
    ])
    dialog.widget_for("style").setCurrentText("formal")
    dialog.apply()
    assert ctx.plugin_settings("testplug")["style"] == "formal"


def test_dialog_does_not_persist_until_apply_called(qtbot, ctx) -> None:
    """Modifying widgets without calling apply() must not write to settings."""
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
    ])
    dialog.widget_for("name").setText("DraftValue")
    # apply() not called → settings unchanged
    assert "name" not in ctx.plugin_settings("testplug")


# ---------------------------------------------------------------------------
# Reset to defaults
# ---------------------------------------------------------------------------


def test_reset_to_defaults_restores_all_widget_values(qtbot, ctx) -> None:
    dialog = _make_dialog(qtbot, ctx, [
        plugin_api.Field("name", "Name", default="World"),
        plugin_api.Field("count", "Count", type=int, default=10),
    ])
    dialog.widget_for("name").setText("Modified")
    dialog.widget_for("count").setValue(99)

    dialog.reset_to_defaults()
    assert dialog.widget_for("name").text() == "World"
    assert dialog.widget_for("count").value() == 10

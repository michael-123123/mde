"""Auto-rendered per-plugin Configure dialog.

Built from a :class:`PluginSettingsSchema` registered by a plugin via
:func:`api.register_settings_schema`. The dialog reads each field's
current value from :func:`AppContext.plugin_settings(plugin_id)`,
falling back to the field's ``default`` when unset, and writes the
edited values back through the same façade on :meth:`apply`.

Field-to-widget mapping:

* ``str`` (no choices) → :class:`QLineEdit`
* ``str`` with ``choices=`` → :class:`QComboBox`
* ``str`` with ``widget="multiline"`` → :class:`QTextEdit`
* ``int`` → :class:`QSpinBox` (bounded by ``min`` / ``max`` if set)
* ``float`` → :class:`QDoubleSpinBox`
* ``bool`` → :class:`QCheckBox`

The dialog is intentionally simple — no validators beyond bounds,
no async, no conditional fields. The plan calls these out as future
extensions if a plugin needs them; for now this covers the common
"API key + a few toggles + a count" cases.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_INT_MAX = 2**31 - 1
_INT_MIN = -(2**31)


class PluginConfigureDialog(QDialog):
    """Modal dialog auto-rendered from a plugin's settings schema."""

    def __init__(self, ctx, schema, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._schema = schema
        self._widgets: dict[str, QWidget] = {}

        self.setWindowTitle(f"Configure {schema.plugin_id}")
        self.setMinimumWidth(420)
        self._build_ui()
        self._load_initial_values()

    # ------------------------------------------------------------------
    # Public API used by tests + Settings → Plugins
    # ------------------------------------------------------------------

    def widget_for(self, key: str) -> QWidget | None:
        return self._widgets.get(key)

    def apply(self) -> None:
        """Persist current widget values to plugin_settings."""
        s = self._ctx.plugin_settings(self._schema.plugin_id)
        for field in self._schema.fields:
            s[field.key] = self._read_widget_value(field)

    def reset_to_defaults(self) -> None:
        for field in self._schema.fields:
            self._set_widget_value(field, field.default)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for field in self._schema.fields:
            widget = self._build_widget(field)
            self._widgets[field.key] = widget
            form.addRow(field.label + ":", widget)
            if field.description:
                hint = QLabel(field.description)
                hint.setObjectName("MutedLabel")
                hint.setWordWrap(True)
                form.addRow("", hint)

        outer.addLayout(form)
        outer.addStretch()

        # Button row
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        reset_btn = QPushButton("Reset to defaults")
        buttons.addButton(reset_btn, QDialogButtonBox.ButtonRole.ResetRole)
        reset_btn.clicked.connect(self.reset_to_defaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_widget(self, field) -> QWidget:
        if field.type is bool:
            return QCheckBox()
        if field.type is int:
            spin = QSpinBox()
            spin.setRange(
                int(field.min) if field.min is not None else _INT_MIN,
                int(field.max) if field.max is not None else _INT_MAX,
            )
            return spin
        if field.type is float:
            spin = QDoubleSpinBox()
            spin.setRange(
                float(field.min) if field.min is not None else -1e12,
                float(field.max) if field.max is not None else 1e12,
            )
            spin.setDecimals(4)
            return spin
        # str
        if field.choices:
            combo = QComboBox()
            for choice in field.choices:
                combo.addItem(choice)
            return combo
        if field.widget == "multiline":
            edit = QTextEdit()
            edit.setMinimumHeight(80)
            return edit
        return QLineEdit()

    # ------------------------------------------------------------------
    # Value transfer
    # ------------------------------------------------------------------

    def _load_initial_values(self) -> None:
        s = self._ctx.plugin_settings(self._schema.plugin_id)
        for field in self._schema.fields:
            value = s.get(field.key, field.default)
            self._set_widget_value(field, value)

    def _set_widget_value(self, field, value: Any) -> None:
        widget = self._widgets[field.key]
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value) if value is not None else False)
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value) if value is not None else 0)
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value) if value is not None else 0.0)
        elif isinstance(widget, QComboBox):
            if value is not None:
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(str(value) if value is not None else "")
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value) if value is not None else "")

    def _read_widget_value(self, field) -> Any:
        widget = self._widgets[field.key]
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return None

    def _accept(self) -> None:
        self.apply()
        self.accept()

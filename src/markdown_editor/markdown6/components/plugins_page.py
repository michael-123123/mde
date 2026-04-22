"""Settings → Plugins page.

Lists every plugin discovered by the loader with its status, a
description line, and a checkbox that lets the user disable it.
Designed as a self-contained ``QWidget`` so it can be tested in
isolation and dropped into :class:`SettingsDialog` with a single
``QStackedWidget.addWidget`` call.

Reads the plugin list from :meth:`AppContext.get_plugins`; writes
user toggle state back through the ``plugins.disabled`` setting on
:meth:`apply`.

Errored plugins (load failure, missing deps, metadata error, API
version mismatch) render with a grayed-out checkbox — the user can't
re-enable them from the UI; they need to fix the underlying problem
(install the missing dep, fix the TOML, etc.) and restart the editor.
Writing errored plugins into ``plugins.disabled`` is avoided so that
a transient error doesn't permanently mark the plugin as disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

from markdown_editor.markdown6.plugins.plugin import (Plugin, PluginSource,
                                                      PluginStatus)


_ERROR_STATUS_TEXT = {
    PluginStatus.LOAD_FAILURE:     "Error (load failure)",
    PluginStatus.MISSING_DEPS:     "Error (missing deps)",
    PluginStatus.METADATA_ERROR:   "Error (metadata)",
    PluginStatus.API_MISMATCH:     "Error (API version mismatch)",
}


def _effective_state(
    plugin: Plugin, disabled_set: set[str],
) -> tuple[str, bool, bool]:
    """Return (status_text, checked, can_toggle) for a plugin's row.

    Render state is driven by the *live* ``plugins.disabled`` setting,
    not by :attr:`Plugin.status`. ``Plugin.status`` is captured once
    at startup; when the user toggles a plugin from this page, the
    editor hides/shows its actions but does not mutate the captured
    status. Reading the current setting each time the page builds
    keeps the checkbox and the menu in sync across re-opens.
    """
    if plugin.is_errored:
        return (_ERROR_STATUS_TEXT[plugin.status], False, False)
    if plugin.name in disabled_set:
        return ("Disabled (by user)", False, True)
    return ("Enabled", True, True)


@dataclass
class _PluginRow:
    """Widgets for one plugin's row — exposed as a struct so tests can
    drive the checkbox directly and assert against the labels."""
    plugin: Plugin
    checkbox: QCheckBox
    name_label: QLabel
    version_label: QLabel
    source_label: QLabel
    status_label: QLabel
    detail_label: QLabel


class PluginsSettingsPage(QWidget):
    """Settings page that lists plugins with enable/disable toggles."""

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._rows: list[_PluginRow] = []
        self._empty_message = (
            "No plugins installed. Drop a plugin directory into "
            f"{self._user_plugin_dir_display()} and restart the editor."
        )
        self._init_ui()

    # ------------------------------------------------------------------
    # Public API (used by SettingsDialog and tests)
    # ------------------------------------------------------------------

    def row_count(self) -> int:
        return len(self._rows)

    def row_for(self, name: str) -> _PluginRow | None:
        for r in self._rows:
            if r.plugin.name == name:
                return r
        return None

    def empty_message(self) -> str:
        return self._empty_message

    def pending_disabled_set(self) -> set[str]:
        """Names the user currently wants disabled, based on checkbox state.

        Errored plugins are excluded regardless of their checkbox — we
        don't want a transient error to stamp the plugin as disabled
        in the user's persistent settings.
        """
        disabled: set[str] = set()
        for row in self._rows:
            if row.plugin.is_errored:
                continue
            if not row.checkbox.isChecked():
                disabled.add(row.plugin.name)
        return disabled

    def apply(self) -> None:
        """Persist the current toggle state to ``plugins.disabled``."""
        self._ctx.set("plugins.disabled", sorted(self.pending_disabled_set()))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(8)

        disabled_now = set(self._ctx.get("plugins.disabled", []) or [])
        plugins = list(self._ctx.get_plugins())
        # Sort: errored last; enabled before disabled; alphabetical within groups.
        plugins.sort(key=lambda p: (
            p.is_errored,
            p.name in disabled_now,
            p.name,
        ))

        if not plugins:
            empty = QLabel(self._empty_message)
            empty.setWordWrap(True)
            empty.setObjectName("MutedLabel")
            body_layout.addWidget(empty)
        else:
            intro = QLabel(
                "Installed plugins. Uncheck to disable; disabled plugins "
                "won't load on next startup. Errored plugins need their "
                "underlying issue fixed (missing dependency, bad TOML, "
                "etc.) before they can be re-enabled."
            )
            intro.setWordWrap(True)
            body_layout.addWidget(intro)

            for plugin in plugins:
                body_layout.addWidget(self._build_row_widget(plugin, disabled_now))

        body_layout.addStretch()
        scroll.setWidget(body)

    def _build_row_widget(self, plugin: Plugin, disabled_now: set[str]) -> QWidget:
        status_text, checked, can_toggle = _effective_state(plugin, disabled_now)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setEnabled(can_toggle)
        layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)

        # Text column: name (+ version + source) on top, status + detail under.
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_label = QLabel(f"<b>{plugin.name}</b>")
        version_label = QLabel(
            plugin.metadata.version if plugin.metadata else "—"
        )
        version_label.setObjectName("MutedLabel")
        source_label = QLabel(
            "builtin" if plugin.source == PluginSource.BUILTIN else "user"
        )
        source_label.setObjectName("MutedLabel")

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(name_label)
        top_row.addWidget(version_label)
        top_row.addWidget(source_label)
        top_row.addStretch()

        status_label_text = status_text
        if plugin.is_errored and plugin.detail:
            status_label_text = f"{status_label_text} — {plugin.detail}"
        status_label = QLabel(status_label_text)
        status_label.setWordWrap(True)

        detail_text = (
            plugin.metadata.description
            if plugin.metadata and plugin.metadata.description
            else ""
        )
        detail_label = QLabel(detail_text)
        detail_label.setWordWrap(True)
        detail_label.setObjectName("MutedLabel")

        text_col.addLayout(top_row)
        text_col.addWidget(status_label)
        if detail_text:
            text_col.addWidget(detail_label)

        layout.addLayout(text_col, 1)

        self._rows.append(_PluginRow(
            plugin=plugin,
            checkbox=checkbox,
            name_label=name_label,
            version_label=version_label,
            source_label=source_label,
            status_label=status_label,
            detail_label=detail_label,
        ))
        return frame

    def _user_plugin_dir_display(self) -> str:
        cfg = getattr(self._ctx, "config_dir", None)
        if cfg is None:
            return "<user config dir>/plugins/"
        return str(cfg / "plugins") + "/"

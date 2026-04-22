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

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QListWidget, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

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
    configure_button: QPushButton | None = None
    info_button: QPushButton | None = None


class PluginsSettingsPage(QWidget):
    """Settings page that lists plugins with enable/disable toggles."""

    # Emitted when the user clicks "Reload plugins". The editor
    # listens and routes to ``plugins.reload.reload_plugins`` with
    # the right roots — the page itself doesn't know the roots.
    reload_requested = Signal()

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._rows: list[_PluginRow] = []
        self.open_folder_button: QPushButton | None = None
        self.reload_button: QPushButton | None = None
        # Extra plugin directories the user has added on top of the
        # default user dir. Stored as plain strings (not Path) because
        # that's the persistence format in `plugins.extra_dirs`.
        self._pending_extra_dirs: list[str] = [
            str(p) for p in (ctx.get("plugins.extra_dirs", []) or [])
        ]
        self._extra_dirs_list: QListWidget | None = None
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
        """Persist the current toggle state and extra-dirs list."""
        self._ctx.set("plugins.disabled", sorted(self.pending_disabled_set()))
        self._ctx.set("plugins.extra_dirs", list(self._pending_extra_dirs))

    # ------------------------------------------------------------------
    # Extra plugin directories (additional discovery roots on top of the
    # default user dir). Mutating these takes effect at the next editor
    # restart — they're added to `_plugin_roots()`.
    # ------------------------------------------------------------------

    def pending_extra_dirs(self) -> list[str]:
        """Return the current pending list (insertion order preserved)."""
        return list(self._pending_extra_dirs)

    def add_extra_dir(self, path) -> None:
        """Add ``path`` to the pending list if it isn't already there."""
        s = str(path)
        if s not in self._pending_extra_dirs:
            self._pending_extra_dirs.append(s)
            self._refresh_extra_dirs_list()

    def remove_extra_dir(self, path) -> None:
        """Remove ``path`` from the pending list (no-op if absent)."""
        s = str(path)
        if s in self._pending_extra_dirs:
            self._pending_extra_dirs.remove(s)
            self._refresh_extra_dirs_list()

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

        # Page-level action bar (Open Folder, etc.) — always shown,
        # regardless of whether any plugins are installed. The Open
        # Folder action especially makes sense on an empty page since
        # that's exactly when a user wants to *get* their first plugin
        # in there.
        action_row = QHBoxLayout()
        self.open_folder_button = QPushButton("Open plugins folder")
        self.open_folder_button.setToolTip(
            "Reveal the user plugin directory in the file manager. "
            "Drop plugin directories here and restart the editor."
        )
        self.open_folder_button.clicked.connect(self._open_user_plugin_folder)
        action_row.addWidget(self.open_folder_button)

        self.reload_button = QPushButton("Reload plugins")
        self.reload_button.setToolTip(
            "Re-discover plugin directories on disk and report what's "
            "new or removed. Restart the editor to actually load any "
            "newly-discovered plugins."
        )
        self.reload_button.clicked.connect(self.reload_requested.emit)
        action_row.addWidget(self.reload_button)
        action_row.addStretch()
        body_layout.addLayout(action_row)

        # Extra plugin directories — list + Add/Remove buttons. Layered
        # on top of the default user dir; takes effect at next restart.
        body_layout.addWidget(self._build_extra_dirs_section())

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

        # Look up settings schema (if any) to decide whether to show
        # the Configure button. Imported lazily so this module doesn't
        # need to depend on the plugin api at module-load time.
        from markdown_editor.markdown6.plugins import api as plugin_api
        schema = plugin_api._REGISTRY.get_settings_schema(plugin.name)

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

        configure_button: QPushButton | None = None
        if schema is not None:
            configure_button = QPushButton("Configure…")
            configure_button.setEnabled(not plugin.is_errored)
            configure_button.clicked.connect(
                lambda _checked=False, _id=plugin.name: self._open_configure_dialog(_id),
            )
            layout.addWidget(configure_button, 0, Qt.AlignmentFlag.AlignTop)

        info_button = QPushButton("ℹ Info")
        info_button.setToolTip("Show plugin metadata + README")
        info_button.clicked.connect(
            lambda _checked=False, _p=plugin: self._open_info_dialog(_p),
        )
        layout.addWidget(info_button, 0, Qt.AlignmentFlag.AlignTop)

        self._rows.append(_PluginRow(
            plugin=plugin,
            checkbox=checkbox,
            name_label=name_label,
            version_label=version_label,
            source_label=source_label,
            status_label=status_label,
            detail_label=detail_label,
            configure_button=configure_button,
            info_button=info_button,
        ))
        return frame

    def _open_info_dialog(self, plugin: Plugin) -> None:
        from markdown_editor.markdown6.components.plugin_info_dialog import (
            PluginInfoDialog,
        )
        dialog = PluginInfoDialog(plugin, parent=self)
        dialog.exec()

    def _open_configure_dialog(self, plugin_id: str) -> None:
        from markdown_editor.markdown6.components.plugin_configure_dialog import (
            PluginConfigureDialog,
        )
        from markdown_editor.markdown6.plugins import api as plugin_api
        schema = plugin_api._REGISTRY.get_settings_schema(plugin_id)
        if schema is None:
            return
        dialog = PluginConfigureDialog(self._ctx, schema, parent=self)
        dialog.exec()

    def _user_plugin_dir_display(self) -> str:
        cfg = getattr(self._ctx, "config_dir", None)
        if cfg is None:
            return "<user config dir>/plugins/"
        return str(cfg / "plugins") + "/"

    def _user_plugin_dir(self):
        """Return the on-disk path to the user plugin directory.

        Mirrors the path ``MarkdownEditor._load_plugins`` reads from,
        so opening this folder in the file manager points the user at
        the same place plugins are loaded from.
        """
        from pathlib import Path
        cfg = getattr(self._ctx, "config_dir", None)
        if cfg is None:
            return None
        return Path(cfg) / "plugins"

    def _open_user_plugin_folder(self) -> None:
        path = self._user_plugin_dir()
        if path is None:
            return
        # Create on demand — saves the user a confusing
        # "folder doesn't exist" error from the file manager.
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # Extra plugin directories UI
    # ------------------------------------------------------------------

    def _build_extra_dirs_section(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        header = QLabel("<b>Extra plugin directories</b>")
        layout.addWidget(header)

        intro = QLabel(
            "Additional directories to scan for plugins on top of the "
            "default user folder. Same as passing <code>--plugins-dir</code> "
            "on the command line. Changes take effect at next restart."
        )
        intro.setWordWrap(True)
        intro.setObjectName("MutedLabel")
        layout.addWidget(intro)

        self._extra_dirs_list = QListWidget()
        self._extra_dirs_list.setMinimumHeight(80)
        layout.addWidget(self._extra_dirs_list)
        self._refresh_extra_dirs_list()

        button_row = QHBoxLayout()
        add_btn = QPushButton("Add directory…")
        add_btn.clicked.connect(self._prompt_add_extra_dir)
        button_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected_extra_dir)
        button_row.addWidget(remove_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        return frame

    def _refresh_extra_dirs_list(self) -> None:
        if self._extra_dirs_list is None:
            return
        self._extra_dirs_list.clear()
        for path in self._pending_extra_dirs:
            self._extra_dirs_list.addItem(path)

    def _prompt_add_extra_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select plugin directory", str(self._user_plugin_dir() or ""),
        )
        if path:
            self.add_extra_dir(path)

    def _remove_selected_extra_dir(self) -> None:
        if self._extra_dirs_list is None:
            return
        item = self._extra_dirs_list.currentItem()
        if item is None:
            return
        self.remove_extra_dir(item.text())

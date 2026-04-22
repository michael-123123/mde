"""Per-plugin Info dialog.

Modal showing a plugin's metadata, status detail (especially useful
for errored plugins where the inline label may be truncated), and
its README.md if the plugin shipped one.

Design intentionally simple — no Markdown rendering for v1: README is
shown via :meth:`QTextBrowser.setMarkdown` which Qt6 supports natively
out of the box, no extra dependency. Plain plugins without a README
just see the metadata section.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QLabel,
                               QScrollArea, QTextBrowser, QVBoxLayout,
                               QWidget)

from markdown_editor.markdown6.plugins.plugin import (Plugin, PluginSource,
                                                       PluginStatus)


_STATUS_DISPLAY = {
    PluginStatus.ENABLED: "Enabled",
    PluginStatus.DISABLED_BY_USER: "Disabled (by user)",
    PluginStatus.LOAD_FAILURE: "Error: load failure",
    PluginStatus.MISSING_DEPS: "Error: missing dependencies",
    PluginStatus.METADATA_ERROR: "Error: bad metadata",
    PluginStatus.API_MISMATCH: "Error: API version mismatch",
}


class PluginInfoDialog(QDialog):
    def __init__(self, plugin: Plugin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._readme_text: str = ""
        self._has_readme = False

        self.setWindowTitle(f"Plugin info: {plugin.name}")
        self.setMinimumSize(520, 420)

        if plugin.readme_path is not None and plugin.readme_path.is_file():
            try:
                self._readme_text = plugin.readme_path.read_text(encoding="utf-8")
                self._has_readme = True
            except OSError:
                self._readme_text = ""

        self._init_ui()

    # ------------------------------------------------------------------
    # Public API used by tests
    # ------------------------------------------------------------------

    def readme_text(self) -> str:
        return self._readme_text

    def has_readme(self) -> bool:
        return self._has_readme

    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        # Metadata section
        meta_lines = self._build_metadata_lines(self._plugin)
        meta_label = QLabel("\n".join(meta_lines))
        meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_label.setWordWrap(True)
        body_layout.addWidget(meta_label)

        # Optional description block
        if self._plugin.metadata and self._plugin.metadata.description:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            body_layout.addWidget(sep)
            desc = QLabel(self._plugin.metadata.description)
            desc.setWordWrap(True)
            body_layout.addWidget(desc)

        # Optional README block
        if self._has_readme:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            body_layout.addWidget(sep)
            readme_label = QLabel("<b>README</b>")
            body_layout.addWidget(readme_label)
            browser = QTextBrowser()
            browser.setMinimumHeight(180)
            browser.setOpenExternalLinks(True)
            # Qt6 supports markdown natively
            browser.setMarkdown(self._readme_text)
            body_layout.addWidget(browser, 1)

        body_layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    @staticmethod
    def _build_metadata_lines(plugin: Plugin) -> list[str]:
        m = plugin.metadata
        source_label = (
            "builtin" if plugin.source == PluginSource.BUILTIN else "user"
        )
        lines = [
            f"Name:    {plugin.name}",
            f"Version: {m.version if m else '—'}",
            f"Source:  {source_label}",
        ]
        if m and m.author:
            lines.append(f"Author:  {m.author}")
        lines.append(f"Status:  {_STATUS_DISPLAY.get(plugin.status, str(plugin.status))}")
        if plugin.detail:
            lines.append(f"Detail:  {plugin.detail}")
        return lines

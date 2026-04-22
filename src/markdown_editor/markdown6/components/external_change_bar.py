"""Non-modal notification bar for external file modifications."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from markdown_editor.markdown6.theme import StyleSheets, get_theme_from_ctx


class ExternalChangeBar(QWidget):
    """Non-modal notification bar shown when a file is modified externally."""

    reload_requested = Signal()
    dismissed = Signal()

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)
        self.hide()

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.message_label = QLabel()
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message_label, 1)

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._on_reload)
        layout.addWidget(self.reload_btn)

        self.dismiss_btn = QPushButton("Dismiss")
        self.dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self.dismiss_btn)

    def show_change(self, filename: str):
        """Show the bar for the given file. Coalesces repeated calls."""
        self.message_label.setText(
            f"\u26a0  {filename} has been modified externally."
        )
        if not self.isVisible():
            self.show()

    def _on_reload(self):
        self.hide()
        self.reload_requested.emit()

    def _on_dismiss(self):
        self.hide()
        self.dismissed.emit()

    def _on_setting_changed(self, key: str, value):
        if key == "view.theme":
            self._apply_theme()

    def _apply_theme(self):
        theme = get_theme_from_ctx(self.ctx)
        self.setStyleSheet(StyleSheets.external_change_bar(theme))

"""Base class for searchable popup dialogs."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.theme import StyleSheets, get_theme_from_ctx


class SearchablePopup(QDialog):
    """Base class for searchable popup dialogs with keyboard navigation."""

    def __init__(self, ctx=None, parent: QWidget | None = None):
        super().__init__(parent)
        if ctx is None:
            ctx = get_app_context()
        self.ctx = ctx
        self._init_base_ui()
        self._apply_theme()

    def _init_base_ui(self):
        """Initialize the base UI components."""
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._select_current)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)

        # List widget
        self.list_widget = QListWidget()
        self.list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_widget)

    def _apply_theme(self):
        """Apply the current theme."""
        theme = get_theme_from_ctx(self.ctx)
        self.setStyleSheet(StyleSheets.popup(theme))

    def _on_search_changed(self, text: str):
        """Handle search text change. Override in subclass."""
        pass

    def _on_item_activated(self, item: QListWidgetItem):
        """Handle item activation. Override in subclass."""
        pass

    def _select_current(self):
        """Select the current item."""
        item = self.list_widget.currentItem()
        if item:
            self._on_item_activated(item)

    def eventFilter(self, obj, event):
        """Filter events for keyboard navigation."""
        if obj == self.search_input and event.type() == event.Type.KeyPress:
            key = event.key()
            current = self.list_widget.currentRow()
            count = self.list_widget.count()

            if key == Qt.Key.Key_Down:
                if current < count - 1:
                    self.list_widget.setCurrentRow(current + 1)
                return True
            elif key == Qt.Key.Key_Up:
                if current > 0:
                    self.list_widget.setCurrentRow(current - 1)
                return True
            elif key == Qt.Key.Key_PageDown:
                self.list_widget.setCurrentRow(min(current + 10, count - 1))
                return True
            elif key == Qt.Key.Key_PageUp:
                self.list_widget.setCurrentRow(max(current - 10, 0))
                return True
            elif key == Qt.Key.Key_Home:
                self.list_widget.setCurrentRow(0)
                return True
            elif key == Qt.Key.Key_End:
                self.list_widget.setCurrentRow(count - 1)
                return True
            elif key == Qt.Key.Key_Escape:
                self.reject()
                return True

        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self._apply_theme()
        self.search_input.clear()
        self.search_input.setFocus()

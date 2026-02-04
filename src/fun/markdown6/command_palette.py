"""Command palette for quick access to all editor commands."""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from fun.markdown6.settings import get_settings
from fun.markdown6.theme import get_theme, StyleSheets


@dataclass
class Command:
    """Represents a command in the palette."""
    id: str
    name: str
    shortcut: str
    callback: Callable
    category: str = ""


class CommandPalette(QDialog):
    """A searchable command palette dialog."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = get_settings()
        self.commands: list[Command] = []
        self.filtered_commands: list[Command] = []
        self._init_ui()
        self._apply_theme()
        # Listen for theme changes
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Command Palette")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setMinimumWidth(500)
        self.setMaximumHeight(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search commands...")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._execute_selected)
        layout.addWidget(self.search_input)

        # Command list
        self.command_list = QListWidget()
        self.command_list.itemActivated.connect(self._on_item_activated)
        self.command_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.command_list.setMinimumHeight(300)  # Show ~10-12 items
        layout.addWidget(self.command_list)

        # Handle up/down navigation
        self.search_input.installEventFilter(self)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()
            self._update_list()  # Refresh list with new colors

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.settings.get("view.theme", "light")
        self._is_dark = theme_name == "dark"
        theme = get_theme(self._is_dark)

        self._text_color = theme.text_primary
        self._shortcut_color = theme.text_secondary
        self.setStyleSheet(StyleSheets.popup(theme))

    def set_commands(self, commands: list[Command]):
        """Set the available commands."""
        self.commands = sorted(commands, key=lambda c: c.name.lower())
        self._update_list()

    def _update_list(self):
        """Update the command list based on search filter."""
        self.command_list.clear()
        search_text = self.search_input.text().lower()

        if search_text:
            # Filter commands
            self.filtered_commands = [
                cmd for cmd in self.commands
                if search_text in cmd.name.lower() or search_text in cmd.category.lower()
            ]
        else:
            self.filtered_commands = self.commands.copy()

        for cmd in self.filtered_commands:
            # Build display text
            if cmd.category:
                display_text = f"{cmd.category}: {cmd.name}"
            else:
                display_text = cmd.name

            # Add shortcut with padding
            if cmd.shortcut:
                # Pad to align shortcuts
                padding = 50 - len(display_text)
                if padding > 0:
                    display_text += " " * padding
                display_text += f"  [{cmd.shortcut}]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self.command_list.addItem(item)

        if self.filtered_commands:
            self.command_list.setCurrentRow(0)

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._update_list()

    def _on_item_activated(self, item: QListWidgetItem):
        """Handle item activation."""
        self._execute_selected()

    def _execute_selected(self):
        """Execute the selected command."""
        row = self.command_list.currentRow()
        if 0 <= row < len(self.filtered_commands):
            cmd = self.filtered_commands[row]
            self.accept()
            cmd.callback()

    def eventFilter(self, obj, event):
        """Filter events for keyboard navigation."""
        if obj == self.search_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down:
                current = self.command_list.currentRow()
                if current < self.command_list.count() - 1:
                    self.command_list.setCurrentRow(current + 1)
                return True
            elif event.key() == Qt.Key.Key_Up:
                current = self.command_list.currentRow()
                if current > 0:
                    self.command_list.setCurrentRow(current - 1)
                return True
            elif event.key() == Qt.Key.Key_PageDown:
                current = self.command_list.currentRow()
                new_row = min(current + 10, self.command_list.count() - 1)
                self.command_list.setCurrentRow(new_row)
                return True
            elif event.key() == Qt.Key.Key_PageUp:
                current = self.command_list.currentRow()
                new_row = max(current - 10, 0)
                self.command_list.setCurrentRow(new_row)
                return True
            elif event.key() == Qt.Key.Key_Home:
                self.command_list.setCurrentRow(0)
                return True
            elif event.key() == Qt.Key.Key_End:
                self.command_list.setCurrentRow(self.command_list.count() - 1)
                return True
            elif event.key() == Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        # Refresh theme in case it changed
        self._apply_theme()
        self.search_input.clear()
        self.search_input.setFocus()
        self._update_list()

        # Center on parent
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.center().x() - self.width() // 2
            y = parent_rect.top() + 100
            self.move(x, y)

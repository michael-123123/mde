"""Command palette for quick access to all editor commands."""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QWidget

from fun.markdown6.searchable_popup import SearchablePopup


@dataclass
class Command:
    """Represents a command in the palette."""
    id: str
    name: str
    shortcut: str
    callback: Callable
    category: str = ""


class CommandPalette(SearchablePopup):
    """A searchable command palette dialog."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.commands: list[Command] = []
        self.filtered_commands: list[Command] = []
        self._init_ui()

    def _init_ui(self):
        """Initialize the command palette UI."""
        self.setWindowTitle("Command Palette")
        self.setMinimumWidth(500)
        self.setMaximumHeight(400)

        self.search_input.setPlaceholderText("Type to search commands...")
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setMinimumHeight(300)

        # Listen for theme changes
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()
            self._update_list()

    def set_commands(self, commands: list[Command]):
        """Set the available commands."""
        self.commands = sorted(commands, key=lambda c: c.name.lower())
        self._update_list()

    def _update_list(self):
        """Update the command list based on search filter."""
        self.list_widget.clear()
        search_text = self.search_input.text().lower()

        if search_text:
            self.filtered_commands = [
                cmd for cmd in self.commands
                if search_text in cmd.name.lower() or search_text in cmd.category.lower()
            ]
        else:
            self.filtered_commands = self.commands.copy()

        for cmd in self.filtered_commands:
            if cmd.category:
                display_text = f"{cmd.category}: {cmd.name}"
            else:
                display_text = cmd.name

            if cmd.shortcut:
                padding = 50 - len(display_text)
                if padding > 0:
                    display_text += " " * padding
                display_text += f"  [{cmd.shortcut}]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self.list_widget.addItem(item)

        if self.filtered_commands:
            self.list_widget.setCurrentRow(0)

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._update_list()

    def _on_item_activated(self, item: QListWidgetItem):
        """Handle item activation."""
        self._execute_selected()

    def _execute_selected(self):
        """Execute the selected command."""
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.filtered_commands):
            cmd = self.filtered_commands[row]
            self.accept()
            cmd.callback()

    def _select_current(self):
        """Select the current item."""
        self._execute_selected()

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self._update_list()

        # Center on parent
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.center().x() - self.width() // 2
            y = parent_rect.top() + 100
            self.move(x, y)

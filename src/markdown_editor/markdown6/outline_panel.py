"""Outline/Table of Contents panel for the Markdown editor."""

import re
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.app_context import AppContext


@dataclass
class Heading:
    """Represents a heading in the document."""
    level: int
    text: str
    line: int


class OutlinePanel(QWidget):
    """A panel showing the document outline/table of contents."""

    heading_clicked = Signal(int)  # line number

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setAnimated(True)
        layout.addWidget(self.tree)

    def _apply_theme(self):
        """Apply the current theme."""
        from markdown_editor.markdown6.theme import get_theme, StyleSheets

        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.panel(theme) +
            StyleSheets.tree_widget(theme)
        )

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

    def update_outline(self, text: str):
        """Update the outline from markdown text."""
        self.tree.clear()

        headings = self._parse_headings(text)
        if not headings:
            item = QTreeWidgetItem(["No headings found"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(item)
            return

        # Build tree structure
        stack: list[tuple[int, QTreeWidgetItem | None]] = [(0, None)]

        for heading in headings:
            item = QTreeWidgetItem([heading.text])
            item.setData(0, Qt.ItemDataRole.UserRole, heading.line)

            # Set icon based on level
            level_icons = {1: "H1", 2: "H2", 3: "H3", 4: "H4", 5: "H5", 6: "H6"}
            item.setText(0, f"{level_icons.get(heading.level, 'H')} {heading.text}")

            # Find parent
            while stack and stack[-1][0] >= heading.level:
                stack.pop()

            parent_item = stack[-1][1] if stack else None

            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            stack.append((heading.level, item))

        # Expand all by default
        self.tree.expandAll()

    def _parse_headings(self, text: str) -> list[Heading]:
        """Parse headings from markdown text."""
        headings = []
        lines = text.split("\n")
        in_code_block = False

        for line_num, line in enumerate(lines):
            # Track code blocks
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                continue

            # Match ATX headings (# Heading)
            match = re.match(r"^(#{1,6})\s+(.+?)(?:\s*#*\s*)?$", line)
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                headings.append(Heading(level=level, text=text, line=line_num))
                continue

            # Match setext headings (underlined)
            if line_num > 0 and lines[line_num - 1].strip():
                if re.match(r"^=+\s*$", line):
                    text = lines[line_num - 1].strip()
                    headings.append(Heading(level=1, text=text, line=line_num - 1))
                elif re.match(r"^-+\s*$", line) and len(line.strip()) >= 3:
                    text = lines[line_num - 1].strip()
                    headings.append(Heading(level=2, text=text, line=line_num - 1))

        return headings

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle item click."""
        line = item.data(0, Qt.ItemDataRole.UserRole)
        if line is not None:
            self.heading_clicked.emit(line)

    def _collapse_all(self):
        """Collapse all items."""
        self.tree.collapseAll()

    def _expand_all(self):
        """Expand all items."""
        self.tree.expandAll()

    def select_heading_at_line(self, line: int):
        """Select the heading at or before the given line."""
        best_item = None
        best_line = -1

        def find_item(item: QTreeWidgetItem):
            nonlocal best_item, best_line
            item_line = item.data(0, Qt.ItemDataRole.UserRole)
            if item_line is not None and item_line <= line and item_line > best_line:
                best_item = item
                best_line = item_line

            for i in range(item.childCount()):
                find_item(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            find_item(self.tree.topLevelItem(i))

        if best_item:
            self.tree.setCurrentItem(best_item)

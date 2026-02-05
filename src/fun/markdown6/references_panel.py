"""References/Backlinks panel for the Markdown editor."""

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from fun.markdown6.settings import get_settings


@dataclass
class Reference:
    """Represents a reference to a file."""
    source_file: Path  # The file containing the reference
    line_number: int   # Line number (0-indexed)
    line_content: str  # The line text containing the reference
    link_text: str     # The actual link/reference text found


class ReferencesPanel(QWidget):
    """A panel showing files that reference the current document (backlinks)."""

    file_clicked = Signal(str)        # file path
    reference_clicked = Signal(str, int)  # file path, line number

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = get_settings()
        self.project_path: Path | None = None
        self.current_file: Path | None = None
        self._references: list[Reference] = []
        self._init_ui()
        self._apply_theme()
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with refresh button
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        self.status_label = QLabel("No file open")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        header_layout.addWidget(self.status_label, 1)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh references")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self.refresh_btn)

        layout.addWidget(header)

        # Tree widget for references
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.setWordWrap(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

    def set_project_path(self, path: Path | None):
        """Set the project root path for scanning."""
        self.project_path = path

    def set_current_file(self, file_path: Path | None):
        """Set the current file and update references."""
        self.current_file = file_path
        self.update_references()

    def update_references(self):
        """Scan project and update the references list."""
        self.tree.clear()
        self._references = []

        if not self.current_file or not self.project_path:
            self.status_label.setText("No file open")
            self._show_empty_message("Open a file to see references")
            return

        if not self.project_path.exists():
            self.status_label.setText("No project open")
            self._show_empty_message("Open a project folder first")
            return

        # Get the filename to search for (without extension for flexible matching)
        target_name = self.current_file.stem
        target_filename = self.current_file.name

        # Scan all markdown files in the project
        self._references = self._find_references(target_name, target_filename)

        # Update UI
        if not self._references:
            self.status_label.setText("No references found")
            self._show_empty_message(f"No files reference '{target_filename}'")
            return

        self.status_label.setText(f"{len(self._references)} reference(s)")
        self._populate_tree()

    def _find_references(self, target_name: str, target_filename: str) -> list[Reference]:
        """Find all references to the target file in the project."""
        references = []

        # Patterns to match:
        # 1. Wiki links: [[filename]] or [[filename|display]]
        # 2. Markdown links: [text](filename.md) or [text](./path/filename.md)
        wiki_pattern = re.compile(
            r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
        )
        md_link_pattern = re.compile(
            r'\[([^\]]*)\]\(([^)]+\.md(?:own)?)\)'
        )

        # Scan all markdown files
        for md_file in self._get_markdown_files():
            # Skip the current file itself
            if md_file.resolve() == self.current_file.resolve():
                continue

            try:
                content = md_file.read_text(encoding='utf-8')
                lines = content.split('\n')

                for line_num, line in enumerate(lines):
                    # Check wiki links
                    for match in wiki_pattern.finditer(line):
                        link_target = match.group(1).strip()
                        if self._matches_target(link_target, target_name, target_filename):
                            references.append(Reference(
                                source_file=md_file,
                                line_number=line_num,
                                line_content=line.strip(),
                                link_text=match.group(0)
                            ))

                    # Check markdown links
                    for match in md_link_pattern.finditer(line):
                        link_path = match.group(2).strip()
                        link_filename = Path(link_path).name
                        link_stem = Path(link_path).stem
                        if self._matches_target(link_stem, target_name, target_filename) or \
                           self._matches_target(link_filename, target_name, target_filename):
                            references.append(Reference(
                                source_file=md_file,
                                line_number=line_num,
                                line_content=line.strip(),
                                link_text=match.group(0)
                            ))

            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                continue

        return references

    def _matches_target(self, link_text: str, target_name: str, target_filename: str) -> bool:
        """Check if link text matches the target file."""
        link_text_lower = link_text.lower()
        # Match by stem (without extension) or full filename
        return (link_text_lower == target_name.lower() or
                link_text_lower == target_filename.lower() or
                link_text_lower == target_name.lower() + '.md' or
                link_text_lower == target_name.lower() + '.markdown')

    def _get_markdown_files(self) -> list[Path]:
        """Get all markdown files in the project."""
        if not self.project_path:
            return []

        files = []
        for ext in ['*.md', '*.markdown']:
            files.extend(self.project_path.rglob(ext))
        return sorted(files)

    def _populate_tree(self):
        """Populate the tree widget with references."""
        # Group references by source file
        by_file: dict[Path, list[Reference]] = {}
        for ref in self._references:
            if ref.source_file not in by_file:
                by_file[ref.source_file] = []
            by_file[ref.source_file].append(ref)

        # Create tree items
        for source_file, refs in sorted(by_file.items(), key=lambda x: x[0].name):
            # File item
            rel_path = source_file.relative_to(self.project_path) if self.project_path else source_file
            file_item = QTreeWidgetItem([f"📄 {rel_path}"])
            file_item.setData(0, Qt.ItemDataRole.UserRole, str(source_file))
            file_item.setData(0, Qt.ItemDataRole.UserRole + 1, -1)  # No specific line
            self.tree.addTopLevelItem(file_item)

            # Reference items (line previews)
            for ref in refs:
                # Truncate long lines
                preview = ref.line_content
                if len(preview) > 80:
                    preview = preview[:77] + "..."

                line_item = QTreeWidgetItem([f"  Ln {ref.line_number + 1}: {preview}"])
                line_item.setData(0, Qt.ItemDataRole.UserRole, str(ref.source_file))
                line_item.setData(0, Qt.ItemDataRole.UserRole + 1, ref.line_number)
                line_item.setToolTip(0, ref.line_content)
                file_item.addChild(line_item)

            file_item.setExpanded(True)

    def _show_empty_message(self, message: str):
        """Show an empty state message."""
        item = QTreeWidgetItem([message])
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.tree.addTopLevelItem(item)

    def _on_refresh_clicked(self):
        """Handle refresh button click."""
        self.update_references()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle single click - emit file path."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path:
            self.file_clicked.emit(file_path)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double click - emit file path and line number."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        line_number = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path:
            if line_number is not None and line_number >= 0:
                self.reference_clicked.emit(file_path, line_number)
            else:
                # Just open the file (no specific line)
                self.reference_clicked.emit(file_path, 0)

    def _apply_theme(self):
        """Apply the current theme."""
        from fun.markdown6.theme import get_theme, StyleSheets

        theme_name = self.settings.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.panel(theme) +
            StyleSheets.tree_widget(theme) +
            StyleSheets.flat_button(theme)
        )

        # Update status label color based on theme
        self.status_label.setStyleSheet(
            f"color: {theme.text_muted}; font-size: 11px; background-color: transparent;"
        )

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

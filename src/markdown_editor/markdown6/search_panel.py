"""Project-wide search panel for the Markdown editor."""

import re
from pathlib import Path
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QPushButton,
)
from PySide6.QtGui import QFont

from markdown_editor.markdown6.app_context import get_project_markdown_files
from markdown_editor.markdown6.theme import get_theme, StyleSheets


@dataclass
class SearchMatch:
    """A single search match."""
    file_path: Path
    line_number: int  # 0-indexed
    line_content: str
    match_start: int  # character position in line
    match_end: int


class SearchPanel(QWidget):
    """Panel for project-wide search."""

    # Emitted when user wants to open a file at a specific line
    file_requested = Signal(str, int)  # file_path, line_number

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.project_path: Path | None = None
        self._matches: list[SearchMatch] = []
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)  # Debounce
        self._search_timer.timeout.connect(self._do_search)

        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in project...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._do_search)
        layout.addWidget(self.search_input)

        # Options row
        options_layout = QHBoxLayout()
        options_layout.setSpacing(12)

        self.case_check = QCheckBox("Aa")
        self.case_check.setToolTip("Case sensitive")
        self.case_check.toggled.connect(self._schedule_search)
        options_layout.addWidget(self.case_check)

        self.word_check = QCheckBox("W")
        self.word_check.setToolTip("Whole word")
        self.word_check.toggled.connect(self._schedule_search)
        options_layout.addWidget(self.word_check)

        self.regex_check = QCheckBox(".*")
        self.regex_check.setToolTip("Regular expression")
        self.regex_check.toggled.connect(self._schedule_search)
        options_layout.addWidget(self.regex_check)

        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("SearchStatus")
        layout.addWidget(self.status_label)

        # Results tree
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderHidden(True)
        self.results_tree.setIndentation(16)
        self.results_tree.setAnimated(True)
        self.results_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.results_tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.results_tree, 1)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_search)
        layout.addWidget(clear_btn)

    def set_project_path(self, path: Path | None):
        """Set the project root path for searching."""
        self.project_path = path
        if self.search_input.text():
            self._schedule_search()

    def focus_search(self):
        """Focus the search input and select all text."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._schedule_search()

    def _schedule_search(self):
        """Schedule a search with debouncing."""
        self._search_timer.start()

    def _do_search(self):
        """Perform the search."""
        self.results_tree.clear()
        self._matches = []

        query = self.search_input.text().strip()
        if not query or not self.project_path:
            self.status_label.setText("")
            return

        if not self.project_path.exists():
            self.status_label.setText("No project open")
            return

        # Build regex pattern
        try:
            if self.regex_check.isChecked():
                pattern = query
            else:
                pattern = re.escape(query)

            if self.word_check.isChecked():
                pattern = rf"\b{pattern}\b"

            flags = 0 if self.case_check.isChecked() else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            self.status_label.setText(f"Invalid regex: {e}")
            return

        # Search files
        self._matches = self._search_files(regex)

        # Update UI
        self._populate_results()

    def _search_files(self, regex: re.Pattern) -> list[SearchMatch]:
        """Search all markdown files for matches."""
        matches = []

        for md_file in self._get_markdown_files():
            try:
                content = md_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                for line_num, line in enumerate(lines):
                    for match in regex.finditer(line):
                        matches.append(SearchMatch(
                            file_path=md_file,
                            line_number=line_num,
                            line_content=line,
                            match_start=match.start(),
                            match_end=match.end(),
                        ))
            except (OSError, UnicodeDecodeError):
                continue

        return matches

    def _get_markdown_files(self) -> list[Path]:
        """Get all markdown files in the project."""
        if not self.project_path:
            return []

        return get_project_markdown_files(self.project_path)

    def _populate_results(self):
        """Populate the results tree."""
        if not self._matches:
            self.status_label.setText("No results")
            return

        # Group by file
        by_file: dict[Path, list[SearchMatch]] = {}
        for match in self._matches:
            if match.file_path not in by_file:
                by_file[match.file_path] = []
            by_file[match.file_path].append(match)

        # Update status
        file_count = len(by_file)
        match_count = len(self._matches)
        self.status_label.setText(
            f"{match_count} result{'s' if match_count != 1 else ''} "
            f"in {file_count} file{'s' if file_count != 1 else ''}"
        )

        # Build tree
        for file_path, file_matches in sorted(by_file.items(), key=lambda x: x[0].name):
            rel_path = file_path.relative_to(self.project_path) if self.project_path else file_path

            # File item
            file_item = QTreeWidgetItem([f"{rel_path} ({len(file_matches)})"])
            file_item.setData(0, Qt.ItemDataRole.UserRole, str(file_path))
            file_item.setData(0, Qt.ItemDataRole.UserRole + 1, -1)
            font = file_item.font(0)
            font.setBold(True)
            file_item.setFont(0, font)
            self.results_tree.addTopLevelItem(file_item)

            # Match items
            for match in file_matches:
                # Truncate long lines
                line_preview = match.line_content.strip()
                if len(line_preview) > 100:
                    # Try to show context around match
                    start = max(0, match.match_start - 30)
                    end = min(len(line_preview), match.match_end + 50)
                    line_preview = ("..." if start > 0 else "") + line_preview[start:end] + ("..." if end < len(match.line_content) else "")

                match_item = QTreeWidgetItem([f"  {match.line_number + 1}: {line_preview}"])
                match_item.setData(0, Qt.ItemDataRole.UserRole, str(match.file_path))
                match_item.setData(0, Qt.ItemDataRole.UserRole + 1, match.line_number)
                match_item.setToolTip(0, match.line_content)
                file_item.addChild(match_item)

            file_item.setExpanded(True)

    def _clear_search(self):
        """Clear the search."""
        self.search_input.clear()
        self.results_tree.clear()
        self._matches = []
        self.status_label.setText("")

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle single click on result item."""
        pass  # Could preview in editor without opening

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double click on result item."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        line_number = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if file_path:
            # If it's a file header, open at line 0
            if line_number == -1:
                line_number = 0
            self.file_requested.emit(file_path, line_number)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.panel(theme) +
            StyleSheets.line_edit(theme) +
            StyleSheets.check_box(theme) +
            StyleSheets.tree_widget(theme) +
            StyleSheets.button(theme) +
            f"""
            #SearchStatus {{
                color: {theme.text_secondary};
                font-size: 11px;
            }}
            """
        )

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

"""Project folder management for the Markdown editor."""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import Qt, Signal, QDir
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeView,
    QFileSystemModel,
    QPushButton,
    QToolButton,
    QLabel,
    QMenu,
    QInputDialog,
    QMessageBox,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QGroupBox,
    QLineEdit,
    QComboBox,
    QProgressDialog,
)

from fun.markdown6.settings import get_settings
from fun.markdown6.theme import get_theme, StyleSheets
from fun.markdown6 import export_service


@dataclass
class ProjectConfig:
    """Configuration for a project."""
    name: str
    root_path: str
    export_order: list[str] = field(default_factory=list)
    export_format: str = "html"
    created: str = ""
    modified: str = ""


class ProjectPanel(QWidget):
    """A panel for managing project files.

    When the project root is outside the user's home directory, the panel
    operates in "lazy" mode: directory contents are only scanned on expand,
    ``expandAll()`` is skipped, and ``get_project_files()`` only returns
    files from already-expanded directories.  This prevents the app from
    freezing when opened with e.g. ``mde -p /``.
    """

    file_selected = Signal(str)  # file path
    file_double_clicked = Signal(str)  # file path
    graph_export_requested = Signal()  # request to open graph export dialog

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = get_settings()
        self.project_path: Path | None = None
        self._lazy = False  # True when project root is outside $HOME
        self._filter_text = ""
        self._init_ui()
        self._apply_theme()
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Filter/search box
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter files...")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.filter_input)

        # File tree
        self.file_model = QFileSystemModel()
        self.file_model.setNameFilters(["*.md", "*.markdown", "*.txt"])
        self.file_model.setNameFilterDisables(False)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.file_model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)

        # Hide all columns except name
        for i in range(1, self.file_model.columnCount()):
            self.tree_view.hideColumn(i)

        self.tree_view.clicked.connect(self._on_item_clicked)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.tree_view)

        # Action buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.setSpacing(4)

        # Export project button (using emoji)
        self.export_btn = QToolButton()
        self.export_btn.setText("📤")
        self.export_btn.setToolTip("Export Project...")
        self.export_btn.clicked.connect(self._show_export_dialog)
        btn_layout.addWidget(self.export_btn)

        # Graph export button (using emoji)
        self.graph_btn = QToolButton()
        self.graph_btn.setText("🕸️")
        self.graph_btn.setToolTip("Export Document Graph...")
        self.graph_btn.clicked.connect(self._on_graph_export_clicked)
        btn_layout.addWidget(self.graph_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.settings.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.panel(theme) +
            StyleSheets.tree_widget(theme) +
            StyleSheets.line_edit(theme) +
            StyleSheets.flat_button(theme)
        )

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

    def _open_folder(self):
        """Open a folder as project."""
        folder = QFileDialog.getExistingDirectory(
            self, "Open Project Folder", str(Path.home())
        )
        if folder:
            self.set_project_path(Path(folder))

    def set_project_path(self, path: Path):
        """Set the project root path.

        Projects outside the user's home directory use lazy scanning to
        avoid freezing on huge trees (e.g. ``/``).
        """
        self.project_path = path
        try:
            home = Path.home()
            self._lazy = not path.resolve().is_relative_to(home.resolve())
        except (ValueError, RuntimeError):
            self._lazy = True
        self.file_model.setRootPath(str(path))
        self.tree_view.setRootIndex(self.file_model.index(str(path)))
        # Remember last project
        self.settings.set("project.last_path", str(path))
        # Clear filter
        self.filter_input.clear()

    def _on_filter_changed(self, text: str):
        """Handle filter text change."""
        self._filter_text = text.lower()
        if text:
            # Create filter pattern that matches the search text
            patterns = [f"*{text}*.md", f"*{text}*.markdown", f"*{text}*.txt"]
            self.file_model.setNameFilters(patterns)
        else:
            # Reset to default filters
            self.file_model.setNameFilters(["*.md", "*.markdown", "*.txt"])
        # In lazy mode, don't expand everything — it would scan the whole tree
        if not self._lazy:
            self.tree_view.expandAll()

    def _on_item_clicked(self, index):
        """Handle item click."""
        path = self.file_model.filePath(index)
        if Path(path).is_file():
            self.file_selected.emit(path)

    def _on_item_double_clicked(self, index):
        """Handle item double click."""
        path = self.file_model.filePath(index)
        if Path(path).is_file():
            self.file_double_clicked.emit(path)

    def _show_context_menu(self, position):
        """Show context menu."""
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            return

        path = Path(self.file_model.filePath(index))
        menu = QMenu(self)

        if path.is_file():
            open_action = menu.addAction("Open")
            open_action.triggered.connect(lambda: self.file_double_clicked.emit(str(path)))

            menu.addSeparator()

            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename_file(path))

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._delete_file(path))
        else:
            new_file_action = menu.addAction("New File")
            new_file_action.triggered.connect(lambda: self._new_file(path))

            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(lambda: self._new_folder(path))

        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def _new_file(self, folder: Path):
        """Create a new file in the folder."""
        name, ok = QInputDialog.getText(
            self, "New File", "File name:", text="untitled.md"
        )
        if ok and name:
            new_path = folder / name
            if not new_path.suffix:
                new_path = new_path.with_suffix(".md")
            try:
                new_path.touch()
                self.file_double_clicked.emit(str(new_path))
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not create file: {e}")

    def _new_folder(self, parent: Path):
        """Create a new folder."""
        name, ok = QInputDialog.getText(
            self, "New Folder", "Folder name:"
        )
        if ok and name:
            new_path = parent / name
            try:
                new_path.mkdir(exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not create folder: {e}")

    def _rename_file(self, path: Path):
        """Rename a file."""
        name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=path.name
        )
        if ok and name:
            new_path = path.parent / name
            try:
                path.rename(new_path)
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not rename file: {e}")

    def _delete_file(self, path: Path):
        """Delete a file."""
        reply = QMessageBox.question(
            self,
            "Delete File",
            f"Are you sure you want to delete '{path.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                path.unlink()
            except OSError as e:
                QMessageBox.critical(self, "Error", f"Could not delete file: {e}")

    def _show_export_dialog(self):
        """Show the project export dialog."""
        if not self.project_path:
            QMessageBox.warning(
                self, "No Project", "Please open a project folder first."
            )
            return

        dialog = ProjectExportDialog(self.project_path, self)
        dialog.exec()

    def _on_graph_export_clicked(self):
        """Handle graph export button click."""
        if not self.project_path:
            QMessageBox.warning(
                self, "No Project", "Please open a project folder first."
            )
            return
        self.graph_export_requested.emit()

    def get_project_files(self) -> list[Path]:
        """Get all markdown files in the project.

        In lazy mode, only scans the top 2 directory levels to avoid
        walking huge trees.  In eager mode, does a full recursive scan.
        """
        if not self.project_path:
            return []

        if not self._lazy:
            files = []
            for ext in ["*.md", "*.markdown"]:
                files.extend(self.project_path.rglob(ext))
            return sorted(files)

        # Lazy mode: only scan 2 levels deep
        files = []
        exts = {".md", ".markdown"}
        for child in self.project_path.iterdir():
            if child.is_file() and child.suffix in exts:
                files.append(child)
            elif child.is_dir():
                try:
                    for grandchild in child.iterdir():
                        if grandchild.is_file() and grandchild.suffix in exts:
                            files.append(grandchild)
                except PermissionError:
                    pass
        return sorted(files)


class ProjectExportDialog(QDialog):
    """Dialog for exporting a project to a single document."""

    def __init__(self, project_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.project_path = project_path
        self.settings = get_settings()
        self._init_ui()
        self._load_files()
        self._apply_theme()

    def _init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Export Project")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # File list with checkboxes
        file_group = QGroupBox("Files to Include (drag to reorder)")
        file_layout = QVBoxLayout(file_group)

        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        file_layout.addWidget(self.file_list)

        # Select all/none buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addStretch()
        file_layout.addLayout(btn_layout)

        layout.addWidget(file_group)

        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout(options_group)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["HTML", "PDF", "DOCX", "Markdown"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        options_layout.addLayout(format_layout)

        self.include_toc = QCheckBox("Include Table of Contents")
        self.include_toc.setChecked(True)
        options_layout.addWidget(self.include_toc)

        self.page_breaks = QCheckBox("Insert page breaks between files")
        self.page_breaks.setChecked(True)
        options_layout.addWidget(self.page_breaks)

        self.use_pandoc = QCheckBox("Use Pandoc for export (requires LaTeX for PDF)")
        self.use_pandoc.setChecked(False)
        if not export_service.has_pandoc():
            self.use_pandoc.setEnabled(False)
            self.use_pandoc.setToolTip("Pandoc is not installed on this system")
        else:
            self.use_pandoc.setToolTip("Use Pandoc instead of built-in exporters")
        options_layout.addWidget(self.use_pandoc)

        layout.addWidget(options_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._export)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.settings.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.dialog(theme) +
            StyleSheets.list_widget(theme) +
            StyleSheets.button(theme) +
            StyleSheets.combo_box(theme) +
            StyleSheets.check_box(theme)
        )

    def _load_files(self):
        """Load project files into the list.

        Uses the parent panel's get_project_files() when available to
        respect lazy scanning limits.
        """
        parent_panel = self.parent()
        if isinstance(parent_panel, ProjectPanel):
            paths = parent_panel.get_project_files()
        else:
            paths = []
            for ext in ["*.md", "*.markdown"]:
                paths.extend(sorted(self.project_path.rglob(ext)))
        for path in paths:
                rel_path = path.relative_to(self.project_path)
                item = QListWidgetItem(str(rel_path))
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.file_list.addItem(item)

    def _select_all(self):
        """Select all files."""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        """Deselect all files."""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _export(self):
        """Export the project."""
        # Get selected files in order
        files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                files.append(Path(item.data(Qt.ItemDataRole.UserRole)))

        if not files:
            QMessageBox.warning(self, "No Files", "Please select at least one file.")
            return

        format_type = self.format_combo.currentText().lower()
        ext = {"html": ".html", "pdf": ".pdf", "docx": ".docx", "markdown": ".md"}[format_type]

        # Get output path
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Project",
            str(self.project_path / f"{self.project_path.name}{ext}"),
            f"{format_type.upper()} Files (*{ext})",
        )

        if not output_path:
            return

        # Create progress dialog
        # Steps: 1 per file for reading + 1 for final conversion
        total_steps = len(files) + 1
        progress = QProgressDialog("Preparing export...", "Cancel", 0, total_steps, self)
        progress.setWindowTitle("Exporting Project")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()

        # Combine files
        combined_content = []

        if self.include_toc.isChecked():
            combined_content.append("# Table of Contents\n")
            for i, file_path in enumerate(files, 1):
                name = file_path.stem.replace("-", " ").replace("_", " ").title()
                combined_content.append(f"{i}. [{name}](#{name.lower().replace(' ', '-')})")
            combined_content.append("\n---\n")

        for i, file_path in enumerate(files):
            if progress.wasCanceled():
                return

            progress.setLabelText(f"Reading: {file_path.name} ({i + 1}/{len(files)})")
            progress.setValue(i)
            QApplication.processEvents()

            content = file_path.read_text(encoding="utf-8")

            if self.page_breaks.isChecked() and format_type == "html":
                combined_content.append('<div style="page-break-before: always;"></div>\n')
            elif self.page_breaks.isChecked() and format_type == "markdown":
                combined_content.append("\n---\n\n")

            combined_content.append(content)
            combined_content.append("\n\n")

        if progress.wasCanceled():
            return

        combined = "\n".join(combined_content)
        title = self.project_path.name

        # Final conversion step
        progress.setLabelText(f"Converting to {format_type.upper()}...")
        progress.setValue(len(files))
        QApplication.processEvents()

        use_pandoc = self.use_pandoc.isChecked()

        try:
            if format_type == "markdown":
                Path(output_path).write_text(combined, encoding="utf-8")
            elif format_type == "html":
                export_service.export_html(combined, output_path, title)
            elif format_type == "pdf":
                export_service.export_pdf(combined, output_path, title, use_pandoc)
            elif format_type == "docx":
                export_service.export_docx(combined, output_path, title, use_pandoc)

            progress.setValue(total_steps)
            QMessageBox.information(self, "Export Complete", f"Exported to {output_path}")
            self.accept()
        except export_service.ExportError as e:
            progress.close()
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Export failed: {e}")

"""Project folder management for the Markdown editor."""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QDir, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileSystemModel,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6 import export_service
from markdown_editor.markdown6.app_context import get_project_markdown_files
from markdown_editor.markdown6.file_tree_widget import FileTreeWidget
from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.theme import StyleSheets, get_theme_from_ctx

logger = getLogger(__name__)


@dataclass
class ProjectConfig:
    """Configuration for a project."""
    name: str
    root_path: str
    export_order: list[str] = field(default_factory=list)
    export_format: str = "html"
    created: str = ""
    modified: str = ""


class _ProjectFileSystemModel(QFileSystemModel):
    """QFileSystemModel that returns the *project-relative* path as the
    tooltip for every index, instead of Qt's default (the absolute path
    on some platforms, nothing on others).

    Showing the relative path on hover gives the user folder context
    without having to expand the tree - useful for disambiguating
    same-named files in different folders, and for files whose basename
    is truncated in the panel's narrow column.
    """

    def __init__(self, project_path_getter):
        super().__init__()
        self._project_path_getter = project_path_getter

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.ToolTipRole and index.isValid():
            file_path = Path(self.filePath(index))
            project_path = self._project_path_getter()
            if project_path is not None:
                try:
                    return str(file_path.relative_to(project_path))
                except ValueError:
                    # File is outside the project root - fall back to
                    # the absolute path so the tooltip still says
                    # something useful.
                    pass
            return str(file_path)
        return super().data(index, role)


class _FileBrowserSortProxy(QSortFilterProxyModel):
    """Sort proxy between ``QFileSystemModel`` and the project tree view.

    Enforces two rules on top of the underlying model:

    1. Directories always appear above files - regardless of sort order.
       ``QFileSystemModel`` has no built-in flag for this; we override
       ``lessThan`` to enforce it.
    2. Within each group (dirs / files), sort by either filename or
       ``QFileInfo.lastModified()``. ``QFileInfo`` is Qt's portable
       timestamp accessor (same call on Linux/macOS/Windows), so the
       comparison is OS-agnostic.

    Sort direction is taken from ``sortOrder()``. Because Qt automatically
    inverts the result of ``lessThan`` under DESC, we pre-invert the
    dir-vs-file branch so directories stay on top either way.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_key = "name"  # "name" | "mtime"

    def set_sort_key(self, key: str):
        if key not in ("name", "mtime"):
            raise ValueError(f"sort key must be 'name' or 'mtime', got {key!r}")
        if key == self._sort_key:
            return
        self._sort_key = key
        self.invalidate()

    def sort_key(self) -> str:
        return self._sort_key

    def lessThan(self, left, right):
        src = self.sourceModel()
        li = src.fileInfo(left)
        ri = src.fileInfo(right)
        # Invariant 1: dirs always above files. Pre-invert under DESC so
        # Qt's automatic flip doesn't move them below.
        if li.isDir() != ri.isDir():
            asc = self.sortOrder() == Qt.SortOrder.AscendingOrder
            return li.isDir() if asc else not li.isDir()
        # Invariant 2: within the same kind, sort by chosen key.
        if self._sort_key == "mtime":
            return li.lastModified() < ri.lastModified()
        return li.fileName().lower() < ri.fileName().lower()


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

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.project_path: Path | None = None
        self._lazy = False  # True when project root is outside $HOME
        self._filter_text = ""
        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

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
        self.file_model = _ProjectFileSystemModel(lambda: self.project_path)
        self.file_model.setNameFilters(["*.md", "*.markdown", "*.txt"])
        self.file_model.setNameFilterDisables(False)
        self._apply_hidden_filter()

        # Sort proxy sits between the file-system model and the tree view.
        # It enforces "dirs always first" plus user-chosen sort key/order.
        # Every code path that crosses this boundary must use
        # ``mapFromSource`` / ``mapToSource``.
        self.proxy = _FileBrowserSortProxy(self)
        self.proxy.setSourceModel(self.file_model)
        self._apply_sort_from_settings()

        self.tree_view = QTreeView()
        # NB: model is NOT bound here. ``QTreeView.setModel(proxy)``
        # triggers Qt to query ``rowCount(QModelIndex())`` on the
        # proxy, which delegates to QFileSystemModel, which answers by
        # enumerating its current root - the filesystem root if
        # setRootPath was never called. Binding here would defeat the
        # whole "no scan" point of the empty / --clean state. The bind
        # is deferred to set_project_path, where it pairs with the
        # setRootPath that actually anchors the model to a tree.
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

        # Spacer keeps the sort button right-aligned, separated from the
        # export-related buttons on the left.
        btn_layout.addStretch()

        self.sort_btn = QToolButton()
        self.sort_btn.setText("⇅")
        self.sort_btn.setToolTip("Sort options")
        self.sort_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.sort_btn.setMenu(self._build_sort_menu())
        # Hide Qt's auto-added menu indicator chevron - it visually
        # squishes the down-arrow half of the ⇅ glyph. Discoverability
        # comes from the tooltip and the button's hover/press feedback.
        self.sort_btn.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        btn_layout.addWidget(self.sort_btn)

        layout.addLayout(btn_layout)

        # Default to the empty / "no project open" state. The whole
        # point of this hide is QFileSystemModel: without setRootPath
        # it defaults to displaying the filesystem root, which means
        # an empty-state project panel would otherwise render '/'.
        # set_project_path flips the chrome back on when a project is
        # actually loaded.
        self._set_chrome_visible(False)

    def _set_chrome_visible(self, visible: bool):
        """Toggle every project-specific widget. Hidden = blank pane
        ('no project open'); visible = the normal project view."""
        self.filter_input.setVisible(visible)
        self.tree_view.setVisible(visible)
        self.export_btn.setVisible(visible)
        self.graph_btn.setVisible(visible)
        self.sort_btn.setVisible(visible)

    def _build_sort_menu(self) -> QMenu:
        """Build the sort-options popup menu attached to the sort button.

        Two action groups - one for key (name / mtime), one for order
        (asc / desc) - both exclusive so the menu always has exactly one
        checkmark per group, matching the user's persisted choice.
        Toggling a radio writes the corresponding ctx setting; the
        settings_changed signal then calls back into the panel via
        ``_apply_sort_from_settings``.
        """
        menu = QMenu(self)

        # --- Sort key group ---
        key_group = QActionGroup(menu)
        key_group.setExclusive(True)
        current_key = self.ctx.get("project.sort_key", "name")

        act_name = menu.addAction("Sort by Name")
        act_name.setCheckable(True)
        act_name.setActionGroup(key_group)
        act_name.setChecked(current_key == "name")
        act_name.triggered.connect(
            lambda: self.ctx.set("project.sort_key", "name")
        )

        act_mtime = menu.addAction("Sort by Modified")
        act_mtime.setCheckable(True)
        act_mtime.setActionGroup(key_group)
        act_mtime.setChecked(current_key == "mtime")
        act_mtime.triggered.connect(
            lambda: self.ctx.set("project.sort_key", "mtime")
        )

        menu.addSeparator()

        # --- Sort order group ---
        order_group = QActionGroup(menu)
        order_group.setExclusive(True)
        current_order = self.ctx.get("project.sort_order", "asc")

        act_asc = menu.addAction("Ascending")
        act_asc.setCheckable(True)
        act_asc.setActionGroup(order_group)
        act_asc.setChecked(current_order == "asc")
        act_asc.triggered.connect(
            lambda: self.ctx.set("project.sort_order", "asc")
        )

        act_desc = menu.addAction("Descending")
        act_desc.setCheckable(True)
        act_desc.setActionGroup(order_group)
        act_desc.setChecked(current_order == "desc")
        act_desc.triggered.connect(
            lambda: self.ctx.set("project.sort_order", "desc")
        )

        # Remember actions so we can keep checkmarks in sync if the
        # settings change from elsewhere (e.g. another panel, settings
        # dialog, hand-edit + reload).
        self._sort_actions = {
            ("name",): act_name,
            ("mtime",): act_mtime,
            ("asc",): act_asc,
            ("desc",): act_desc,
        }

        return menu

    def _apply_theme(self):
        """Apply the current theme."""
        theme = get_theme_from_ctx(self.ctx)

        self.setStyleSheet(
            StyleSheets.panel(theme) +
            StyleSheets.tree_widget(theme) +
            StyleSheets.line_edit(theme) +
            StyleSheets.flat_button(theme)
        )

    def _apply_hidden_filter(self):
        """Apply the hidden files filter based on settings."""
        show_hidden = self.ctx.get("files.show_hidden", False)
        base_filters = QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        if show_hidden:
            base_filters |= QDir.Filter.Hidden
        self.file_model.setFilter(base_filters)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()
        elif key == "files.show_hidden":
            self._apply_hidden_filter()
        elif key in ("project.sort_key", "project.sort_order"):
            self._apply_sort_from_settings()

    def _apply_sort_from_settings(self):
        """Read sort_key / sort_order from settings and apply to the proxy.

        Defensive: unknown values fall back to defaults so a hand-edited
        settings file can't break the panel.
        """
        key = self.ctx.get("project.sort_key", "name")
        if key not in ("name", "mtime"):
            key = "name"
        order_str = self.ctx.get("project.sort_order", "asc")
        order = (
            Qt.SortOrder.DescendingOrder if order_str == "desc"
            else Qt.SortOrder.AscendingOrder
        )
        self.proxy.set_sort_key(key)
        self.proxy.sort(0, order)
        # Keep menu checkmarks in sync if the change came from elsewhere.
        actions = getattr(self, "_sort_actions", None)
        if actions:
            actions[("name",)].setChecked(key == "name")
            actions[("mtime",)].setChecked(key == "mtime")
            actions[("asc",)].setChecked(order_str == "asc")
            actions[("desc",)].setChecked(order_str == "desc")

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
            # path.resolve() can hit symlink loops (RuntimeError) or
            # cross-drive comparison issues on Windows (ValueError);
            # default to lazy mode so a broken root doesn't freeze us.
            logger.exception(
                "Could not resolve project path %s relative to home; "
                "defaulting to lazy mode", path,
            )
            self._lazy = True
        logger.info(
            "Project root: %s%s", path, " (lazy mode)" if self._lazy else "",
        )
        self.file_model.setRootPath(str(path))
        # Bind the model on first project load (deferred from _init_ui
        # to avoid the implicit '/' enumeration). Subsequent
        # set_project_path calls re-call setModel; Qt treats that as a
        # no-op when the model is unchanged.
        self.tree_view.setModel(self.proxy)
        self.tree_view.setRootIndex(self.proxy.mapFromSource(self.file_model.index(str(path))))
        # The panel may have been started in the empty / no-project
        # state with its chrome hidden; reveal it now that a real
        # project is loaded.
        self._set_chrome_visible(True)
        # Remember last project
        self.ctx.set("project.last_path", str(path))
        # Clear filter
        self.filter_input.clear()
        # Restore expanded directories from last session
        self._pending_expand: set[str] = set()
        self.restore_tree_state()

    def save_tree_state(self):
        """Save the list of expanded directory paths."""
        if not self.project_path:
            return
        expanded = []
        self._collect_expanded(self.tree_view.rootIndex(), expanded)
        self.ctx.set("project.expanded_dirs", expanded)

    def _collect_expanded(self, parent_index, result: list[str]):
        """Recursively collect expanded directory paths.

        ``parent_index`` is a proxy index (``tree_view.rootIndex()`` and
        proxy children); we walk the proxy and ask ``file_model`` for
        the underlying path via ``mapToSource``.
        """
        for row in range(self.proxy.rowCount(parent_index)):
            child = self.proxy.index(row, 0, parent_index)
            if self.tree_view.isExpanded(child):
                src = self.proxy.mapToSource(child)
                result.append(self.file_model.filePath(src))
                self._collect_expanded(child, result)

    def restore_tree_state(self):
        """Restore expanded directories from settings.

        QFileSystemModel loads directory contents asynchronously.  We
        listen for ``directoryLoaded`` and, each time a directory becomes
        available, expand any of its children that were saved.  Expanding
        a directory triggers its children to load, which fires more
        ``directoryLoaded`` signals, cascading down the tree.
        """
        if not self.project_path:
            return
        if not self.ctx.get("project.restore_tree_state", True):
            return
        dirs = self.ctx.get("project.expanded_dirs", [])
        if not dirs:
            return
        # Only restore dirs that are under the current project root and exist
        project_str = str(self.project_path.resolve())
        self._pending_expand = {
            d for d in dirs
            if d.startswith(project_str) and Path(d).is_dir()
        }
        if not self._pending_expand:
            return
        self.file_model.directoryLoaded.connect(self._on_directory_loaded)

    def _on_directory_loaded(self, loaded_path: str):
        """When a directory is loaded, expand any pending children of it."""
        logger.debug("Directory loaded: %s", loaded_path)
        if not self._pending_expand:
            self._disconnect_directory_loaded()
            return
        # Find pending dirs that are direct children of loaded_path,
        # or that *are* loaded_path itself.
        newly_expanded = []
        for dir_path in list(self._pending_expand):
            # Expand if this dir is inside (or equal to) the just-loaded dir
            if dir_path == loaded_path or str(Path(dir_path).parent) == loaded_path:
                src = self.file_model.index(dir_path)
                if src.isValid():
                    self.tree_view.expand(self.proxy.mapFromSource(src))
                    newly_expanded.append(dir_path)
        self._pending_expand -= set(newly_expanded)
        if not self._pending_expand:
            self._disconnect_directory_loaded()

    def _disconnect_directory_loaded(self):
        """Safely disconnect the directoryLoaded signal."""
        try:
            self.file_model.directoryLoaded.disconnect(self._on_directory_loaded)
        except RuntimeError:
            # Qt raises RuntimeError when disconnecting a slot that
            # was never connected (or already disconnected). That can
            # happen during cleanup races; intentionally silent.
            pass

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

    def _proxy_to_path(self, index) -> str:
        """Resolve a tree-view index (which may be a proxy or, in tests,
        a source index) into a filesystem path. Tolerating both keeps
        existing tests that pass ``file_model.index(...)`` directly
        working without rewriting every call site."""
        if index.model() is self.proxy:
            index = self.proxy.mapToSource(index)
        return self.file_model.filePath(index)

    def _on_item_clicked(self, index):
        """Handle item click."""
        path = self._proxy_to_path(index)
        if Path(path).is_file():
            self.file_selected.emit(path)

    def _on_item_double_clicked(self, index):
        """Handle item double click."""
        path = self._proxy_to_path(index)
        if Path(path).is_file():
            self.file_double_clicked.emit(path)

    def _is_writable(self, op: str) -> bool:
        """Consult the parent MarkdownEditor's read-only gate. Defensive
        for ProjectPanel uses outside the main window (e.g., tests
        that construct a standalone panel) - those default to writable
        because there's no gate to consult."""
        main = self.window()
        authorize = getattr(main, "_authorize", None)
        if authorize is None:
            return True
        return authorize(op, None)

    def _show_context_menu(self, position):
        """Show context menu. Mutating actions (rename/delete/new) are
        disabled when the app is in read-only mode."""
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            return

        path = Path(self._proxy_to_path(index))
        menu = QMenu(self)

        if path.is_file():
            open_action = menu.addAction("Open")
            open_action.triggered.connect(lambda: self.file_double_clicked.emit(str(path)))

            menu.addSeparator()

            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename_file(path))
            rename_action.setEnabled(self._is_writable("rename_file"))

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._delete_file(path))
            delete_action.setEnabled(self._is_writable("delete_file"))
        else:
            new_file_action = menu.addAction("New File")
            new_file_action.triggered.connect(lambda: self._new_file(path))
            new_file_action.setEnabled(self._is_writable("new_file"))

            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(lambda: self._new_folder(path))
            new_folder_action.setEnabled(self._is_writable("new_folder"))

        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def _new_file(self, folder: Path):
        """Create a new file in the folder."""
        if not self._is_writable("new_file"):
            return
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
                logger.exception(f"Could not create file: {new_path}")
                QMessageBox.critical(self, "Error", f"Could not create file: {e}")

    def _new_folder(self, parent: Path):
        """Create a new folder."""
        if not self._is_writable("new_folder"):
            return
        name, ok = QInputDialog.getText(
            self, "New Folder", "Folder name:"
        )
        if ok and name:
            new_path = parent / name
            try:
                new_path.mkdir(exist_ok=True)
            except OSError as e:
                logger.exception(f"Could not create folder: {new_path}")
                QMessageBox.critical(self, "Error", f"Could not create folder: {e}")

    def _rename_file(self, path: Path):
        """Rename a file."""
        if not self._is_writable("rename_file"):
            return
        name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=path.name
        )
        if ok and name:
            new_path = path.parent / name
            try:
                path.rename(new_path)
            except OSError as e:
                logger.exception(f"Could not rename {path} to {new_path}")
                QMessageBox.critical(self, "Error", f"Could not rename file: {e}")

    def _delete_file(self, path: Path):
        """Delete a file."""
        if not self._is_writable("delete_file"):
            return
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
                logger.exception(f"Could not delete {path}")
                QMessageBox.critical(self, "Error", f"Could not delete file: {e}")

    def _show_export_dialog(self):
        """Show the project export dialog."""
        if not self.project_path:
            QMessageBox.warning(
                self, "No Project", "Please open a project folder first."
            )
            return

        dialog = ProjectExportDialog(self.project_path, self.ctx, self)
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

        max_depth = 2 if self._lazy else None
        return get_project_markdown_files(self.project_path, max_depth=max_depth)


class ProjectExportDialog(QDialog):
    """Dialog for exporting a project to a single document."""

    def __init__(self, project_path: Path, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.project_path = project_path
        self.ctx = ctx
        self._init_ui()
        self._load_files()
        self._apply_theme()

    def _init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Export Project")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # File tree with checkboxes
        file_group = QGroupBox("Files to Include")
        file_layout = QVBoxLayout(file_group)

        self.file_tree = FileTreeWidget()
        file_layout.addWidget(self.file_tree)

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
        theme = get_theme_from_ctx(self.ctx)

        self.setStyleSheet(
            StyleSheets.dialog(theme) +
            StyleSheets.tree_widget(theme) +
            StyleSheets.button(theme) +
            StyleSheets.combo_box(theme) +
            StyleSheets.check_box(theme)
        )

    def _load_files(self):
        """Load project files into the tree.

        Uses the parent panel's get_project_files() when available to
        respect lazy scanning limits.
        """
        parent_panel = self.parent()
        if isinstance(parent_panel, ProjectPanel):
            paths = parent_panel.get_project_files()
        else:
            paths = get_project_markdown_files(self.project_path)
        self.file_tree.load_files(paths, self.project_path)

    def _select_all(self):
        """Select all files."""
        self.file_tree.select_all()

    def _select_none(self):
        """Deselect all files."""
        self.file_tree.select_none()

    def _export(self):
        """Export the project."""
        # Get selected files in order
        files = self.file_tree.get_selected_files()

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

        # Read all files with progress updates, then delegate to the
        # shared combiner — TOC building and page-break insertion are
        # the single source of truth in `export_service.combine_project_markdown`.
        documents: list[tuple[Path, str]] = []
        for i, file_path in enumerate(files):
            if progress.wasCanceled():
                return

            progress.setLabelText(f"Reading: {file_path.name} ({i + 1}/{len(files)})")
            progress.setValue(i)
            QApplication.processEvents()

            documents.append((file_path, file_path.read_text(encoding="utf-8")))

        if progress.wasCanceled():
            return

        combined = export_service.combine_project_markdown(
            documents,
            include_toc=self.include_toc.isChecked(),
            page_breaks=self.page_breaks.isChecked(),
            output_format=("html" if format_type == "html" else "markdown"),
        )
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
                export_service.export_html(combined, output_path, title, ctx=self.ctx)
            elif format_type == "pdf":
                export_service.export_pdf(combined, output_path, title, use_pandoc)
            elif format_type == "docx":
                export_service.export_docx(combined, output_path, title, use_pandoc)

            progress.setValue(total_steps)
            QMessageBox.information(self, "Export Complete", f"Exported to {output_path}")
            self.accept()
        except export_service.ExportError as e:
            progress.close()
            logger.exception("Project export error")
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            progress.close()
            logger.exception("Project export failed")
            QMessageBox.critical(self, "Error", f"Export failed: {e}")

"""Reusable tree widget for displaying project files with checkboxes."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class FileTreeWidget(QTreeWidget):
    """Tree widget that displays files grouped by directory with checkboxes.

    Directories get tri-state checkboxes that reflect/control their children.
    Emits ``selection_changed`` whenever any checkbox changes.
    """

    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._project_path: Path | None = None
        self._updating = False  # guard against recursive check-state updates
        self.itemChanged.connect(self._on_item_changed)

    # --- public API ---

    def load_files(self, files: list[Path], project_path: Path):
        """Populate the tree from a sorted list of absolute file paths.

        Files are grouped into directory nodes based on their path
        relative to *project_path*.  All items start checked.
        """
        self._project_path = project_path
        self.blockSignals(True)
        self.clear()

        dir_items: dict[Path, QTreeWidgetItem] = {}

        for file_path in files:
            rel = file_path.relative_to(project_path)
            parts = rel.parts  # e.g. ("docs", "guide.md") or ("readme.md",)

            if len(parts) == 1:
                # Top-level file
                item = self._make_file_item(parts[0], file_path)
                self.addTopLevelItem(item)
            else:
                # Ensure parent directory chain exists
                parent = self._ensure_dir_chain(parts[:-1], dir_items)
                item = self._make_file_item(parts[-1], file_path)
                parent.addChild(item)

        # Set all directory items to checked (children are already checked)
        for dir_item in dir_items.values():
            dir_item.setCheckState(0, Qt.CheckState.Checked)

        self.collapseAll()
        self.blockSignals(False)

    def select_all(self):
        """Check all items."""
        self._set_all_check_state(Qt.CheckState.Checked)

    def select_none(self):
        """Uncheck all items."""
        self._set_all_check_state(Qt.CheckState.Unchecked)

    def get_selected_files(self) -> list[Path]:
        """Return absolute paths of all checked file (leaf) items, in tree order."""
        result: list[Path] = []
        self._collect_checked(None, result)
        return result

    # --- internal helpers ---

    def _make_file_item(self, name: str, abs_path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.ItemDataRole.UserRole, str(abs_path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        return item

    def _ensure_dir_chain(
        self, parts: tuple[str, ...], cache: dict[Path, QTreeWidgetItem]
    ) -> QTreeWidgetItem:
        """Return (creating if needed) the QTreeWidgetItem for a directory path."""
        cumulative = Path()
        parent_item: QTreeWidgetItem | None = None

        for part in parts:
            cumulative = cumulative / part
            if cumulative in cache:
                parent_item = cache[cumulative]
                continue

            dir_item = QTreeWidgetItem([part])
            dir_item.setFlags(
                dir_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            # Check state will be set after all children are added
            if parent_item is None:
                self.addTopLevelItem(dir_item)
            else:
                parent_item.addChild(dir_item)

            cache[cumulative] = dir_item
            parent_item = dir_item

        return parent_item

    def _set_all_check_state(self, state: Qt.CheckState):
        self.blockSignals(True)
        for i in range(self.topLevelItemCount()):
            self._set_subtree_state(self.topLevelItem(i), state)
        self.blockSignals(False)
        self.selection_changed.emit()

    def _set_subtree_state(self, item: QTreeWidgetItem, state: Qt.CheckState):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_subtree_state(item.child(i), state)

    def _collect_checked(self, parent: QTreeWidgetItem | None, result: list[Path]):
        """Walk the tree and collect checked leaf items."""
        if parent is None:
            count = self.topLevelItemCount()
            get_child = self.topLevelItem
        else:
            count = parent.childCount()
            get_child = parent.child

        for i in range(count):
            item = get_child(i)
            if item.childCount() > 0:
                # Directory node — recurse
                self._collect_checked(item, result)
            else:
                # Leaf (file) node
                if item.checkState(0) == Qt.CheckState.Checked:
                    path_str = item.data(0, Qt.ItemDataRole.UserRole)
                    if path_str:
                        result.append(Path(path_str))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Propagate check state changes and emit signal."""
        if self._updating:
            return
        self._updating = True
        try:
            # If a directory was toggled, propagate to children
            if item.childCount() > 0:
                state = item.checkState(0)
                # Only propagate fully checked / unchecked (not partial)
                if state != Qt.CheckState.PartiallyChecked:
                    self._set_subtree_state(item, state)

            # Update parent chain
            parent = item.parent()
            while parent is not None:
                self._update_parent_state(parent)
                parent = parent.parent()
        finally:
            self._updating = False

        self.selection_changed.emit()

    @staticmethod
    def _update_parent_state(parent: QTreeWidgetItem):
        """Set parent check state based on children."""
        checked = 0
        unchecked = 0
        for i in range(parent.childCount()):
            state = parent.child(i).checkState(0)
            if state == Qt.CheckState.Checked:
                checked += 1
            elif state == Qt.CheckState.Unchecked:
                unchecked += 1
            else:
                # At least one child is partial → parent is partial
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                return

        total = parent.childCount()
        if checked == total:
            parent.setCheckState(0, Qt.CheckState.Checked)
        elif unchecked == total:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

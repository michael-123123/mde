"""Visual table editor for creating and editing markdown tables."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.theme import StyleSheets, get_theme_from_ctx


class TableEditorDialog(QDialog):
    """A dialog for creating and editing markdown tables visually."""

    def __init__(self, ctx=None, parent: QWidget | None = None, initial_markdown: str = ""):
        super().__init__(parent)
        if ctx is None:
            from markdown_editor.markdown6.app_context import get_app_context
            ctx = get_app_context()
        self.ctx = ctx
        self.initial_markdown = initial_markdown
        self._init_ui()
        self._apply_theme()

        if initial_markdown:
            self._parse_markdown_table(initial_markdown)

    def _init_ui(self):
        """Initialize the UI."""
        self.setWindowTitle("Table Editor")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Rows:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 100)
        self.rows_spin.setValue(3)
        self.rows_spin.valueChanged.connect(self._update_table_size)
        controls.addWidget(self.rows_spin)

        controls.addWidget(QLabel("Columns:"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(3)
        self.cols_spin.valueChanged.connect(self._update_table_size)
        controls.addWidget(self.cols_spin)

        controls.addStretch()

        add_row_btn = QPushButton("Add Row")
        add_row_btn.clicked.connect(self._add_row)
        controls.addWidget(add_row_btn)

        add_col_btn = QPushButton("Add Column")
        add_col_btn.clicked.connect(self._add_column)
        controls.addWidget(add_col_btn)

        del_row_btn = QPushButton("Delete Row")
        del_row_btn.clicked.connect(self._delete_row)
        controls.addWidget(del_row_btn)

        del_col_btn = QPushButton("Delete Column")
        del_col_btn.clicked.connect(self._delete_column)
        controls.addWidget(del_col_btn)

        layout.addLayout(controls)

        # Alignment controls
        align_layout = QHBoxLayout()
        align_layout.addWidget(QLabel("Column alignment:"))

        self.alignment_combos: list[QComboBox] = []
        self.alignment_container = QWidget()
        self.alignment_layout = QHBoxLayout(self.alignment_container)
        self.alignment_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.addWidget(self.alignment_container)
        align_layout.addStretch()

        layout.addLayout(align_layout)

        # Table
        self.table = QTableWidget()
        self.table.setRowCount(3)
        self.table.setColumnCount(3)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["Header 1", "Header 2", "Header 3"])
        layout.addWidget(self.table)

        # Update alignments
        self._update_alignment_controls()

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _apply_theme(self):
        """Apply the current theme."""
        theme = get_theme_from_ctx(self.ctx)

        self.setStyleSheet(
            StyleSheets.dialog(theme) +
            StyleSheets.table_widget(theme) +
            StyleSheets.button(theme) +
            StyleSheets.spin_box(theme) +
            StyleSheets.combo_box(theme)
        )

    def _update_table_size(self):
        """Update the table size based on spin boxes."""
        rows = self.rows_spin.value()
        cols = self.cols_spin.value()
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self._update_alignment_controls()

    def _update_alignment_controls(self):
        """Update the alignment combo boxes for each column."""
        # Clear existing
        for combo in self.alignment_combos:
            combo.deleteLater()
        self.alignment_combos.clear()

        # Create new
        for i in range(self.table.columnCount()):
            combo = QComboBox()
            combo.addItems(["Left", "Center", "Right"])
            combo.setFixedWidth(80)
            self.alignment_layout.addWidget(combo)
            self.alignment_combos.append(combo)

    def _add_row(self):
        """Add a row to the table."""
        self.table.insertRow(self.table.rowCount())
        self.rows_spin.setValue(self.table.rowCount())

    def _add_column(self):
        """Add a column to the table."""
        self.table.insertColumn(self.table.columnCount())
        self.cols_spin.setValue(self.table.columnCount())
        self._update_alignment_controls()

    def _delete_row(self):
        """Delete the current row."""
        row = self.table.currentRow()
        if row >= 0 and self.table.rowCount() > 1:
            self.table.removeRow(row)
            self.rows_spin.setValue(self.table.rowCount())

    def _delete_column(self):
        """Delete the current column."""
        col = self.table.currentColumn()
        if col >= 0 and self.table.columnCount() > 1:
            self.table.removeColumn(col)
            self.cols_spin.setValue(self.table.columnCount())
            self._update_alignment_controls()

    def _parse_markdown_table(self, markdown: str):
        """Parse a markdown table and populate the editor."""
        lines = [line.strip() for line in markdown.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return

        # Parse header
        header_cells = [cell.strip() for cell in lines[0].split("|") if cell.strip()]

        # Parse alignment row
        align_row = lines[1] if len(lines) > 1 else ""
        alignments = []
        for cell in align_row.split("|"):
            cell = cell.strip()
            if cell.startswith(":") and cell.endswith(":"):
                alignments.append("Center")
            elif cell.endswith(":"):
                alignments.append("Right")
            else:
                alignments.append("Left")

        # Parse data rows
        data_rows = []
        for line in lines[2:]:
            cells = [cell.strip() for cell in line.split("|") if cell.strip()]
            data_rows.append(cells)

        # Update table
        self.table.setColumnCount(len(header_cells))
        self.table.setRowCount(len(data_rows))
        self.rows_spin.setValue(len(data_rows))
        self.cols_spin.setValue(len(header_cells))

        # Set headers
        self.table.setHorizontalHeaderLabels(header_cells)

        # Set data
        for row_idx, row_data in enumerate(data_rows):
            for col_idx, cell_data in enumerate(row_data):
                if col_idx < len(header_cells):
                    item = QTableWidgetItem(cell_data)
                    self.table.setItem(row_idx, col_idx, item)

        # Update alignment controls
        self._update_alignment_controls()
        for i, alignment in enumerate(alignments):
            if i < len(self.alignment_combos):
                idx = self.alignment_combos[i].findText(alignment)
                if idx >= 0:
                    self.alignment_combos[i].setCurrentIndex(idx)

    def get_markdown(self) -> str:
        """Generate markdown table from the editor contents."""
        rows = self.table.rowCount()
        cols = self.table.columnCount()

        if rows == 0 or cols == 0:
            return ""

        # Calculate column widths
        col_widths = []
        for col in range(cols):
            header = self.table.horizontalHeaderItem(col)
            header_text = header.text() if header else f"Column {col + 1}"
            max_width = len(header_text)

            for row in range(rows):
                item = self.table.item(row, col)
                cell_text = item.text() if item else ""
                max_width = max(max_width, len(cell_text))

            col_widths.append(max(max_width, 3))  # Minimum width of 3

        # Build header row
        headers = []
        for col in range(cols):
            header = self.table.horizontalHeaderItem(col)
            header_text = header.text() if header else f"Column {col + 1}"
            headers.append(header_text.ljust(col_widths[col]))

        header_row = "| " + " | ".join(headers) + " |"

        # Build separator row with alignment
        separators = []
        for col in range(cols):
            width = col_widths[col]
            alignment = self.alignment_combos[col].currentText() if col < len(self.alignment_combos) else "Left"

            if alignment == "Center":
                sep = ":" + "-" * (width - 2) + ":"
            elif alignment == "Right":
                sep = "-" * (width - 1) + ":"
            else:  # Left
                sep = "-" * width

            separators.append(sep)

        separator_row = "| " + " | ".join(separators) + " |"

        # Build data rows
        data_rows = []
        for row in range(rows):
            cells = []
            for col in range(cols):
                item = self.table.item(row, col)
                cell_text = item.text() if item else ""
                cells.append(cell_text.ljust(col_widths[col]))
            data_rows.append("| " + " | ".join(cells) + " |")

        return "\n".join([header_row, separator_row] + data_rows)


def create_table_from_size(rows: int, cols: int) -> str:
    """Create a basic markdown table with the given size."""
    headers = [f"Header {i + 1}" for i in range(cols)]
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * cols) + " |"

    data_rows = []
    for row in range(rows):
        cells = [f"Cell {row + 1},{col + 1}" for col in range(cols)]
        data_rows.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_row, separator_row] + data_rows)

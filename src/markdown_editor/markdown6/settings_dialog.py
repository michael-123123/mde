"""Settings dialog for the Markdown editor."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QFontComboBox,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.app_context import get_app_context, DEFAULT_SETTINGS
from markdown_editor.markdown6.app_context import DEFAULT_SHORTCUTS
from markdown_editor.markdown6.theme import get_theme, StyleSheets


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, ctx=None, parent=None):
        super().__init__(parent)
        if ctx is None:
            ctx = get_app_context()
        self.ctx = ctx
        self.pending_shortcuts = {}

        self.setWindowTitle("Settings")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self._init_ui()
        self._load_settings()
        self._apply_theme()
        # Listen for theme changes
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(
            StyleSheets.dialog(theme) +
            StyleSheets.line_edit(theme) +
            StyleSheets.button(theme) +
            StyleSheets.combo_box(theme) +
            StyleSheets.spin_box(theme) +
            StyleSheets.check_box(theme) +
            StyleSheets.list_widget(theme) +
            StyleSheets.table_widget(theme) +
            StyleSheets.scroll_area(theme)
        )

    def _init_ui(self):
        """Initialize the dialog UI."""
        # Main layout for the dialog
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Splitter for category list and settings panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Category list
        self.category_list = QListWidget()
        self.category_list.setMinimumWidth(120)
        self.category_list.setMaximumWidth(200)
        self.category_list.setSpacing(2)  # Add spacing between items
        self.category_list.currentRowChanged.connect(self._on_category_changed)

        categories = [
            ("Editor", "editor"),
            ("View", "view"),
            ("Appearance", "appearance"),
            ("Files", "files"),
            ("External Tools", "tools"),
            ("Keyboard Shortcuts", "shortcuts"),
        ]

        from PySide6.QtCore import QSize
        for name, _ in categories:
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(-1, 32))  # Explicit height for each item
            self.category_list.addItem(item)

        splitter.addWidget(self.category_list)

        # Stacked widget for settings panels
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.stack.addWidget(self._create_editor_page())
        self.stack.addWidget(self._create_view_page())
        self.stack.addWidget(self._create_appearance_page())
        self.stack.addWidget(self._create_files_page())
        self.stack.addWidget(self._create_tools_page())
        self.stack.addWidget(self._create_shortcuts_page())

        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)  # Category list doesn't stretch
        splitter.setStretchFactor(1, 1)  # Content area stretches
        splitter.setSizes([150, 650])

        main_layout.addWidget(splitter, 1)  # Splitter takes available space

        # Button row at bottom
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        button_layout.addWidget(buttons)

        main_layout.addLayout(button_layout)

        # Select first category
        self.category_list.setCurrentRow(0)

    def _on_category_changed(self, row: int):
        """Handle category selection change."""
        self.stack.setCurrentIndex(row)

    def _create_editor_page(self) -> QWidget:
        """Create the editor settings page."""
        # Scroll area for the page
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        # Font group
        font_group = QGroupBox("Font")
        font_layout = QFormLayout(font_group)

        self.font_family = QLineEdit()
        font_layout.addRow("Font Family:", self.font_family)

        self.font_size = QSpinBox()
        self.font_size.setRange(6, 72)
        font_layout.addRow("Font Size:", self.font_size)

        layout.addWidget(font_group)

        # Tabs group
        tabs_group = QGroupBox("Tabs & Indentation")
        tabs_layout = QFormLayout(tabs_group)

        self.tab_size = QSpinBox()
        self.tab_size.setRange(1, 8)
        tabs_layout.addRow("Tab Size:", self.tab_size)

        self.use_spaces = QCheckBox("Use spaces instead of tabs")
        tabs_layout.addRow("", self.use_spaces)

        self.auto_indent = QCheckBox("Auto-indent new lines")
        tabs_layout.addRow("", self.auto_indent)

        layout.addWidget(tabs_group)

        # Editor behavior group
        behavior_group = QGroupBox("Behavior")
        behavior_layout = QFormLayout(behavior_group)

        self.word_wrap = QCheckBox("Wrap lines")
        behavior_layout.addRow("", self.word_wrap)

        self.auto_pairs = QCheckBox("Auto-close brackets and quotes")
        behavior_layout.addRow("", self.auto_pairs)

        self.highlight_current_line = QCheckBox("Highlight current line")
        behavior_layout.addRow("", self.highlight_current_line)

        self.show_whitespace = QCheckBox("Show whitespace characters")
        behavior_layout.addRow("", self.show_whitespace)

        layout.addWidget(behavior_group)

        # Auto-save group
        autosave_group = QGroupBox("Auto-save")
        autosave_layout = QFormLayout(autosave_group)

        self.auto_save = QCheckBox("Enable auto-save")
        autosave_layout.addRow("", self.auto_save)

        self.auto_save_interval = QSpinBox()
        self.auto_save_interval.setRange(10, 600)
        self.auto_save_interval.setSuffix(" seconds")
        autosave_layout.addRow("Interval:", self.auto_save_interval)

        layout.addWidget(autosave_group)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _create_view_page(self) -> QWidget:
        """Create the view settings page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        # Theme group
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)

        self.theme = QComboBox()
        self.theme.addItems(["Light", "Dark"])
        theme_layout.addRow("Color Theme:", self.theme)

        layout.addWidget(theme_group)

        # Display group
        display_group = QGroupBox("Display")
        display_layout = QFormLayout(display_group)

        self.show_line_numbers = QCheckBox("Show line numbers")
        display_layout.addRow("", self.show_line_numbers)

        self.show_preview = QCheckBox("Show preview pane")
        display_layout.addRow("", self.show_preview)

        self.sync_scrolling = QCheckBox("Sync scrolling between editor and preview")
        display_layout.addRow("", self.sync_scrolling)

        self.scroll_past_end = QCheckBox("Scroll past end of document")
        display_layout.addRow("", self.scroll_past_end)

        layout.addWidget(display_group)

        # Preview group
        preview_group = QGroupBox("Preview")
        preview_layout = QFormLayout(preview_group)

        self.preview_font_size = QSpinBox()
        self.preview_font_size.setRange(8, 32)
        preview_layout.addRow("Font Size:", self.preview_font_size)

        layout.addWidget(preview_group)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _create_font_size_row(self, label: str, key_prefix: str) -> tuple:
        """Create a row with a size spinbox and unit combo for an appearance element.

        Returns (size_spinbox, unit_combo) so they can be stored for load/save.
        """
        size_spin = QDoubleSpinBox()
        size_spin.setRange(0.1, 200.0)
        size_spin.setDecimals(2)
        size_spin.setSingleStep(0.25)

        unit_combo = QComboBox()
        unit_combo.addItems(["em", "%", "px"])

        row = QHBoxLayout()
        row.addWidget(size_spin, 1)
        row.addWidget(unit_combo)

        return size_spin, unit_combo, row

    def _create_appearance_page(self) -> QWidget:
        """Create the appearance settings page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        # Body text group
        body_group = QGroupBox("Body Text")
        body_layout = QFormLayout(body_group)

        self.preview_body_font = QFontComboBox()
        body_layout.addRow("Font Family:", self.preview_body_font)

        self.preview_line_height = QDoubleSpinBox()
        self.preview_line_height.setRange(0.5, 5.0)
        self.preview_line_height.setDecimals(2)
        self.preview_line_height.setSingleStep(0.1)
        body_layout.addRow("Line Height:", self.preview_line_height)

        layout.addWidget(body_group)

        # Headings group
        heading_group = QGroupBox("Headings")
        heading_layout = QFormLayout(heading_group)

        self.preview_heading_font = QFontComboBox()
        heading_layout.addRow("Font Family:", self.preview_heading_font)

        self._heading_controls = {}
        for level in range(1, 7):
            key = f"h{level}"
            spin, combo, row = self._create_font_size_row(f"H{level}:", key)
            heading_layout.addRow(f"H{level} Size:", row)
            self._heading_controls[key] = (spin, combo)

        layout.addWidget(heading_group)

        # Code group
        code_group = QGroupBox("Code")
        code_layout = QFormLayout(code_group)

        self.preview_code_font = QFontComboBox()
        self.preview_code_font.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        code_layout.addRow("Font Family:", self.preview_code_font)

        spin, combo, row = self._create_font_size_row("Code Size:", "code")
        code_layout.addRow("Size:", row)
        self._code_size_spin = spin
        self._code_size_combo = combo

        layout.addWidget(code_group)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _create_files_page(self) -> QWidget:
        """Create the files settings page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        # File handling group
        files_group = QGroupBox("File Handling")
        files_layout = QFormLayout(files_group)

        self.detect_external_changes = QCheckBox("Detect external file changes")
        files_layout.addRow("", self.detect_external_changes)

        self.restore_tree_state = QCheckBox("Restore expanded folders on startup")
        files_layout.addRow("", self.restore_tree_state)

        self.show_hidden_files = QCheckBox("Show hidden files and folders")
        files_layout.addRow("", self.show_hidden_files)

        self.max_recent_files = QSpinBox()
        self.max_recent_files.setRange(1, 50)
        files_layout.addRow("Max recent files:", self.max_recent_files)

        clear_recent_btn = QPushButton("Clear Recent Files")
        clear_recent_btn.clicked.connect(self._clear_recent_files)
        files_layout.addRow("", clear_recent_btn)

        layout.addWidget(files_group)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _create_tool_row(self, label_text: str, line_edit: QLineEdit, tool_cmd: str) -> QHBoxLayout:
        """Create a row with a line edit and browse button for a tool path."""
        row = QHBoxLayout()
        line_edit.setPlaceholderText(f"System default ({tool_cmd})")
        row.addWidget(line_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(lambda: self._browse_tool_path(line_edit))
        row.addWidget(browse_btn)

        detect_btn = QPushButton("Detect")
        detect_btn.setFixedWidth(60)
        detect_btn.clicked.connect(lambda: self._detect_tool(line_edit, tool_cmd))
        row.addWidget(detect_btn)

        return row

    def _browse_tool_path(self, line_edit: QLineEdit):
        """Open a file dialog to select a tool path."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Executable", line_edit.text() or ""
        )
        if path:
            line_edit.setText(path)

    def _detect_tool(self, line_edit: QLineEdit, tool_cmd: str):
        """Auto-detect a tool on the system PATH."""
        import shutil
        found = shutil.which(tool_cmd)
        if found:
            line_edit.setText(found)
        else:
            QMessageBox.warning(
                self, "Not Found",
                f"'{tool_cmd}' was not found on your system PATH."
            )

    def _create_tools_page(self) -> QWidget:
        """Create the external tools settings page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        info = QLabel(
            "Configure paths to external tools. Leave empty to use the system PATH. "
            "Use Browse to select a specific executable, or Detect to find it automatically."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Pandoc
        pandoc_group = QGroupBox("Pandoc (PDF/DOCX export)")
        pandoc_layout = QFormLayout(pandoc_group)
        self.pandoc_path = QLineEdit()
        pandoc_layout.addRow("Path:", self._create_tool_row("Pandoc:", self.pandoc_path, "pandoc"))
        pandoc_desc = QLabel("Used for high-quality PDF and DOCX export. Install: apt install pandoc texlive-xetex")
        pandoc_desc.setWordWrap(True)
        pandoc_desc.setStyleSheet("color: gray; font-size: 11px;")
        pandoc_layout.addRow("", pandoc_desc)
        layout.addWidget(pandoc_group)

        # Graphviz
        dot_group = QGroupBox("Graphviz (DOT diagram rendering)")
        dot_layout = QFormLayout(dot_group)
        self.dot_path = QLineEdit()
        dot_layout.addRow("Path:", self._create_tool_row("Graphviz:", self.dot_path, "dot"))
        dot_desc = QLabel("Renders ```dot and ```graphviz code blocks as SVG diagrams. Install: apt install graphviz")
        dot_desc.setWordWrap(True)
        dot_desc.setStyleSheet("color: gray; font-size: 11px;")
        dot_layout.addRow("", dot_desc)
        layout.addWidget(dot_group)

        # Mermaid
        mmdc_group = QGroupBox("Mermaid CLI (Mermaid diagram rendering)")
        mmdc_layout = QFormLayout(mmdc_group)
        self.mmdc_path = QLineEdit()
        mmdc_layout.addRow("Path:", self._create_tool_row("Mermaid:", self.mmdc_path, "mmdc"))
        mmdc_desc = QLabel("Renders ```mermaid code blocks as SVG diagrams. Install: npm install -g @mermaid-js/mermaid-cli")
        mmdc_desc.setWordWrap(True)
        mmdc_desc.setStyleSheet("color: gray; font-size: 11px;")
        mmdc_layout.addRow("", mmdc_desc)
        layout.addWidget(mmdc_group)

        # Status summary
        self.tools_status = QLabel()
        self.tools_status.setWordWrap(True)
        self._update_tools_status()
        layout.addWidget(self.tools_status)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _update_tools_status(self):
        """Update the tool availability status display."""
        from markdown_editor.markdown6 import tool_paths

        lines = []
        for name, check_fn, install_hint in [
            ("Pandoc", tool_paths.get_pandoc_path, "apt install pandoc"),
            ("Graphviz (dot)", tool_paths.get_dot_path, "apt install graphviz"),
            ("Mermaid (mmdc)", tool_paths.get_mmdc_path, "npm install -g @mermaid-js/mermaid-cli"),
        ]:
            path = check_fn()
            if path:
                lines.append(f"  {name}: {path}")
            else:
                lines.append(f"  {name}: not found ({install_hint})")

        self.tools_status.setText("Tool status:\n" + "\n".join(lines))

    def _create_shortcuts_page(self) -> QWidget:
        """Create the keyboard shortcuts page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        info_label = QLabel(
            "Double-click a shortcut to edit it. "
            "Press Escape to clear a shortcut."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.shortcut_search = QLineEdit()
        self.shortcut_search.setPlaceholderText("Filter shortcuts...")
        self.shortcut_search.textChanged.connect(self._filter_shortcuts)
        search_layout.addWidget(self.shortcut_search)
        layout.addLayout(search_layout)

        # Shortcuts table - this should expand
        self.shortcuts_table = QTableWidget()
        self.shortcuts_table.setColumnCount(3)
        self.shortcuts_table.setHorizontalHeaderLabels(["Action", "Shortcut", "Default"])
        self.shortcuts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.shortcuts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.shortcuts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.shortcuts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.shortcuts_table.cellDoubleClicked.connect(self._edit_shortcut)
        self.shortcuts_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout.addWidget(self.shortcuts_table, 1)  # Stretch factor 1

        # Buttons
        btn_layout = QHBoxLayout()
        reset_shortcuts_btn = QPushButton("Reset All Shortcuts")
        reset_shortcuts_btn.clicked.connect(self._reset_shortcuts)
        btn_layout.addStretch()
        btn_layout.addWidget(reset_shortcuts_btn)
        layout.addLayout(btn_layout)

        return page

    def _load_settings(self):
        """Load current settings into the UI."""
        # Editor settings
        self.font_family.setText(self.ctx.get("editor.font_family", "Monospace"))
        self.font_size.setValue(self.ctx.get("editor.font_size", 11))
        self.tab_size.setValue(self.ctx.get("editor.tab_size", 4))
        self.use_spaces.setChecked(self.ctx.get("editor.use_spaces", True))
        self.auto_indent.setChecked(self.ctx.get("editor.auto_indent", True))
        self.word_wrap.setChecked(self.ctx.get("editor.word_wrap", True))
        self.auto_pairs.setChecked(self.ctx.get("editor.auto_pairs", True))
        self.highlight_current_line.setChecked(
            self.ctx.get("editor.highlight_current_line", True)
        )
        self.show_whitespace.setChecked(self.ctx.get("editor.show_whitespace", False))
        self.auto_save.setChecked(self.ctx.get("editor.auto_save", False))
        self.auto_save_interval.setValue(self.ctx.get("editor.auto_save_interval", 60))

        # View settings
        theme = self.ctx.get("view.theme", "light")
        self.theme.setCurrentIndex(0 if theme == "light" else 1)
        self.show_line_numbers.setChecked(self.ctx.get("editor.show_line_numbers", True))
        self.show_preview.setChecked(self.ctx.get("view.show_preview", True))
        self.sync_scrolling.setChecked(self.ctx.get("view.sync_scrolling", True))
        self.scroll_past_end.setChecked(self.ctx.get("editor.scroll_past_end", True))
        self.preview_font_size.setValue(self.ctx.get("view.preview_font_size", 14))

        # Files settings
        self.detect_external_changes.setChecked(
            self.ctx.get("files.detect_external_changes", True)
        )
        self.restore_tree_state.setChecked(
            self.ctx.get("project.restore_tree_state", True)
        )
        self.show_hidden_files.setChecked(
            self.ctx.get("files.show_hidden", False)
        )
        self.max_recent_files.setValue(self.ctx.get("files.max_recent_files", 10))

        # External tools settings
        self.pandoc_path.setText(self.ctx.get("tools.pandoc_path", ""))
        self.dot_path.setText(self.ctx.get("tools.dot_path", ""))
        self.mmdc_path.setText(self.ctx.get("tools.mmdc_path", ""))

        # Appearance
        from PySide6.QtGui import QFont, QFontDatabase
        body_font_name = self.ctx.get("preview.body_font_family", "")
        if not body_font_name:
            # Resolve the default system font
            body_font_name = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        self.preview_body_font.setCurrentFont(QFont(body_font_name))

        heading_font_name = self.ctx.get("preview.heading_font_family", "")
        if heading_font_name:
            self.preview_heading_font.setCurrentFont(QFont(heading_font_name))
        else:
            # Show same as body when inheriting
            self.preview_heading_font.setCurrentFont(QFont(body_font_name))
        self._heading_font_customized = bool(self.ctx.get("preview.heading_font_family", ""))

        code_font_name = self.ctx.get("preview.code_font_family", "")
        if not code_font_name:
            code_font_name = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        self.preview_code_font.setCurrentFont(QFont(code_font_name))
        self.preview_line_height.setValue(self.ctx.get("preview.line_height", 1.5))
        for level in range(1, 7):
            key = f"h{level}"
            spin, combo = self._heading_controls[key]
            spin.setValue(self.ctx.get(f"preview.{key}_size", 1.0))
            unit = self.ctx.get(f"preview.{key}_size_unit", "em")
            combo.setCurrentText(unit)
        self._code_size_spin.setValue(self.ctx.get("preview.code_size", 85))
        self._code_size_combo.setCurrentText(self.ctx.get("preview.code_size_unit", "%"))

        # Load shortcuts
        self._populate_shortcuts_table()

    def _populate_shortcuts_table(self):
        """Populate the shortcuts table."""
        self.shortcuts_table.setRowCount(0)

        shortcuts = self.ctx.get_all_shortcuts()

        # Group shortcuts by category
        categories = {
            "file": "File",
            "edit": "Edit",
            "markdown": "Markdown",
            "view": "View",
            "tabs": "Tabs",
            "find": "Find",
        }

        sorted_shortcuts = sorted(shortcuts.items(), key=lambda x: x[0])

        for action, shortcut in sorted_shortcuts:
            row = self.shortcuts_table.rowCount()
            self.shortcuts_table.insertRow(row)

            # Format action name
            parts = action.split(".")
            if len(parts) >= 2:
                category = categories.get(parts[0], parts[0].title())
                name = parts[1].replace("_", " ").title()
                display_name = f"{category}: {name}"
            else:
                display_name = action.replace("_", " ").title()

            action_item = QTableWidgetItem(display_name)
            action_item.setData(Qt.ItemDataRole.UserRole, action)
            action_item.setFlags(action_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.shortcuts_table.setItem(row, 0, action_item)

            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setFlags(shortcut_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.shortcuts_table.setItem(row, 1, shortcut_item)

            default = DEFAULT_SHORTCUTS.get(action, "")
            default_item = QTableWidgetItem(default)
            default_item.setFlags(default_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            default_item.setForeground(Qt.GlobalColor.gray)
            self.shortcuts_table.setItem(row, 2, default_item)

    def _filter_shortcuts(self, text: str):
        """Filter the shortcuts table."""
        text = text.lower()
        for row in range(self.shortcuts_table.rowCount()):
            action_item = self.shortcuts_table.item(row, 0)
            shortcut_item = self.shortcuts_table.item(row, 1)

            visible = (
                text in action_item.text().lower() or
                text in shortcut_item.text().lower()
            )
            self.shortcuts_table.setRowHidden(row, not visible)

    def _edit_shortcut(self, row: int, column: int):
        """Edit a shortcut."""
        if column != 1:
            return

        action_item = self.shortcuts_table.item(row, 0)
        action = action_item.data(Qt.ItemDataRole.UserRole)
        current_shortcut = self.shortcuts_table.item(row, 1).text()

        dialog = ShortcutEditDialog(action, current_shortcut, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_shortcut = dialog.get_shortcut()
            self.shortcuts_table.item(row, 1).setText(new_shortcut)
            self.pending_shortcuts[action] = new_shortcut

    def _reset_shortcuts(self):
        """Reset all shortcuts to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Shortcuts",
            "Are you sure you want to reset all keyboard shortcuts to their defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.ctx.reset_shortcuts()
            self.pending_shortcuts.clear()
            self._populate_shortcuts_table()

    def _clear_recent_files(self):
        """Clear the recent files list."""
        self.ctx.clear_recent_files()
        QMessageBox.information(self, "Recent Files", "Recent files list cleared.")

    def _reset_to_defaults(self):
        """Reset all settings to defaults by removing config files."""
        reply = QMessageBox.question(
            self,
            "Restore Default Settings",
            "This will delete your saved settings and keyboard shortcuts, "
            "restoring everything to factory defaults.\n\n"
            "Config files will be removed from:\n"
            f"{self.ctx.config_dir}\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.ctx.restore_all_defaults()
            self.pending_shortcuts.clear()
            self._load_settings()
            QMessageBox.information(
                self,
                "Settings Restored",
                "All settings have been restored to defaults."
            )

    def _apply(self):
        """Apply the current settings."""
        # Editor settings
        self.ctx.set("editor.font_family", self.font_family.text())
        self.ctx.set("editor.font_size", self.font_size.value())
        self.ctx.set("editor.tab_size", self.tab_size.value())
        self.ctx.set("editor.use_spaces", self.use_spaces.isChecked())
        self.ctx.set("editor.auto_indent", self.auto_indent.isChecked())
        self.ctx.set("editor.word_wrap", self.word_wrap.isChecked())
        self.ctx.set("editor.auto_pairs", self.auto_pairs.isChecked())
        self.ctx.set("editor.highlight_current_line", self.highlight_current_line.isChecked())
        self.ctx.set("editor.show_whitespace", self.show_whitespace.isChecked())
        self.ctx.set("editor.auto_save", self.auto_save.isChecked())
        self.ctx.set("editor.auto_save_interval", self.auto_save_interval.value())

        # View settings
        self.ctx.set("view.theme", "light" if self.theme.currentIndex() == 0 else "dark")
        self.ctx.set("editor.show_line_numbers", self.show_line_numbers.isChecked())
        self.ctx.set("view.show_preview", self.show_preview.isChecked())
        self.ctx.set("view.sync_scrolling", self.sync_scrolling.isChecked())
        self.ctx.set("editor.scroll_past_end", self.scroll_past_end.isChecked())
        self.ctx.set("view.preview_font_size", self.preview_font_size.value())

        # Files settings
        self.ctx.set("files.detect_external_changes", self.detect_external_changes.isChecked())
        self.ctx.set("project.restore_tree_state", self.restore_tree_state.isChecked())
        self.ctx.set("files.show_hidden", self.show_hidden_files.isChecked())
        self.ctx.set("files.max_recent_files", self.max_recent_files.value())

        # External tools settings
        self.ctx.set("tools.pandoc_path", self.pandoc_path.text().strip())
        self.ctx.set("tools.dot_path", self.dot_path.text().strip())
        self.ctx.set("tools.mmdc_path", self.mmdc_path.text().strip())

        # Appearance
        self.ctx.set("preview.body_font_family", self.preview_body_font.currentFont().family())
        # Only save heading font if user changed it from the body default
        heading_family = self.preview_heading_font.currentFont().family()
        body_family = self.preview_body_font.currentFont().family()
        if heading_family != body_family or self._heading_font_customized:
            self.ctx.set("preview.heading_font_family", heading_family)
        else:
            self.ctx.set("preview.heading_font_family", "")
        self.ctx.set("preview.code_font_family", self.preview_code_font.currentFont().family())
        self.ctx.set("preview.line_height", self.preview_line_height.value())
        for level in range(1, 7):
            key = f"h{level}"
            spin, combo = self._heading_controls[key]
            self.ctx.set(f"preview.{key}_size", spin.value())
            self.ctx.set(f"preview.{key}_size_unit", combo.currentText())
        self.ctx.set("preview.code_size", self._code_size_spin.value())
        self.ctx.set("preview.code_size_unit", self._code_size_combo.currentText())

        # Shortcuts
        for action, shortcut in self.pending_shortcuts.items():
            self.ctx.set_shortcut(action, shortcut)

        self.pending_shortcuts.clear()

    def _accept(self):
        """Accept and close the dialog."""
        self._apply()
        self.accept()


class ShortcutEditDialog(QDialog):
    """Dialog for editing a single shortcut."""

    def __init__(self, action: str, current: str, parent=None):
        super().__init__(parent)
        self.action = action
        self.setWindowTitle("Edit Shortcut")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Instructions
        layout.addWidget(QLabel(f"Enter new shortcut for: {action}"))
        layout.addWidget(QLabel("Press Escape to clear the shortcut."))

        # Shortcut input
        self.shortcut_edit = QKeySequenceEdit()
        if current:
            self.shortcut_edit.setKeySequence(QKeySequence(current))
        layout.addWidget(self.shortcut_edit)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_shortcut)
        layout.addWidget(clear_btn)

    def _clear_shortcut(self):
        """Clear the shortcut."""
        self.shortcut_edit.clear()

    def get_shortcut(self) -> str:
        """Get the entered shortcut."""
        return self.shortcut_edit.keySequence().toString()

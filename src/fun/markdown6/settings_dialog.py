"""Settings dialog for the Markdown editor."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fun.markdown6.settings import get_settings, DEFAULT_SETTINGS, DEFAULT_SHORTCUTS
from fun.markdown6.theme import get_theme, StyleSheets


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.pending_shortcuts = {}

        self.setWindowTitle("Settings")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)

        self._init_ui()
        self._load_settings()
        self._apply_theme()
        # Listen for theme changes
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.settings.get("view.theme", "light")
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
            ("Files", "files"),
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
        self.stack.addWidget(self._create_files_page())
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
        self.font_family.setText(self.settings.get("editor.font_family", "Monospace"))
        self.font_size.setValue(self.settings.get("editor.font_size", 11))
        self.tab_size.setValue(self.settings.get("editor.tab_size", 4))
        self.use_spaces.setChecked(self.settings.get("editor.use_spaces", True))
        self.auto_indent.setChecked(self.settings.get("editor.auto_indent", True))
        self.word_wrap.setChecked(self.settings.get("editor.word_wrap", True))
        self.auto_pairs.setChecked(self.settings.get("editor.auto_pairs", True))
        self.highlight_current_line.setChecked(
            self.settings.get("editor.highlight_current_line", True)
        )
        self.show_whitespace.setChecked(self.settings.get("editor.show_whitespace", False))
        self.auto_save.setChecked(self.settings.get("editor.auto_save", False))
        self.auto_save_interval.setValue(self.settings.get("editor.auto_save_interval", 60))

        # View settings
        theme = self.settings.get("view.theme", "light")
        self.theme.setCurrentIndex(0 if theme == "light" else 1)
        self.show_line_numbers.setChecked(self.settings.get("editor.show_line_numbers", True))
        self.show_preview.setChecked(self.settings.get("view.show_preview", True))
        self.sync_scrolling.setChecked(self.settings.get("view.sync_scrolling", True))
        self.preview_font_size.setValue(self.settings.get("view.preview_font_size", 14))

        # Files settings
        self.detect_external_changes.setChecked(
            self.settings.get("files.detect_external_changes", True)
        )
        self.max_recent_files.setValue(self.settings.get("files.max_recent_files", 10))

        # Load shortcuts
        self._populate_shortcuts_table()

    def _populate_shortcuts_table(self):
        """Populate the shortcuts table."""
        self.shortcuts_table.setRowCount(0)

        shortcuts = self.settings.get_all_shortcuts()

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
            self.settings.reset_shortcuts()
            self.pending_shortcuts.clear()
            self._populate_shortcuts_table()

    def _clear_recent_files(self):
        """Clear the recent files list."""
        self.settings.clear_recent_files()
        QMessageBox.information(self, "Recent Files", "Recent files list cleared.")

    def _reset_to_defaults(self):
        """Reset all settings to defaults by removing config files."""
        reply = QMessageBox.question(
            self,
            "Restore Default Settings",
            "This will delete your saved settings and keyboard shortcuts, "
            "restoring everything to factory defaults.\n\n"
            "Config files will be removed from:\n"
            f"{self.settings.config_dir}\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.restore_all_defaults()
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
        self.settings.set("editor.font_family", self.font_family.text())
        self.settings.set("editor.font_size", self.font_size.value())
        self.settings.set("editor.tab_size", self.tab_size.value())
        self.settings.set("editor.use_spaces", self.use_spaces.isChecked())
        self.settings.set("editor.auto_indent", self.auto_indent.isChecked())
        self.settings.set("editor.word_wrap", self.word_wrap.isChecked())
        self.settings.set("editor.auto_pairs", self.auto_pairs.isChecked())
        self.settings.set("editor.highlight_current_line", self.highlight_current_line.isChecked())
        self.settings.set("editor.show_whitespace", self.show_whitespace.isChecked())
        self.settings.set("editor.auto_save", self.auto_save.isChecked())
        self.settings.set("editor.auto_save_interval", self.auto_save_interval.value())

        # View settings
        self.settings.set("view.theme", "light" if self.theme.currentIndex() == 0 else "dark")
        self.settings.set("editor.show_line_numbers", self.show_line_numbers.isChecked())
        self.settings.set("view.show_preview", self.show_preview.isChecked())
        self.settings.set("view.sync_scrolling", self.sync_scrolling.isChecked())
        self.settings.set("view.preview_font_size", self.preview_font_size.value())

        # Files settings
        self.settings.set("files.detect_external_changes", self.detect_external_changes.isChecked())
        self.settings.set("files.max_recent_files", self.max_recent_files.value())

        # Shortcuts
        for action, shortcut in self.pending_shortcuts.items():
            self.settings.set_shortcut(action, shortcut)

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

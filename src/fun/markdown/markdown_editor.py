"""A feature-rich Qt5 Markdown editor with split-screen editing and preview."""

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QKeySequence, QTextCursor, QTextDocument
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension
from pygments.formatters import HtmlFormatter

from fun.markdown.enhanced_editor import EnhancedEditor
from fun.markdown.settings import get_settings
from fun.markdown.settings_dialog import SettingsDialog


class FindReplaceBar(QWidget):
    """A find/replace bar widget."""

    def __init__(self, editor: EnhancedEditor, parent: QWidget | None = None):
        super().__init__(parent)
        self.editor = editor
        self.last_search = ""
        self._init_ui()
        self.hide()

    def _init_ui(self):
        """Set up the find/replace bar UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Find row
        find_row = QHBoxLayout()
        find_row.setSpacing(4)

        find_label = QLabel("Find:")
        find_label.setFixedWidth(60)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search text...")
        self.find_input.returnPressed.connect(self.find_next)
        self.find_input.textChanged.connect(self._on_search_text_changed)

        self.case_checkbox = QCheckBox("Case sensitive")
        self.whole_word_checkbox = QCheckBox("Whole word")

        self.find_prev_btn = QPushButton("Previous")
        self.find_prev_btn.clicked.connect(self.find_previous)
        self.find_next_btn = QPushButton("Next")
        self.find_next_btn.clicked.connect(self.find_next)

        self.match_label = QLabel("")
        self.match_label.setMinimumWidth(80)

        close_btn = QPushButton("×")
        close_btn.setFixedWidth(24)
        close_btn.clicked.connect(self.hide_bar)

        find_row.addWidget(find_label)
        find_row.addWidget(self.find_input, 1)
        find_row.addWidget(self.case_checkbox)
        find_row.addWidget(self.whole_word_checkbox)
        find_row.addWidget(self.find_prev_btn)
        find_row.addWidget(self.find_next_btn)
        find_row.addWidget(self.match_label)
        find_row.addWidget(close_btn)

        layout.addLayout(find_row)

        # Replace row
        replace_row = QHBoxLayout()
        replace_row.setSpacing(4)

        replace_label = QLabel("Replace:")
        replace_label.setFixedWidth(60)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        self.replace_input.returnPressed.connect(self.replace_next)

        self.replace_btn = QPushButton("Replace")
        self.replace_btn.clicked.connect(self.replace_next)
        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.clicked.connect(self.replace_all)

        replace_row.addWidget(replace_label)
        replace_row.addWidget(self.replace_input, 1)
        replace_row.addWidget(self.replace_btn)
        replace_row.addWidget(self.replace_all_btn)
        replace_row.addStretch()

        self.replace_row_widget = QWidget()
        self.replace_row_widget.setLayout(replace_row)
        layout.addWidget(self.replace_row_widget)

    def show_find(self):
        """Show the find bar (hide replace row)."""
        self.replace_row_widget.hide()
        self.show()
        self.find_input.setFocus()
        self.find_input.selectAll()
        self._select_current_word()

    def show_replace(self):
        """Show the find and replace bar."""
        self.replace_row_widget.show()
        self.show()
        self.find_input.setFocus()
        self.find_input.selectAll()
        self._select_current_word()

    def hide_bar(self):
        """Hide the find/replace bar."""
        self.hide()
        self.editor.setFocus()

    def _select_current_word(self):
        """Pre-fill search with selected text or word under cursor."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_input.setText(cursor.selectedText())
        else:
            cursor.select(QTextCursor.WordUnderCursor)
            word = cursor.selectedText()
            if word:
                self.find_input.setText(word)

    def _on_search_text_changed(self, text: str):
        """Handle search text changes for live search."""
        if text:
            self._find(text, forward=True, wrap=True, from_start=True)
        else:
            self.match_label.setText("")

    def _get_find_flags(self) -> QTextDocument.FindFlags:
        """Get the current find flags based on checkboxes."""
        flags = QTextDocument.FindFlags()
        if self.case_checkbox.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.whole_word_checkbox.isChecked():
            flags |= QTextDocument.FindWholeWords
        return flags

    def _find(
        self,
        text: str,
        forward: bool = True,
        wrap: bool = True,
        from_start: bool = False,
    ) -> bool:
        """Perform the find operation."""
        if not text:
            return False

        flags = self._get_find_flags()
        if not forward:
            flags |= QTextDocument.FindBackward

        cursor = self.editor.textCursor()
        if from_start:
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)

        found = self.editor.find(text, flags)

        if not found and wrap:
            cursor = self.editor.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.Start)
            else:
                cursor.movePosition(QTextCursor.End)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, flags)

        if found:
            self.match_label.setText("Found")
            self.match_label.setStyleSheet("color: green;")
        else:
            self.match_label.setText("Not found")
            self.match_label.setStyleSheet("color: red;")

        self.last_search = text
        return found

    def find_next(self):
        """Find next occurrence."""
        text = self.find_input.text()
        self._find(text, forward=True, wrap=True)

    def find_previous(self):
        """Find previous occurrence."""
        text = self.find_input.text()
        self._find(text, forward=False, wrap=True)

    def replace_next(self):
        """Replace current selection and find next."""
        text = self.find_input.text()
        replacement = self.replace_input.text()

        if not text:
            return

        cursor = self.editor.textCursor()

        if cursor.hasSelection():
            selected = cursor.selectedText()
            if self.case_checkbox.isChecked():
                match = selected == text
            else:
                match = selected.lower() == text.lower()

            if match:
                cursor.insertText(replacement)

        self.find_next()

    def replace_all(self):
        """Replace all occurrences."""
        text = self.find_input.text()
        replacement = self.replace_input.text()

        if not text:
            return

        flags = self._get_find_flags()
        count = 0

        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)

        cursor = self.editor.textCursor()
        cursor.beginEditBlock()

        while self.editor.find(text, flags):
            tc = self.editor.textCursor()
            tc.insertText(replacement)
            count += 1

        cursor.endEditBlock()

        self.match_label.setText(f"Replaced {count}")
        self.match_label.setStyleSheet("color: blue;")

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
        elif event.key() == Qt.Key_F3:
            if event.modifiers() & Qt.ShiftModifier:
                self.find_previous()
            else:
                self.find_next()
        else:
            super().keyPressEvent(event)


class DocumentTab(QWidget):
    """A single document tab with editor and preview panes."""

    def __init__(self, parent: "MarkdownEditor"):
        super().__init__()
        self.main_window = parent
        self.settings = get_settings()
        self.file_path: Path | None = None
        self.unsaved_changes = False
        self._sync_scrolling = True

        self._init_ui()
        self._init_timer()
        self._connect_signals()

    def _init_ui(self):
        """Set up the tab's user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter with editor and preview
        self.splitter = QSplitter(Qt.Horizontal)

        # Editor container (editor + minimap + find bar)
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Editor with minimap
        editor_with_minimap = QWidget()
        ewm_layout = QHBoxLayout(editor_with_minimap)
        ewm_layout.setContentsMargins(0, 0, 0, 0)
        ewm_layout.setSpacing(0)

        self.editor = EnhancedEditor()
        self.editor.setAcceptDrops(True)

        ewm_layout.addWidget(self.editor)
        ewm_layout.addWidget(self.editor.minimap)

        self.find_replace_bar = FindReplaceBar(self.editor, self)

        editor_layout.addWidget(editor_with_minimap)
        editor_layout.addWidget(self.find_replace_bar)

        # Preview pane - use QWebEngineView if available for better CSS support
        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
            self._use_webengine = True
        else:
            self.preview = QTextBrowser()
            self.preview.setOpenExternalLinks(True)
            self._use_webengine = False
        self._apply_preview_style()

        self.splitter.addWidget(editor_container)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([600, 600])

        layout.addWidget(self.splitter)

        # Apply settings
        self._apply_settings()

    def _apply_preview_style(self):
        """Apply styling to the preview pane."""
        # QWebEngineView styling is done via HTML/CSS, not widget stylesheet
        if self._use_webengine:
            return

        # QTextBrowser widget styling
        theme = self.settings.get("view.theme", "light")
        if theme == "dark":
            self.preview.setStyleSheet("""
                QTextBrowser {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    padding: 20px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: 14px;
                }
            """)
        else:
            self.preview.setStyleSheet("""
                QTextBrowser {
                    background-color: #ffffff;
                    padding: 20px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: 14px;
                }
            """)

    def _apply_settings(self):
        """Apply current settings."""
        self.preview.setVisible(self.settings.get("view.show_preview", True))
        self._sync_scrolling = self.settings.get("view.sync_scrolling", True)

    def _init_timer(self):
        """Initialize the render debounce timer."""
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render_markdown)

    def _connect_signals(self):
        """Connect signals."""
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.file_externally_modified.connect(self._on_file_externally_modified)
        self.settings.settings_changed.connect(self._on_setting_changed)

        # Sync scrolling
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scroll)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.show_preview":
            self.preview.setVisible(value)
        elif key == "view.sync_scrolling":
            self._sync_scrolling = value
        elif key == "view.theme":
            self._apply_preview_style()
            # Re-render preview with new theme
            self.render_markdown()
        elif key == "view.preview_font_size":
            # Re-render preview with new font size
            self.render_markdown()

    def _on_text_changed(self):
        """Handle text changes in the editor."""
        if not self.unsaved_changes:
            self.unsaved_changes = True
            self.main_window.update_tab_title(self)
            self.main_window.update_window_title()
        self.render_timer.start(300)

    def _on_file_externally_modified(self):
        """Handle external file modification."""
        reply = QMessageBox.question(
            self,
            "File Changed",
            f"The file '{self.file_path.name}' has been modified outside the editor.\n"
            "Do you want to reload it?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Yes:
            self.reload_file()

    def _on_editor_scroll(self):
        """Handle editor scroll for sync scrolling."""
        if self._sync_scrolling and self.preview.isVisible():
            ratio = self.editor.get_scroll_ratio()
            if self._use_webengine:
                # Use JavaScript to scroll QWebEngineView
                js = f"window.scrollTo(0, document.body.scrollHeight * {ratio});"
                self.preview.page().runJavaScript(js)
            else:
                preview_scrollbar = self.preview.verticalScrollBar()
                preview_scrollbar.setValue(int(ratio * preview_scrollbar.maximum()))

    def render_markdown(self):
        """Convert markdown to HTML and display in preview pane."""
        text = self.editor.toPlainText()
        self.main_window.md.reset()
        html_content = self.main_window.md.convert(text)
        full_html = self.main_window.get_html_template(html_content)
        self.preview.setHtml(full_html)

    def reload_file(self):
        """Reload the file from disk."""
        if self.file_path and self.file_path.exists():
            content = self.file_path.read_text(encoding="utf-8")
            self.editor.setPlainText(content)
            self.unsaved_changes = False
            self.main_window.update_tab_title(self)

    def get_tab_title(self) -> str:
        """Return the title for this tab."""
        if self.file_path:
            name = self.file_path.name
        else:
            name = "Untitled"
        if self.unsaved_changes:
            name = f"*{name}"
        return name

    def show_find(self):
        """Show the find bar."""
        self.find_replace_bar.show_find()

    def show_replace(self):
        """Show the find and replace bar."""
        self.find_replace_bar.show_replace()


class MarkdownEditor(QMainWindow):
    """A tabbed Markdown editor with split-screen editing and preview."""

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._is_fullscreen = False
        self._init_markdown()
        self._init_ui()
        self._init_actions()
        self._init_shortcuts()
        self._connect_signals()
        self.new_tab()
        self._update_recent_files_menu()

    def _init_markdown(self):
        """Initialize the Markdown converter with extensions."""
        self.md = markdown.Markdown(
            extensions=[
                "extra",
                FencedCodeExtension(),
                CodeHiliteExtension(css_class="highlight", guess_lang=True),
                TableExtension(),
                TocExtension(),
                "sane_lists",
            ]
        )

    def _init_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Markdown Editor")
        self.setGeometry(100, 100, 1200, 800)
        self.setAcceptDrops(True)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tab_widget)

        self._create_menu_bar()
        self._create_status_bar()

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.new_action = file_menu.addAction("&New Tab")
        self.new_action.triggered.connect(self.new_tab)

        self.open_action = file_menu.addAction("&Open...")
        self.open_action.triggered.connect(self.open_file)

        # Recent files submenu
        self.recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()

        self.save_action = file_menu.addAction("&Save")
        self.save_action.triggered.connect(self.save_file)

        self.save_as_action = file_menu.addAction("Save &As...")
        self.save_as_action.triggered.connect(self.save_file_as)

        file_menu.addSeparator()

        self.export_html_action = file_menu.addAction("Export to &HTML...")
        self.export_html_action.triggered.connect(self._export_html)

        file_menu.addSeparator()

        self.close_tab_action = file_menu.addAction("&Close Tab")
        self.close_tab_action.triggered.connect(self._close_current_tab)

        file_menu.addSeparator()

        self.quit_action = file_menu.addAction("&Quit")
        self.quit_action.triggered.connect(self.close)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self.undo_action = edit_menu.addAction("&Undo")
        self.undo_action.triggered.connect(self._undo)

        self.redo_action = edit_menu.addAction("&Redo")
        self.redo_action.triggered.connect(self._redo)

        edit_menu.addSeparator()

        self.cut_action = edit_menu.addAction("Cu&t")
        self.cut_action.triggered.connect(self._cut)

        self.copy_action = edit_menu.addAction("&Copy")
        self.copy_action.triggered.connect(self._copy)

        self.paste_action = edit_menu.addAction("&Paste")
        self.paste_action.triggered.connect(self._paste)

        self.select_all_action = edit_menu.addAction("Select &All")
        self.select_all_action.triggered.connect(self._select_all)

        edit_menu.addSeparator()

        self.find_action = edit_menu.addAction("&Find...")
        self.find_action.triggered.connect(self._show_find)

        self.replace_action = edit_menu.addAction("&Replace...")
        self.replace_action.triggered.connect(self._show_replace)

        self.go_to_line_action = edit_menu.addAction("&Go to Line...")
        self.go_to_line_action.triggered.connect(self._go_to_line)

        edit_menu.addSeparator()

        self.duplicate_line_action = edit_menu.addAction("&Duplicate Line")
        self.duplicate_line_action.triggered.connect(self._duplicate_line)

        self.delete_line_action = edit_menu.addAction("De&lete Line")
        self.delete_line_action.triggered.connect(self._delete_line)

        self.move_line_up_action = edit_menu.addAction("Move Line &Up")
        self.move_line_up_action.triggered.connect(self._move_line_up)

        self.move_line_down_action = edit_menu.addAction("Move Line &Down")
        self.move_line_down_action.triggered.connect(self._move_line_down)

        edit_menu.addSeparator()

        self.toggle_comment_action = edit_menu.addAction("Toggle &Comment")
        self.toggle_comment_action.triggered.connect(self._toggle_comment)

        edit_menu.addSeparator()

        self.settings_action = edit_menu.addAction("Se&ttings...")
        self.settings_action.triggered.connect(self._show_settings)

        # Format menu (Markdown)
        format_menu = menubar.addMenu("F&ormat")

        self.bold_action = format_menu.addAction("&Bold")
        self.bold_action.triggered.connect(self._format_bold)

        self.italic_action = format_menu.addAction("&Italic")
        self.italic_action.triggered.connect(self._format_italic)

        self.code_action = format_menu.addAction("&Code")
        self.code_action.triggered.connect(self._format_code)

        format_menu.addSeparator()

        self.link_action = format_menu.addAction("Insert &Link")
        self.link_action.triggered.connect(self._format_link)

        self.image_action = format_menu.addAction("Insert &Image")
        self.image_action.triggered.connect(self._format_image)

        format_menu.addSeparator()

        self.heading_increase_action = format_menu.addAction("Increase &Heading Level")
        self.heading_increase_action.triggered.connect(self._heading_increase)

        self.heading_decrease_action = format_menu.addAction("&Decrease Heading Level")
        self.heading_decrease_action.triggered.connect(self._heading_decrease)

        # View menu
        view_menu = menubar.addMenu("&View")

        self.refresh_action = view_menu.addAction("&Refresh Preview")
        self.refresh_action.triggered.connect(self._refresh_preview)

        view_menu.addSeparator()

        self.toggle_preview_action = view_menu.addAction("Toggle &Preview")
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(self.settings.get("view.show_preview", True))
        self.toggle_preview_action.triggered.connect(self._toggle_preview)

        self.toggle_minimap_action = view_menu.addAction("Toggle &Minimap")
        self.toggle_minimap_action.setCheckable(True)
        self.toggle_minimap_action.setChecked(self.settings.get("view.show_minimap", False))
        self.toggle_minimap_action.triggered.connect(self._toggle_minimap)

        self.toggle_line_numbers_action = view_menu.addAction("Toggle &Line Numbers")
        self.toggle_line_numbers_action.setCheckable(True)
        self.toggle_line_numbers_action.setChecked(self.settings.get("editor.show_line_numbers", True))
        self.toggle_line_numbers_action.triggered.connect(self._toggle_line_numbers)

        self.toggle_word_wrap_action = view_menu.addAction("Toggle &Word Wrap")
        self.toggle_word_wrap_action.setCheckable(True)
        self.toggle_word_wrap_action.setChecked(self.settings.get("editor.word_wrap", True))
        self.toggle_word_wrap_action.triggered.connect(self._toggle_word_wrap)

        self.toggle_whitespace_action = view_menu.addAction("Toggle Whi&tespace")
        self.toggle_whitespace_action.setCheckable(True)
        self.toggle_whitespace_action.setChecked(self.settings.get("editor.show_whitespace", False))
        self.toggle_whitespace_action.triggered.connect(self._toggle_whitespace)

        view_menu.addSeparator()

        self.zoom_in_action = view_menu.addAction("Zoom &In")
        self.zoom_in_action.triggered.connect(self._zoom_in)

        self.zoom_out_action = view_menu.addAction("Zoom &Out")
        self.zoom_out_action.triggered.connect(self._zoom_out)

        self.zoom_reset_action = view_menu.addAction("&Reset Zoom")
        self.zoom_reset_action.triggered.connect(self._zoom_reset)

        view_menu.addSeparator()

        self.fullscreen_action = view_menu.addAction("&Fullscreen")
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen)

        view_menu.addSeparator()

        self.next_tab_action = view_menu.addAction("&Next Tab")
        self.next_tab_action.triggered.connect(self._next_tab)

        self.prev_tab_action = view_menu.addAction("&Previous Tab")
        self.prev_tab_action.triggered.connect(self._prev_tab)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = help_menu.addAction("&About")
        about_action.triggered.connect(self._show_about)

    def _init_actions(self):
        """Set shortcuts for actions based on settings."""
        action_map = {
            "file.new": self.new_action,
            "file.open": self.open_action,
            "file.save": self.save_action,
            "file.save_as": self.save_as_action,
            "file.close_tab": self.close_tab_action,
            "file.quit": self.quit_action,
            "edit.undo": self.undo_action,
            "edit.redo": self.redo_action,
            "edit.cut": self.cut_action,
            "edit.copy": self.copy_action,
            "edit.paste": self.paste_action,
            "edit.select_all": self.select_all_action,
            "edit.find": self.find_action,
            "edit.replace": self.replace_action,
            "edit.go_to_line": self.go_to_line_action,
            "edit.duplicate_line": self.duplicate_line_action,
            "edit.delete_line": self.delete_line_action,
            "edit.move_line_up": self.move_line_up_action,
            "edit.move_line_down": self.move_line_down_action,
            "edit.toggle_comment": self.toggle_comment_action,
            "markdown.bold": self.bold_action,
            "markdown.italic": self.italic_action,
            "markdown.code": self.code_action,
            "markdown.link": self.link_action,
            "markdown.image": self.image_action,
            "markdown.heading_increase": self.heading_increase_action,
            "markdown.heading_decrease": self.heading_decrease_action,
            "view.refresh_preview": self.refresh_action,
            "view.toggle_preview": self.toggle_preview_action,
            "view.toggle_minimap": self.toggle_minimap_action,
            "view.toggle_line_numbers": self.toggle_line_numbers_action,
            "view.toggle_word_wrap": self.toggle_word_wrap_action,
            "view.toggle_whitespace": self.toggle_whitespace_action,
            "view.zoom_in": self.zoom_in_action,
            "view.zoom_out": self.zoom_out_action,
            "view.zoom_reset": self.zoom_reset_action,
            "view.fullscreen": self.fullscreen_action,
            "tabs.next": self.next_tab_action,
            "tabs.previous": self.prev_tab_action,
        }

        self.action_map = action_map
        self._apply_shortcuts()

    def _apply_shortcuts(self):
        """Apply shortcuts from settings to actions."""
        for action_id, action in self.action_map.items():
            shortcut = self.settings.get_shortcut(action_id)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))

    def _create_status_bar(self):
        """Create the status bar."""
        self.status_bar = self.statusBar()

        # Word count label
        self.word_count_label = QLabel("Words: 0 | Chars: 0")
        self.status_bar.addPermanentWidget(self.word_count_label)

        # Cursor position label
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        self.status_bar.addPermanentWidget(self.cursor_pos_label)

        self.status_bar.showMessage("Ready")

    def _init_shortcuts(self):
        """Set up additional keyboard shortcuts."""
        # Tab navigation shortcuts (Alt+1-9)
        for i in range(1, 10):
            shortcut_key = self.settings.get_shortcut(f"tabs.go_to_{i}")
            if shortcut_key:
                shortcut = QShortcut(QKeySequence(shortcut_key), self)
                shortcut.activated.connect(lambda idx=i - 1: self._go_to_tab(idx))

        # Find next/previous
        find_next_key = self.settings.get_shortcut("find.next")
        if find_next_key:
            find_next_shortcut = QShortcut(QKeySequence(find_next_key), self)
            find_next_shortcut.activated.connect(self._find_next)

        find_prev_key = self.settings.get_shortcut("find.previous")
        if find_prev_key:
            find_prev_shortcut = QShortcut(QKeySequence(find_prev_key), self)
            find_prev_shortcut.activated.connect(self._find_previous)

    def _connect_signals(self):
        """Connect settings signals."""
        self.settings.shortcut_changed.connect(self._on_shortcut_changed)
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _on_shortcut_changed(self, action: str, shortcut: str):
        """Handle shortcut change."""
        if action in self.action_map:
            self.action_map[action].setShortcut(QKeySequence(shortcut))

    def _on_setting_changed(self, key: str, value):
        """Handle setting change."""
        if key == "view.show_preview":
            self.toggle_preview_action.setChecked(value)
        elif key == "view.show_minimap":
            self.toggle_minimap_action.setChecked(value)
        elif key == "editor.show_line_numbers":
            self.toggle_line_numbers_action.setChecked(value)
        elif key == "editor.word_wrap":
            self.toggle_word_wrap_action.setChecked(value)
        elif key == "editor.show_whitespace":
            self.toggle_whitespace_action.setChecked(value)

    def _update_recent_files_menu(self):
        """Update the recent files menu."""
        self.recent_menu.clear()

        recent_files = self.settings.get_recent_files()

        if not recent_files:
            action = self.recent_menu.addAction("No Recent Files")
            action.setEnabled(False)
            return

        for path in recent_files:
            action = self.recent_menu.addAction(str(path))
            action.triggered.connect(lambda checked, p=path: self.open_file(p))

        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Clear Recent Files")
        clear_action.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self):
        """Clear recent files list."""
        self.settings.clear_recent_files()
        self._update_recent_files_menu()

    def current_tab(self) -> DocumentTab | None:
        """Return the currently active document tab."""
        return self.tab_widget.currentWidget()

    def _on_tab_changed(self, index: int):
        """Handle tab change event."""
        self.update_window_title()
        tab = self.current_tab()
        if tab:
            # Connect word count and cursor position signals
            tab.editor.word_count_changed.connect(self._update_word_count)
            tab.editor.cursor_position_changed.connect(self._update_cursor_position)
            # Trigger initial updates
            tab.editor._update_word_count()
            tab.editor._on_cursor_position_changed()

    def _update_word_count(self, words: int, chars: int):
        """Update word count in status bar."""
        self.word_count_label.setText(f"Words: {words} | Chars: {chars}")

    def _update_cursor_position(self, line: int, col: int):
        """Update cursor position in status bar."""
        self.cursor_pos_label.setText(f"Ln {line}, Col {col}")

    def update_window_title(self):
        """Update the window title to reflect current tab."""
        tab = self.current_tab()
        if tab:
            title = f"{tab.get_tab_title()} - Markdown Editor"
        else:
            title = "Markdown Editor"
        self.setWindowTitle(title)

    def update_tab_title(self, tab: DocumentTab):
        """Update the title of a specific tab."""
        index = self.tab_widget.indexOf(tab)
        if index >= 0:
            self.tab_widget.setTabText(index, tab.get_tab_title())

    def get_html_template(self, content: str) -> str:
        """Wrap rendered markdown in HTML with styling."""
        theme = self.settings.get("view.theme", "light")
        if theme == "dark":
            bg_color = "#1e1e1e"
            text_color = "#d4d4d4"
            heading_border = "#333"
            code_bg = "#2d2d2d"
            blockquote_color = "#888"
            link_color = "#4ec9b0"
            pygments_style = "monokai"
        else:
            bg_color = "#ffffff"
            text_color = "#24292e"
            heading_border = "#eaecef"
            code_bg = "#f6f8fa"
            blockquote_color = "#6a737d"
            link_color = "#0366d6"
            pygments_style = "github-dark"

        font_size = self.settings.get("view.preview_font_size", 14)

        # Generate Pygments CSS for syntax highlighting
        formatter = HtmlFormatter(style=pygments_style, cssclass="highlight")
        pygments_css = formatter.get_style_defs(".highlight")

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: {font_size}px;
                    line-height: 1.5;
                    color: {text_color};
                    background-color: {bg_color};
                    max-width: 100%;
                    padding: 20px;
                    margin: 0;
                }}
                * {{
                    box-sizing: border-box;
                }}
                h1 {{
                    font-size: 2em;
                    font-weight: 600;
                    border-bottom: 1px solid {heading_border};
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h2 {{
                    font-size: 1.5em;
                    font-weight: 600;
                    border-bottom: 1px solid {heading_border};
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h3 {{ font-size: 1.25em; font-weight: 600; margin-top: 24px; margin-bottom: 16px; }}
                h4, h5, h6 {{ font-weight: 600; margin-top: 24px; margin-bottom: 16px; }}
                p {{ margin-top: 0; margin-bottom: 16px; }}
                code {{
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 85%;
                    background-color: {code_bg};
                    padding: 0.2em 0.4em;
                    border-radius: 3px;
                }}
                pre {{
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 85%;
                    background-color: {code_bg};
                    padding: 16px;
                    overflow: auto;
                    border-radius: 6px;
                    line-height: 1.2;
                    margin: 0 0 16px 0;
                    white-space: pre;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                    font-size: 100%;
                    line-height: inherit;
                    display: block;
                }}
                /* Pygments highlight container */
                .highlight {{
                    background-color: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    overflow: auto;
                    margin-bottom: 16px;
                    line-height: 1.2;
                }}
                .highlight pre {{
                    margin: 0;
                    padding: 0;
                    background-color: transparent;
                    line-height: 1.2;
                }}
                .highlight code {{
                    line-height: 1.2;
                }}
                /* Remove any margins/padding inside code blocks */
                pre *, .highlight * {{
                    margin: 0;
                    padding: 0;
                    line-height: 1.2;
                }}
                pre span, .highlight span {{
                    display: inline;
                }}
                .codehilite {{
                    background-color: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    overflow: auto;
                    margin-bottom: 16px;
                }}
                .codehilite pre {{
                    margin: 0;
                    padding: 0;
                    background-color: transparent;
                    line-height: 1.2;
                }}
                blockquote {{
                    margin: 0;
                    padding: 0 1em;
                    color: {blockquote_color};
                    border-left: 0.25em solid {heading_border};
                }}
                ul, ol {{ padding-left: 2em; margin-top: 0; margin-bottom: 16px; }}
                li {{ margin-top: 0.25em; }}
                table {{ border-collapse: collapse; margin-top: 0; margin-bottom: 16px; width: 100%; }}
                th, td {{ padding: 6px 13px; border: 1px solid {heading_border}; }}
                th {{ font-weight: 600; background-color: {code_bg}; }}
                hr {{ height: 0.25em; padding: 0; margin: 24px 0; background-color: {heading_border}; border: 0; }}
                a {{ color: {link_color}; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                img {{ max-width: 100%; box-sizing: border-box; }}
                /* Pygments syntax highlighting */
                {pygments_css}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

    # Edit menu actions
    def _undo(self):
        tab = self.current_tab()
        if tab:
            tab.editor.undo()

    def _redo(self):
        tab = self.current_tab()
        if tab:
            tab.editor.redo()

    def _cut(self):
        tab = self.current_tab()
        if tab:
            tab.editor.cut()

    def _copy(self):
        tab = self.current_tab()
        if tab:
            tab.editor.copy()

    def _paste(self):
        tab = self.current_tab()
        if tab:
            tab.editor.paste()

    def _select_all(self):
        tab = self.current_tab()
        if tab:
            tab.editor.selectAll()

    def _show_find(self):
        tab = self.current_tab()
        if tab:
            tab.show_find()

    def _show_replace(self):
        tab = self.current_tab()
        if tab:
            tab.show_replace()

    def _find_next(self):
        tab = self.current_tab()
        if tab and tab.find_replace_bar.isVisible():
            tab.find_replace_bar.find_next()

    def _find_previous(self):
        tab = self.current_tab()
        if tab and tab.find_replace_bar.isVisible():
            tab.find_replace_bar.find_previous()

    def _go_to_line(self):
        tab = self.current_tab()
        if not tab:
            return

        line_count = tab.editor.blockCount()
        line, ok = QInputDialog.getInt(
            self,
            "Go to Line",
            f"Line number (1-{line_count}):",
            1,
            1,
            line_count,
        )
        if ok:
            tab.editor.go_to_line(line)

    def _duplicate_line(self):
        tab = self.current_tab()
        if tab:
            tab.editor.duplicate_line()

    def _delete_line(self):
        tab = self.current_tab()
        if tab:
            tab.editor.delete_line()

    def _move_line_up(self):
        tab = self.current_tab()
        if tab:
            tab.editor.move_line_up()

    def _move_line_down(self):
        tab = self.current_tab()
        if tab:
            tab.editor.move_line_down()

    def _toggle_comment(self):
        tab = self.current_tab()
        if tab:
            tab.editor.toggle_comment()

    def _show_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    # Format menu actions
    def _format_bold(self):
        tab = self.current_tab()
        if tab:
            tab.editor.format_bold()

    def _format_italic(self):
        tab = self.current_tab()
        if tab:
            tab.editor.format_italic()

    def _format_code(self):
        tab = self.current_tab()
        if tab:
            tab.editor.format_code()

    def _format_link(self):
        tab = self.current_tab()
        if tab:
            tab.editor.format_link()

    def _format_image(self):
        tab = self.current_tab()
        if tab:
            tab.editor.format_image()

    def _heading_increase(self):
        tab = self.current_tab()
        if tab:
            tab.editor.increase_heading()

    def _heading_decrease(self):
        tab = self.current_tab()
        if tab:
            tab.editor.decrease_heading()

    # View menu actions
    def _refresh_preview(self):
        tab = self.current_tab()
        if tab:
            tab.render_markdown()

    def _toggle_preview(self):
        value = self.toggle_preview_action.isChecked()
        self.settings.set("view.show_preview", value)

    def _toggle_minimap(self):
        value = self.toggle_minimap_action.isChecked()
        self.settings.set("view.show_minimap", value)

    def _toggle_line_numbers(self):
        value = self.toggle_line_numbers_action.isChecked()
        self.settings.set("editor.show_line_numbers", value)

    def _toggle_word_wrap(self):
        value = self.toggle_word_wrap_action.isChecked()
        self.settings.set("editor.word_wrap", value)

    def _toggle_whitespace(self):
        value = self.toggle_whitespace_action.isChecked()
        self.settings.set("editor.show_whitespace", value)

    def _zoom_in(self):
        tab = self.current_tab()
        if tab:
            # Zoom editor
            tab.editor.zoom_in()
            # Zoom preview
            preview_size = self.settings.get("view.preview_font_size", 14)
            if preview_size < 32:
                self.settings.set("view.preview_font_size", preview_size + 1)

    def _zoom_out(self):
        tab = self.current_tab()
        if tab:
            # Zoom editor
            tab.editor.zoom_out()
            # Zoom preview
            preview_size = self.settings.get("view.preview_font_size", 14)
            if preview_size > 8:
                self.settings.set("view.preview_font_size", preview_size - 1)

    def _zoom_reset(self):
        tab = self.current_tab()
        if tab:
            # Reset editor zoom
            tab.editor.zoom_reset()
            # Reset preview zoom
            self.settings.set("view.preview_font_size", 14)

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self._is_fullscreen = True

    # Tab navigation
    def _next_tab(self):
        count = self.tab_widget.count()
        if count > 1:
            current = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex((current + 1) % count)

    def _prev_tab(self):
        count = self.tab_widget.count()
        if count > 1:
            current = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex((current - 1) % count)

    def _go_to_tab(self, index: int):
        if index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)

    # File operations
    def new_tab(self) -> DocumentTab:
        """Create a new empty document tab."""
        tab = DocumentTab(self)
        index = self.tab_widget.addTab(tab, tab.get_tab_title())
        self.tab_widget.setCurrentIndex(index)
        self.status_bar.showMessage("New tab created")
        return tab

    def open_file(self, file_path: str | Path | None = None):
        """Open a markdown file in a new tab."""
        if not isinstance(file_path, (str, Path)) or not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Markdown File",
                "",
                "Markdown Files (*.md *.markdown *.txt);;All Files (*)",
            )
            if not file_path:
                return

        path = Path(file_path)
        if not path.exists():
            QMessageBox.warning(self, "Error", f"File not found: {path}")
            return

        # Check if file is already open
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab.file_path and tab.file_path.resolve() == path.resolve():
                self.tab_widget.setCurrentIndex(i)
                self.status_bar.showMessage(f"Switched to: {path}")
                return

        try:
            content = path.read_text(encoding="utf-8")

            # Use current tab if it's empty and untitled
            tab = self.current_tab()
            if (
                tab
                and tab.file_path is None
                and not tab.unsaved_changes
                and not tab.editor.toPlainText()
            ):
                pass
            else:
                tab = DocumentTab(self)
                index = self.tab_widget.addTab(tab, "")
                self.tab_widget.setCurrentIndex(index)

            tab.editor.setPlainText(content)
            tab.file_path = path
            tab.editor.set_file_path(path)
            tab.unsaved_changes = False
            self.update_tab_title(tab)
            self.update_window_title()
            tab.render_markdown()

            # Add to recent files
            self.settings.add_recent_file(path)
            self._update_recent_files_menu()

            self.status_bar.showMessage(f"Opened: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file: {e}")

    def save_file(self) -> bool:
        """Save the current tab's file."""
        tab = self.current_tab()
        if not tab:
            return False

        if tab.file_path is None:
            return self.save_file_as()

        try:
            tab.file_path.write_text(tab.editor.toPlainText(), encoding="utf-8")
            tab.unsaved_changes = False
            tab.editor.document().setModified(False)
            self.update_tab_title(tab)
            self.update_window_title()
            self.status_bar.showMessage(f"Saved: {tab.file_path}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")
            return False

    def save_file_as(self) -> bool:
        """Save the current tab's file with a new name."""
        tab = self.current_tab()
        if not tab:
            return False

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown File",
            "",
            "Markdown Files (*.md);;All Files (*)",
        )
        if not file_path:
            return False

        tab.file_path = Path(file_path)
        tab.editor.set_file_path(tab.file_path)
        return self.save_file()

    def _export_html(self):
        """Export the current document to HTML."""
        tab = self.current_tab()
        if not tab:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to HTML",
            "",
            "HTML Files (*.html);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self.md.reset()
            html_content = self.md.convert(tab.editor.toPlainText())
            full_html = self.get_html_template(html_content)

            Path(file_path).write_text(full_html, encoding="utf-8")
            self.status_bar.showMessage(f"Exported to: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not export file: {e}")

    def _close_current_tab(self):
        """Close the current tab."""
        index = self.tab_widget.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def close_tab(self, index: int) -> bool:
        """Close a tab by index."""
        tab = self.tab_widget.widget(index)
        if not tab:
            return False

        if not self._check_tab_unsaved_changes(tab):
            return False

        self.tab_widget.removeTab(index)

        if self.tab_widget.count() == 0:
            self.new_tab()

        return True

    def _check_tab_unsaved_changes(self, tab: DocumentTab) -> bool:
        """Check for unsaved changes in a tab and prompt user."""
        if not tab.unsaved_changes:
            return True

        name = tab.file_path.name if tab.file_path else "Untitled"
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f'"{name}" has unsaved changes. Do you want to save them?',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if reply == QMessageBox.Save:
            current_index = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentWidget(tab)
            result = self.save_file()
            self.tab_widget.setCurrentIndex(current_index)
            return result
        elif reply == QMessageBox.Cancel:
            return False
        return True

    # Drag and drop
    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop events."""
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())

    def closeEvent(self, event):
        """Handle window close event."""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if not self._check_tab_unsaved_changes(tab):
                event.ignore()
                return
        event.accept()

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Markdown Editor",
            "Markdown Editor\n\n"
            "A feature-rich Markdown editor with live preview.\n\n"
            "Features:\n"
            "• Split-screen editing and preview\n"
            "• Syntax highlighting\n"
            "• Multiple tabs\n"
            "• Find and replace\n"
            "• Customizable shortcuts\n"
            "• Dark/light themes\n"
            "• And more!"
        )


def main():
    """Run the Markdown editor application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    editor = MarkdownEditor()
    editor.show()

    for arg in sys.argv[1:]:
        editor.open_file(arg)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

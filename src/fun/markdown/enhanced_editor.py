"""Enhanced text editor with line numbers, minimap, and advanced features."""

import re
from pathlib import Path

from PyQt5.QtCore import Qt, QRect, QSize, QTimer, pyqtSignal, QFileSystemWatcher
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QTextCursor,
    QTextFormat,
    QTextOption,
)
from PyQt5.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from fun.markdown.settings import get_settings
from fun.markdown.syntax_highlighter import MarkdownHighlighter


class LineNumberArea(QWidget):
    """Widget for displaying line numbers in the editor gutter."""

    def __init__(self, editor: "EnhancedEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class Minimap(QTextEdit):
    """A minimap widget showing document overview."""

    clicked = pyqtSignal(int)  # line number

    def __init__(self, editor: "EnhancedEditor"):
        super().__init__()
        self.editor = editor
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setFixedWidth(100)

        # Very small font
        font = QFont("Monospace", 2)
        self.setFont(font)

        # Style
        self.setStyleSheet("""
            QTextEdit {
                background-color: #f0f0f0;
                border: none;
                border-left: 1px solid #ddd;
            }
        """)

        self.viewport_rect = QRect()

    def set_dark_mode(self, dark: bool):
        if dark:
            self.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    border: none;
                    border-left: 1px solid #333;
                    color: #808080;
                }
            """)
        else:
            self.setStyleSheet("""
                QTextEdit {
                    background-color: #f0f0f0;
                    border: none;
                    border-left: 1px solid #ddd;
                }
            """)

    def update_content(self, text: str):
        """Update minimap content."""
        self.setPlainText(text)

    def update_viewport_rect(self, first_visible: int, last_visible: int, total_lines: int):
        """Update the visible viewport indicator."""
        if total_lines == 0:
            return

        doc_height = self.document().size().height()
        line_height = doc_height / max(total_lines, 1)

        y_start = int(first_visible * line_height)
        y_end = int(last_visible * line_height)

        self.viewport_rect = QRect(0, y_start, self.width(), y_end - y_start)
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)

        # Draw viewport indicator
        if not self.viewport_rect.isEmpty():
            painter = QPainter(self.viewport())
            painter.fillRect(
                self.viewport_rect,
                QColor(100, 100, 100, 50)
            )
            painter.end()

    def mousePressEvent(self, event):
        """Handle click to jump to position."""
        if event.button() == Qt.LeftButton:
            # Calculate line from click position
            doc_height = self.document().size().height()
            if doc_height > 0:
                ratio = event.y() / self.height()
                total_lines = self.document().blockCount()
                line = int(ratio * total_lines)
                self.clicked.emit(line)

    def mouseMoveEvent(self, event):
        """Handle drag to scroll."""
        if event.buttons() & Qt.LeftButton:
            doc_height = self.document().size().height()
            if doc_height > 0:
                ratio = event.y() / self.height()
                total_lines = self.document().blockCount()
                line = int(ratio * total_lines)
                self.clicked.emit(line)


class EnhancedEditor(QPlainTextEdit):
    """Enhanced plain text editor with line numbers and advanced features."""

    word_count_changed = pyqtSignal(int, int)  # words, characters
    cursor_position_changed = pyqtSignal(int, int)  # line, column
    file_externally_modified = pyqtSignal()

    # Auto-pair characters
    AUTO_PAIRS = {
        "(": ")",
        "[": "]",
        "{": "}",
        '"': '"',
        "'": "'",
        "`": "`",
        "*": "*",
        "_": "_",
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = get_settings()
        self.file_path: Path | None = None
        self._file_watcher: QFileSystemWatcher | None = None
        self._ignore_next_file_change = False

        self._init_ui()
        self._init_line_numbers()
        self._init_minimap()
        self._init_highlighter()
        self._init_timers()
        self._connect_signals()
        self._apply_settings()

    def _init_ui(self):
        """Initialize the editor UI."""
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        # Set font
        font_family = self.settings.get("editor.font_family", "Monospace")
        font_size = self.settings.get("editor.font_size", 11)
        font = QFont(font_family, font_size)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # Tab settings
        tab_size = self.settings.get("editor.tab_size", 4)
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(" ") * tab_size
        )

    def _init_line_numbers(self):
        """Initialize line number area."""
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width()

    def _init_minimap(self):
        """Initialize minimap widget."""
        self.minimap = Minimap(self)
        self.minimap.clicked.connect(self._go_to_line)
        self.minimap.hide()

    def _init_highlighter(self):
        """Initialize syntax highlighter."""
        dark_mode = self.settings.get("view.theme", "light") == "dark"
        self.highlighter = MarkdownHighlighter(self.document(), dark_mode)

    def _init_timers(self):
        """Initialize timers."""
        # Word count update timer
        self.word_count_timer = QTimer()
        self.word_count_timer.setSingleShot(True)
        self.word_count_timer.timeout.connect(self._update_word_count)

        # Auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)
        if self.settings.get("editor.auto_save", False):
            interval = self.settings.get("editor.auto_save_interval", 60) * 1000
            self.auto_save_timer.start(interval)

    def _connect_signals(self):
        """Connect signals."""
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _apply_settings(self):
        """Apply current settings."""
        # Word wrap
        if self.settings.get("editor.word_wrap", True):
            self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Show whitespace
        if self.settings.get("editor.show_whitespace", False):
            option = self.document().defaultTextOption()
            option.setFlags(
                option.flags() | QTextOption.ShowTabsAndSpaces
            )
            self.document().setDefaultTextOption(option)
        else:
            option = self.document().defaultTextOption()
            option.setFlags(
                option.flags() & ~QTextOption.ShowTabsAndSpaces
            )
            self.document().setDefaultTextOption(option)

        # Line numbers
        self.line_number_area.setVisible(
            self.settings.get("editor.show_line_numbers", True)
        )
        self._update_line_number_area_width()

        # Minimap
        self.minimap.setVisible(self.settings.get("view.show_minimap", False))

        # Theme
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme."""
        theme = self.settings.get("view.theme", "light")
        dark = theme == "dark"

        if dark:
            self.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    selection-background-color: #264f78;
                }
            """)
        else:
            self.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #ffffff;
                    color: #24292e;
                    selection-background-color: #b3d7ff;
                }
            """)

        self.highlighter.set_dark_mode(dark)
        self.minimap.set_dark_mode(dark)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "editor.word_wrap":
            if value:
                self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            else:
                self.setLineWrapMode(QPlainTextEdit.NoWrap)
        elif key == "editor.show_whitespace":
            option = self.document().defaultTextOption()
            if value:
                option.setFlags(option.flags() | QTextOption.ShowTabsAndSpaces)
            else:
                option.setFlags(option.flags() & ~QTextOption.ShowTabsAndSpaces)
            self.document().setDefaultTextOption(option)
        elif key == "editor.show_line_numbers":
            self.line_number_area.setVisible(value)
            self._update_line_number_area_width()
        elif key == "view.show_minimap":
            self.minimap.setVisible(value)
        elif key == "view.theme":
            self._apply_theme()
        elif key == "editor.font_size":
            font = self.font()
            font.setPointSize(value)
            self.setFont(font)
            self._update_line_number_area_width()
        elif key == "editor.auto_save":
            if value:
                interval = self.settings.get("editor.auto_save_interval", 60) * 1000
                self.auto_save_timer.start(interval)
            else:
                self.auto_save_timer.stop()

    def _on_text_changed(self):
        """Handle text changes."""
        self.word_count_timer.start(500)
        self._update_minimap()

    def _on_cursor_position_changed(self):
        """Handle cursor position changes."""
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber() + 1
        self.cursor_position_changed.emit(line, column)

        # Update current line highlight
        if self.settings.get("editor.highlight_current_line", True):
            self._highlight_current_line()

    def _highlight_current_line(self):
        """Highlight the current line."""
        extra_selections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()

            theme = self.settings.get("view.theme", "light")
            if theme == "dark":
                line_color = QColor(40, 40, 40)
            else:
                line_color = QColor(255, 255, 220)

            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    def _update_word_count(self):
        """Update word and character counts."""
        text = self.toPlainText()
        char_count = len(text)
        word_count = len(text.split()) if text.strip() else 0
        self.word_count_changed.emit(word_count, char_count)

    def _update_minimap(self):
        """Update the minimap content."""
        if self.minimap.isVisible():
            self.minimap.update_content(self.toPlainText())

            # Update viewport indicator
            first_visible = self.firstVisibleBlock().blockNumber()
            cursor = self.cursorForPosition(self.viewport().rect().bottomLeft())
            last_visible = cursor.blockNumber()
            total_lines = self.blockCount()

            self.minimap.update_viewport_rect(first_visible, last_visible, total_lines)

    def _auto_save(self):
        """Auto-save the document if it has a file path."""
        if self.file_path and self.document().isModified():
            self.save_file()

    # Line number methods
    def line_number_area_width(self) -> int:
        """Calculate the width needed for line numbers."""
        if not self.settings.get("editor.show_line_numbers", True):
            return 0

        digits = len(str(max(1, self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def _update_line_number_area_width(self):
        """Update the editor margins to accommodate line numbers."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        """Update the line number area on scroll or resize."""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)

        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        """Paint the line number area."""
        painter = QPainter(self.line_number_area)

        theme = self.settings.get("view.theme", "light")
        if theme == "dark":
            painter.fillRect(event.rect(), QColor(30, 30, 30))
            number_color = QColor(100, 100, 100)
            current_color = QColor(200, 200, 200)
        else:
            painter.fillRect(event.rect(), QColor(240, 240, 240))
            number_color = QColor(150, 150, 150)
            current_color = QColor(50, 50, 50)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)

                if block_number == current_line:
                    painter.setPen(current_color)
                    font = painter.font()
                    font.setBold(True)
                    painter.setFont(font)
                else:
                    painter.setPen(number_color)
                    font = painter.font()
                    font.setBold(False)
                    painter.setFont(font)

                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    # File watching
    def set_file_path(self, path: Path | None):
        """Set the file path and enable file watching."""
        # Stop watching old file
        if self._file_watcher and self.file_path:
            self._file_watcher.removePath(str(self.file_path))

        self.file_path = path

        # Watch new file
        if path and self.settings.get("files.detect_external_changes", True):
            if self._file_watcher is None:
                self._file_watcher = QFileSystemWatcher()
                self._file_watcher.fileChanged.connect(self._on_file_changed)
            self._file_watcher.addPath(str(path))

    def _on_file_changed(self, path: str):
        """Handle external file changes."""
        if self._ignore_next_file_change:
            self._ignore_next_file_change = False
            # Re-add the watch (it's removed after the file is modified)
            if self.file_path:
                self._file_watcher.addPath(str(self.file_path))
            return

        self.file_externally_modified.emit()

        # Re-add the watch
        if self.file_path:
            self._file_watcher.addPath(str(self.file_path))

    def save_file(self) -> bool:
        """Save the file content."""
        if not self.file_path:
            return False

        self._ignore_next_file_change = True
        try:
            self.file_path.write_text(self.toPlainText(), encoding="utf-8")
            self.document().setModified(False)
            return True
        except Exception:
            return False

    # Go to line
    def _go_to_line(self, line: int):
        """Go to a specific line number."""
        block = self.document().findBlockByLineNumber(line)
        if block.isValid():
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.centerCursor()

    def go_to_line(self, line: int):
        """Public method to go to a specific line (1-indexed)."""
        self._go_to_line(line - 1)

    # Text manipulation methods
    def duplicate_line(self):
        """Duplicate the current line or selection."""
        cursor = self.textCursor()

        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.clearSelection()
            cursor.insertText(text)
        else:
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            line_text = cursor.selectedText()
            cursor.movePosition(QTextCursor.EndOfLine)
            cursor.insertText("\n" + line_text)

        self.setTextCursor(cursor)

    def delete_line(self):
        """Delete the current line."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    def move_line_up(self):
        """Move the current line up."""
        cursor = self.textCursor()
        if cursor.blockNumber() == 0:
            return

        cursor.beginEditBlock()

        # Select current line
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        line_text = cursor.selectedText()
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        # Move up and insert
        cursor.movePosition(QTextCursor.Up)
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.insertText(line_text + "\n")
        cursor.movePosition(QTextCursor.Up)

        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def move_line_down(self):
        """Move the current line down."""
        cursor = self.textCursor()
        if cursor.blockNumber() >= self.blockCount() - 1:
            return

        cursor.beginEditBlock()

        # Select current line
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        line_text = cursor.selectedText()
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        # Move to end of next line and insert
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText("\n" + line_text)

        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def indent_selection(self):
        """Indent the selection or current line."""
        cursor = self.textCursor()
        use_spaces = self.settings.get("editor.use_spaces", True)
        tab_size = self.settings.get("editor.tab_size", 4)
        indent_char = " " * tab_size if use_spaces else "\t"

        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()

            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.StartOfLine)
            start_block = cursor.blockNumber()

            cursor.setPosition(end)
            if cursor.atBlockStart():
                cursor.movePosition(QTextCursor.Left)
            end_block = cursor.blockNumber()

            cursor.beginEditBlock()

            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.StartOfLine)

            for _ in range(end_block - start_block + 1):
                cursor.insertText(indent_char)
                cursor.movePosition(QTextCursor.Down)
                cursor.movePosition(QTextCursor.StartOfLine)

            cursor.endEditBlock()
        else:
            cursor.insertText(indent_char)

    def outdent_selection(self):
        """Outdent the selection or current line."""
        cursor = self.textCursor()
        tab_size = self.settings.get("editor.tab_size", 4)

        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()

            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.StartOfLine)
            start_block = cursor.blockNumber()

            cursor.setPosition(end)
            if cursor.atBlockStart():
                cursor.movePosition(QTextCursor.Left)
            end_block = cursor.blockNumber()

            cursor.beginEditBlock()

            for block_num in range(start_block, end_block + 1):
                block = self.document().findBlockByNumber(block_num)
                text = block.text()

                if text.startswith("\t"):
                    cursor.setPosition(block.position())
                    cursor.deleteChar()
                elif text.startswith(" " * tab_size):
                    cursor.setPosition(block.position())
                    for _ in range(tab_size):
                        cursor.deleteChar()
                elif text.startswith(" "):
                    cursor.setPosition(block.position())
                    while cursor.block().text().startswith(" "):
                        cursor.deleteChar()

            cursor.endEditBlock()
        else:
            cursor.movePosition(QTextCursor.StartOfLine)
            block_text = cursor.block().text()

            if block_text.startswith("\t"):
                cursor.deleteChar()
            elif block_text.startswith(" " * tab_size):
                for _ in range(tab_size):
                    cursor.deleteChar()

    def toggle_comment(self):
        """Toggle HTML comment on selected lines."""
        cursor = self.textCursor()

        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            selected_text = cursor.selectedText()

            # Check if already commented
            if selected_text.startswith("<!--") and selected_text.endswith("-->"):
                # Remove comment
                new_text = selected_text[4:-3]
            else:
                # Add comment
                new_text = f"<!--{selected_text}-->"

            cursor.insertText(new_text)
        else:
            # Comment current line
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            line_text = cursor.selectedText()

            if line_text.strip().startswith("<!--") and line_text.strip().endswith("-->"):
                # Remove comment
                new_text = re.sub(r"<!--\s*", "", line_text)
                new_text = re.sub(r"\s*-->", "", new_text)
            else:
                # Add comment
                new_text = f"<!-- {line_text} -->"

            cursor.insertText(new_text)

    # Markdown formatting
    def wrap_selection(self, prefix: str, suffix: str | None = None):
        """Wrap the selection with prefix and suffix."""
        if suffix is None:
            suffix = prefix

        cursor = self.textCursor()

        if cursor.hasSelection():
            text = cursor.selectedText()

            # Check if already wrapped
            if text.startswith(prefix) and text.endswith(suffix):
                # Remove wrapping
                new_text = text[len(prefix):-len(suffix) if suffix else None]
            else:
                # Add wrapping
                new_text = f"{prefix}{text}{suffix}"

            cursor.insertText(new_text)
        else:
            # Insert markers and position cursor between them
            pos = cursor.position()
            cursor.insertText(prefix + suffix)
            cursor.setPosition(pos + len(prefix))
            self.setTextCursor(cursor)

    def format_bold(self):
        """Toggle bold formatting."""
        self.wrap_selection("**")

    def format_italic(self):
        """Toggle italic formatting."""
        self.wrap_selection("*")

    def format_code(self):
        """Toggle inline code formatting."""
        self.wrap_selection("`")

    def format_link(self):
        """Insert a link."""
        cursor = self.textCursor()

        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"[{text}](url)")
            # Position cursor at 'url'
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 4)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 3)
        else:
            pos = cursor.position()
            cursor.insertText("[text](url)")
            cursor.setPosition(pos + 1)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 4)

        self.setTextCursor(cursor)

    def format_image(self):
        """Insert an image."""
        cursor = self.textCursor()

        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"![{text}](url)")
        else:
            pos = cursor.position()
            cursor.insertText("![alt](url)")
            cursor.setPosition(pos + 2)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 3)

        self.setTextCursor(cursor)

    def increase_heading(self):
        """Increase heading level."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)

        block_text = cursor.block().text()
        match = re.match(r"^(#{1,5})\s", block_text)

        if match:
            # Already a heading, increase level
            cursor.insertText("#")
        elif not block_text.startswith("######"):
            # Not at max level
            cursor.insertText("# ")

        self.setTextCursor(cursor)

    def decrease_heading(self):
        """Decrease heading level."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)

        block_text = cursor.block().text()
        match = re.match(r"^(#{1,6})\s", block_text)

        if match:
            hashes = match.group(1)
            if len(hashes) == 1:
                # Remove heading entirely
                cursor.movePosition(
                    QTextCursor.Right, QTextCursor.KeepAnchor, len(hashes) + 1
                )
                cursor.removeSelectedText()
            else:
                # Decrease level
                cursor.deleteChar()

    # Zoom
    def zoom_in(self):
        """Increase font size."""
        font = self.font()
        size = font.pointSize()
        if size < 72:
            font.setPointSize(size + 1)
            self.setFont(font)
            self.settings.set("editor.font_size", size + 1, save=False)
            self._update_line_number_area_width()

    def zoom_out(self):
        """Decrease font size."""
        font = self.font()
        size = font.pointSize()
        if size > 6:
            font.setPointSize(size - 1)
            self.setFont(font)
            self.settings.set("editor.font_size", size - 1, save=False)
            self._update_line_number_area_width()

    def zoom_reset(self):
        """Reset font size to default."""
        font = self.font()
        font.setPointSize(11)
        self.setFont(font)
        self.settings.set("editor.font_size", 11, save=False)
        self._update_line_number_area_width()

    # Key event handling
    def keyPressEvent(self, event):
        """Handle key press events."""
        # Auto-pairs
        if self.settings.get("editor.auto_pairs", True):
            char = event.text()
            if char in self.AUTO_PAIRS:
                cursor = self.textCursor()
                if cursor.hasSelection():
                    # Wrap selection
                    text = cursor.selectedText()
                    cursor.insertText(char + text + self.AUTO_PAIRS[char])
                    return
                else:
                    # Insert pair
                    cursor.insertText(char + self.AUTO_PAIRS[char])
                    cursor.movePosition(QTextCursor.Left)
                    self.setTextCursor(cursor)
                    return

            # Handle closing character - skip if next char is the same
            if char in self.AUTO_PAIRS.values():
                cursor = self.textCursor()
                if not cursor.atEnd():
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                    next_char = cursor.selectedText()
                    cursor.movePosition(QTextCursor.Left)
                    if next_char == char:
                        cursor.movePosition(QTextCursor.Right)
                        self.setTextCursor(cursor)
                        return

        # Auto-indent on Enter
        if event.key() == Qt.Key_Return and self.settings.get("editor.auto_indent", True):
            cursor = self.textCursor()
            block_text = cursor.block().text()

            # Get leading whitespace
            indent = ""
            for c in block_text:
                if c in " \t":
                    indent += c
                else:
                    break

            # Check for list continuation
            list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s", block_text)
            if list_match:
                # Continue list
                marker = list_match.group(2)
                if marker[0].isdigit():
                    # Increment number
                    num = int(marker[:-1]) + 1
                    marker = f"{num}."
                super().keyPressEvent(event)
                cursor = self.textCursor()
                cursor.insertText(f"{indent}{marker} ")
                return

            super().keyPressEvent(event)
            if indent:
                cursor = self.textCursor()
                cursor.insertText(indent)
            return

        # Tab/Shift+Tab for indent/outdent
        if event.key() == Qt.Key_Tab:
            if event.modifiers() & Qt.ShiftModifier:
                self.outdent_selection()
            else:
                self.indent_selection()
            return

        if event.key() == Qt.Key_Backtab:
            self.outdent_selection()
            return

        super().keyPressEvent(event)

    # Drag and drop
    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        """Handle drop events."""
        if event.mimeData().hasUrls():
            # Let the main window handle file drops
            event.ignore()
        else:
            super().dropEvent(event)

    # Scroll sync support
    def get_scroll_ratio(self) -> float:
        """Get the current scroll position as a ratio."""
        scrollbar = self.verticalScrollBar()
        if scrollbar.maximum() == 0:
            return 0.0
        return scrollbar.value() / scrollbar.maximum()

    def set_scroll_ratio(self, ratio: float):
        """Set the scroll position from a ratio."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(int(ratio * scrollbar.maximum()))

"""Enhanced text editor with line numbers and advanced features."""

import re
import uuid
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QRect, QSize, QTimer, Signal, QFileSystemWatcher, QMimeData, QPoint
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QKeySequence,
    QPainter,
    QTextCursor,
    QTextFormat,
    QTextOption,
    QTextBlock,
    QPolygon,
)
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from fun.markdown6.settings import get_settings
from fun.markdown6.syntax_highlighter import MarkdownHighlighter


class FoldingRegion:
    """Represents a foldable region in the document."""

    def __init__(self, start_line: int, end_line: int, region_type: str = "heading"):
        self.start_line = start_line
        self.end_line = end_line
        self.region_type = region_type  # "heading", "code_block"
        self.is_folded = False


class LineNumberArea(QWidget):
    """Widget for displaying line numbers in the editor gutter."""

    def __init__(self, editor: "EnhancedEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event):
        """Handle click on fold indicator."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate which line was clicked
            block = self.editor.firstVisibleBlock()
            top = int(self.editor.blockBoundingGeometry(block).translated(
                self.editor.contentOffset()).top())

            while block.isValid() and top <= event.position().y():
                if block.isVisible():
                    bottom = top + int(self.editor.blockBoundingRect(block).height())
                    if top <= event.position().y() < bottom:
                        line = block.blockNumber()
                        self.editor.toggle_fold_at_line(line)
                        break
                    top = bottom
                block = block.next()


class WikiLinkCompleter(QListWidget):
    """Autocomplete popup for wiki-style links."""

    link_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.itemActivated.connect(self._on_item_activated)
        self.setMaximumHeight(200)
        self.setMinimumWidth(200)

    def _on_item_activated(self, item):
        self.link_selected.emit(item.text())
        self.hide()

    def show_completions(self, completions: list[str], pos):
        self.clear()
        for comp in completions[:10]:  # Limit to 10
            self.addItem(comp)
        if self.count() > 0:
            self.setCurrentRow(0)
            self.move(pos)
            self.show()
        else:
            self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item:
                self._on_item_activated(item)
        elif event.key() == Qt.Key.Key_Down:
            current = self.currentRow()
            if current < self.count() - 1:
                self.setCurrentRow(current + 1)
        elif event.key() == Qt.Key.Key_Up:
            current = self.currentRow()
            if current > 0:
                self.setCurrentRow(current - 1)
        else:
            super().keyPressEvent(event)


class EnhancedEditor(QPlainTextEdit):
    """Enhanced plain text editor with line numbers and advanced features."""

    word_count_changed = Signal(int, int)  # words, characters
    cursor_position_changed = Signal(int, int)  # line, column
    file_externally_modified = Signal()
    link_ctrl_clicked = Signal(str)  # link URL/path when Ctrl+clicked

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

        # Folding support
        self.folding_regions: dict[int, FoldingRegion] = {}
        self.folded_blocks: set[int] = set()

        # Wiki-link autocomplete
        self.wiki_link_completer: WikiLinkCompleter | None = None
        self._available_links: list[str] = []
        self._wiki_link_prefix = ""

        # Snippet manager
        self._snippet_manager = None

        self._init_ui()
        self._init_line_numbers()
        self._init_highlighter()
        self._init_timers()
        self._init_wiki_completer()
        self._connect_signals()
        self._apply_settings()

    def _init_ui(self):
        """Initialize the editor UI."""
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)
        self._hover_link_range: tuple[int, int] | None = None  # (start, end) positions

        # Set font
        font_family = self.settings.get("editor.font_family", "Monospace")
        font_size = self.settings.get("editor.font_size", 11)
        font = QFont(font_family, font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
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

        # Folding regions update timer (debounce expensive parsing)
        self.folding_timer = QTimer()
        self.folding_timer.setSingleShot(True)
        self.folding_timer.timeout.connect(self._do_update_folding_regions)

        # Auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)
        if self.settings.get("editor.auto_save", False):
            interval = self.settings.get("editor.auto_save_interval", 60) * 1000
            self.auto_save_timer.start(interval)

    def _init_wiki_completer(self):
        """Initialize wiki-link autocomplete."""
        self.wiki_link_completer = WikiLinkCompleter(self)
        self.wiki_link_completer.link_selected.connect(self._insert_wiki_link)

    def _connect_signals(self):
        """Connect signals."""
        self.textChanged.connect(self._on_text_changed)
        self.textChanged.connect(self._schedule_folding_update)
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
        self.settings.settings_changed.connect(self._on_setting_changed)

    def _schedule_folding_update(self):
        """Schedule a debounced folding regions update."""
        self.folding_timer.start(500)

    def _apply_settings(self):
        """Apply current settings."""
        # Word wrap
        if self.settings.get("editor.word_wrap", True):
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Show whitespace
        if self.settings.get("editor.show_whitespace", False):
            option = self.document().defaultTextOption()
            option.setFlags(
                option.flags() | QTextOption.Flag.ShowTabsAndSpaces
            )
            self.document().setDefaultTextOption(option)
        else:
            option = self.document().defaultTextOption()
            option.setFlags(
                option.flags() & ~QTextOption.Flag.ShowTabsAndSpaces
            )
            self.document().setDefaultTextOption(option)

        # Line numbers
        self.line_number_area.setVisible(
            self.settings.get("editor.show_line_numbers", True)
        )
        self._update_line_number_area_width()

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

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "editor.word_wrap":
            if value:
                self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            else:
                self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        elif key == "editor.show_whitespace":
            option = self.document().defaultTextOption()
            if value:
                option.setFlags(option.flags() | QTextOption.Flag.ShowTabsAndSpaces)
            else:
                option.setFlags(option.flags() & ~QTextOption.Flag.ShowTabsAndSpaces)
            self.document().setDefaultTextOption(option)
        elif key == "editor.show_line_numbers":
            self.line_number_area.setVisible(value)
            self._update_line_number_area_width()
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
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
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

    def _auto_save(self):
        """Auto-save the document if it has a file path."""
        if self.file_path and self.document().isModified():
            self.save_file()

    # Line number methods
    def line_number_area_width(self) -> int:
        """Calculate the width needed for line numbers."""
        if not self.settings.get("editor.show_line_numbers", True):
            return 0

        digits = len(str(max(1, self.blockCount()))) + 1  # +1 for padding
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
            fold_color = QColor(150, 150, 150)
        else:
            painter.fillRect(event.rect(), QColor(240, 240, 240))
            number_color = QColor(150, 150, 150)
            current_color = QColor(50, 50, 50)
            fold_color = QColor(100, 100, 100)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        current_line = self.textCursor().blockNumber()
        fold_indicator_width = 12

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

                # Draw line number (leave space for fold indicator)
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - fold_indicator_width - 3,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

                # Draw fold indicator if this line is foldable
                if block_number in self.folding_regions:
                    is_folded = self.folding_regions[block_number].is_folded
                    painter.setPen(fold_color)

                    # Draw a triangle indicator
                    indicator_x = self.line_number_area.width() - fold_indicator_width
                    indicator_y = top + (self.fontMetrics().height() - 8) // 2
                    indicator_size = 8

                    if is_folded:
                        # Right-pointing triangle (folded)
                        points = [
                            QPoint(indicator_x, indicator_y),
                            QPoint(indicator_x, indicator_y + indicator_size),
                            QPoint(indicator_x + indicator_size, indicator_y + indicator_size // 2),
                        ]
                    else:
                        # Down-pointing triangle (expanded)
                        points = [
                            QPoint(indicator_x, indicator_y),
                            QPoint(indicator_x + indicator_size, indicator_y),
                            QPoint(indicator_x + indicator_size // 2, indicator_y + indicator_size),
                        ]

                    polygon = QPolygon(points)
                    painter.setBrush(fold_color)
                    painter.drawPolygon(polygon)

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
        """Go to a specific line number (0-indexed block number)."""
        # Use findBlockByNumber, not findBlockByLineNumber
        # findBlockByLineNumber counts visual lines (affected by word wrap)
        # findBlockByNumber counts actual text blocks (source lines)
        block = self.document().findBlockByNumber(line)
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
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
            line_text = cursor.selectedText()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            cursor.insertText("\n" + line_text)

        self.setTextCursor(cursor)

    def delete_line(self):
        """Delete the current line."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    def move_line_up(self):
        """Move the current line up."""
        cursor = self.textCursor()
        if cursor.blockNumber() == 0:
            return

        cursor.beginEditBlock()

        # Select current line
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        line_text = cursor.selectedText()
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        # Move up and insert
        cursor.movePosition(QTextCursor.MoveOperation.Up)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.insertText(line_text + "\n")
        cursor.movePosition(QTextCursor.MoveOperation.Up)

        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def move_line_down(self):
        """Move the current line down."""
        cursor = self.textCursor()
        if cursor.blockNumber() >= self.blockCount() - 1:
            return

        cursor.beginEditBlock()

        # Select current line
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        line_text = cursor.selectedText()
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        # Move to end of next line and insert
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
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
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            start_block = cursor.blockNumber()

            cursor.setPosition(end)
            if cursor.atBlockStart():
                cursor.movePosition(QTextCursor.MoveOperation.Left)
            end_block = cursor.blockNumber()

            cursor.beginEditBlock()

            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)

            for _ in range(end_block - start_block + 1):
                cursor.insertText(indent_char)
                cursor.movePosition(QTextCursor.MoveOperation.Down)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)

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
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            start_block = cursor.blockNumber()

            cursor.setPosition(end)
            if cursor.atBlockStart():
                cursor.movePosition(QTextCursor.MoveOperation.Left)
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
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
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
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
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
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 4)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 3)
        else:
            pos = cursor.position()
            cursor.insertText("[text](url)")
            cursor.setPosition(pos + 1)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 4)

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
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 3)

        self.setTextCursor(cursor)

    def increase_heading(self):
        """Increase heading level."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)

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
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)

        block_text = cursor.block().text()
        match = re.match(r"^(#{1,6})\s", block_text)

        if match:
            hashes = match.group(1)
            if len(hashes) == 1:
                # Remove heading entirely
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(hashes) + 1
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

    # Mouse event handling
    def mousePressEvent(self, event):
        """Handle mouse press events - Ctrl+click opens links."""
        if (event.button() == Qt.MouseButton.LeftButton and
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # Get cursor position at click
            cursor = self.cursorForPosition(event.pos())
            link = self._find_link_at_cursor(cursor)
            if link:
                self.link_ctrl_clicked.emit(link)
                return
        super().mousePressEvent(event)

    def _find_link_at_cursor(self, cursor: QTextCursor) -> str | None:
        """Find a markdown link at the cursor position."""
        line = cursor.block().text()
        pos_in_line = cursor.positionInBlock()

        # Check for wiki link [[target]] or [[target|display]]
        # Wiki links conventionally refer to markdown files, so add .md if no extension
        wiki_pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
        for match in wiki_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                target = match.group(1).strip()
                # Add .md extension for wiki links without extension
                if '.' not in Path(target).name:
                    target = target + '.md'
                return target

        # Check for markdown link [text](url) - return URL as-is
        md_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
        for match in md_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                return match.group(2).strip()

        # Check for bare URLs
        url_pattern = re.compile(r'https?://[^\s<>\[\]()]+')
        for match in url_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                return match.group(0)

        return None

    def _find_link_range_at_cursor(self, cursor: QTextCursor) -> tuple[int, int] | None:
        """Find the document position range of a link at cursor. Returns (start, end) or None."""
        line = cursor.block().text()
        pos_in_line = cursor.positionInBlock()
        block_start = cursor.block().position()

        # Check for wiki link [[target]] or [[target|display]]
        wiki_pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
        for match in wiki_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                return (block_start + match.start(), block_start + match.end())

        # Check for markdown link [text](url)
        md_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
        for match in md_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                return (block_start + match.start(), block_start + match.end())

        # Check for bare URLs
        url_pattern = re.compile(r'https?://[^\s<>\[\]()]+')
        for match in url_pattern.finditer(line):
            if match.start() <= pos_in_line <= match.end():
                return (block_start + match.start(), block_start + match.end())

        return None

    def mouseMoveEvent(self, event):
        """Handle mouse move - show link cursor and highlight when Ctrl+hovering."""
        ctrl_pressed = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier

        if ctrl_pressed:
            cursor = self.cursorForPosition(event.pos())
            link_range = self._find_link_range_at_cursor(cursor)

            if link_range != self._hover_link_range:
                self._hover_link_range = link_range
                self._update_link_highlight()

            if link_range:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            if self._hover_link_range is not None:
                self._hover_link_range = None
                self._update_link_highlight()
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

        super().mouseMoveEvent(event)

    def _update_link_highlight(self):
        """Update the extra selection for link highlighting."""
        if self._hover_link_range:
            start, end = self._hover_link_range
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            # Style: blue color + underline
            fmt = selection.format
            fmt.setForeground(QColor("#0066cc"))
            fmt.setFontUnderline(True)
            selection.format = fmt

            # Preserve existing extra selections (like current line highlight) and add ours
            existing = [s for s in self.extraSelections()
                       if s.format.property(QTextFormat.Property.FullWidthSelection)]
            self.setExtraSelections(existing + [selection])
        else:
            # Remove link highlight, keep other selections
            existing = [s for s in self.extraSelections()
                       if s.format.property(QTextFormat.Property.FullWidthSelection)]
            self.setExtraSelections(existing)

    # Key event handling
    def keyPressEvent(self, event):
        """Handle key press events."""
        # Handle Ctrl key press for link hover highlight
        if event.key() == Qt.Key.Key_Control:
            # Check if mouse is over a link and update highlight
            pos = self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(pos):
                cursor = self.cursorForPosition(pos)
                link_range = self._find_link_range_at_cursor(cursor)
                if link_range:
                    self._hover_link_range = link_range
                    self._update_link_highlight()
                    self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

        # Wiki link completer navigation
        if self.wiki_link_completer and self.wiki_link_completer.isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                self.wiki_link_completer.keyPressEvent(event)
                return

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
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
                    self.setTextCursor(cursor)
                    # Check for wiki link trigger after [[
                    if char == '[':
                        QTimer.singleShot(0, self._check_wiki_link_trigger)
                    return

            # Handle closing character - skip if next char is the same
            if char in self.AUTO_PAIRS.values():
                cursor = self.textCursor()
                if not cursor.atEnd():
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
                    next_char = cursor.selectedText()
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
                    if next_char == char:
                        cursor.movePosition(QTextCursor.MoveOperation.Right)
                        self.setTextCursor(cursor)
                        return

        # Auto-indent on Enter
        if event.key() == Qt.Key.Key_Return and self.settings.get("editor.auto_indent", True):
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

        # Tab for snippet expansion or indent
        if event.key() == Qt.Key.Key_Tab:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.outdent_selection()
            else:
                # Try to expand snippet first
                if not self.try_expand_snippet():
                    self.indent_selection()
            return

        if event.key() == Qt.Key.Key_Backtab:
            self.outdent_selection()
            return

        super().keyPressEvent(event)

        # Check for wiki link trigger after typing
        if event.text() and not event.modifiers():
            QTimer.singleShot(0, self._check_wiki_link_trigger)

    def keyReleaseEvent(self, event):
        """Handle key release events."""
        # Clear link hover highlight when Ctrl is released
        if event.key() == Qt.Key.Key_Control:
            if self._hover_link_range is not None:
                self._hover_link_range = None
                self._update_link_highlight()
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().keyReleaseEvent(event)

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

    # ==================== FOLDING SUPPORT ====================

    def _do_update_folding_regions(self):
        """Update the folding regions based on document content."""
        text = self.toPlainText()
        lines = text.split('\n')
        new_regions: dict[int, FoldingRegion] = {}

        in_code_block = False
        code_block_start = -1
        heading_stack: list[tuple[int, int]] = []  # (line, level)

        for i, line in enumerate(lines):
            # Track code blocks
            if line.strip().startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_block_start = i
                else:
                    in_code_block = False
                    if code_block_start >= 0 and i > code_block_start:
                        region = FoldingRegion(code_block_start, i, "code_block")
                        # Preserve fold state
                        if code_block_start in self.folding_regions:
                            region.is_folded = self.folding_regions[code_block_start].is_folded
                        new_regions[code_block_start] = region
                    code_block_start = -1
                continue

            if in_code_block:
                continue

            # Track headings
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))

                # Close any headings of same or higher level
                while heading_stack and heading_stack[-1][1] >= level:
                    start_line, _ = heading_stack.pop()
                    if i > start_line + 1:
                        region = FoldingRegion(start_line, i - 1, "heading")
                        if start_line in self.folding_regions:
                            region.is_folded = self.folding_regions[start_line].is_folded
                        new_regions[start_line] = region

                heading_stack.append((i, level))

        # Close remaining headings at end of document
        for start_line, _ in heading_stack:
            end_line = len(lines) - 1
            if end_line > start_line:
                region = FoldingRegion(start_line, end_line, "heading")
                if start_line in self.folding_regions:
                    region.is_folded = self.folding_regions[start_line].is_folded
                new_regions[start_line] = region

        self.folding_regions = new_regions

    def toggle_fold_at_line(self, line: int):
        """Toggle folding at the given line."""
        if line in self.folding_regions:
            region = self.folding_regions[line]
            region.is_folded = not region.is_folded
            self._apply_folding()

    def fold_all(self):
        """Fold all regions."""
        for region in self.folding_regions.values():
            region.is_folded = True
        self._apply_folding()

    def unfold_all(self):
        """Unfold all regions."""
        for region in self.folding_regions.values():
            region.is_folded = False
        self._apply_folding()

    def _apply_folding(self):
        """Apply the current folding state to the document."""
        self.folded_blocks.clear()

        # Collect all folded line ranges
        for region in self.folding_regions.values():
            if region.is_folded:
                for line in range(region.start_line + 1, region.end_line + 1):
                    self.folded_blocks.add(line)

        # Apply visibility to blocks
        block = self.document().begin()
        while block.isValid():
            line_num = block.blockNumber()
            visible = line_num not in self.folded_blocks
            block.setVisible(visible)
            block = block.next()

        # Update the document layout
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def is_line_foldable(self, line: int) -> bool:
        """Check if a line is foldable."""
        return line in self.folding_regions

    def is_line_folded(self, line: int) -> bool:
        """Check if a line's region is folded."""
        if line in self.folding_regions:
            return self.folding_regions[line].is_folded
        return False

    # ==================== PASTE IMAGE ====================

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        """Check if we can handle the mime data."""
        if source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData):
        """Handle paste from mime data, including images."""
        if source.hasImage():
            self._paste_image(source)
        else:
            super().insertFromMimeData(source)

    def _paste_image(self, source: QMimeData):
        """Paste an image from clipboard."""
        image = QImage(source.imageData())
        if image.isNull():
            return

        # Determine save location
        if self.file_path:
            # Save relative to current file
            images_dir = self.file_path.parent / "images"
        else:
            # Ask user where to save
            folder = QFileDialog.getExistingDirectory(
                self, "Select Images Folder", str(Path.home())
            )
            if not folder:
                return
            images_dir = Path(folder)

        # Create images directory if needed
        images_dir.mkdir(exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}_{uuid.uuid4().hex[:8]}.png"
        image_path = images_dir / filename

        # Save the image
        if image.save(str(image_path)):
            # Insert markdown image link
            if self.file_path:
                # Use relative path
                rel_path = image_path.relative_to(self.file_path.parent)
                markdown = f"![image]({rel_path})"
            else:
                markdown = f"![image]({image_path})"

            cursor = self.textCursor()
            cursor.insertText(markdown)

    # ==================== WIKI LINKS ====================

    def set_available_links(self, links: list[str]):
        """Set the list of available wiki links for autocomplete."""
        self._available_links = links

    def _check_wiki_link_trigger(self):
        """Check if we should show wiki link autocomplete."""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        # Look for [[ pattern before cursor
        if col >= 2:
            text_before = block_text[:col]
            bracket_pos = text_before.rfind('[[')
            if bracket_pos >= 0:
                # Check if we're still inside [[...]]
                close_bracket = text_before.find(']]', bracket_pos)
                if close_bracket < 0:
                    # We're inside an open wiki link
                    prefix = text_before[bracket_pos + 2:]
                    self._wiki_link_prefix = prefix
                    self._show_wiki_completions(prefix)
                    return True

        if self.wiki_link_completer:
            self.wiki_link_completer.hide()
        return False

    def _show_wiki_completions(self, prefix: str):
        """Show wiki link completions."""
        if not self._available_links or not self.wiki_link_completer:
            return

        prefix_lower = prefix.lower()
        matches = [
            link for link in self._available_links
            if prefix_lower in link.lower()
        ]

        if matches:
            cursor_rect = self.cursorRect()
            pos = self.mapToGlobal(cursor_rect.bottomLeft())
            self.wiki_link_completer.show_completions(matches, pos)
        else:
            self.wiki_link_completer.hide()

    def _insert_wiki_link(self, link: str):
        """Insert a wiki link at the current cursor position."""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        # Find the [[ position
        text_before = block_text[:col]
        bracket_pos = text_before.rfind('[[')

        if bracket_pos >= 0:
            # Select from [[ to cursor
            cursor.setPosition(cursor.block().position() + bracket_pos)
            cursor.setPosition(
                cursor.block().position() + col,
                QTextCursor.MoveMode.KeepAnchor
            )
            cursor.insertText(f"[[{link}]]")

    # ==================== SNIPPETS ====================

    def get_snippet_manager(self):
        """Get the snippet manager."""
        if self._snippet_manager is None:
            from fun.markdown6.snippets import get_snippet_manager
            self._snippet_manager = get_snippet_manager()
        return self._snippet_manager

    def try_expand_snippet(self) -> bool:
        """Try to expand a snippet at the cursor position."""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        # Find potential trigger word (starts with /)
        text_before = block_text[:col]
        match = re.search(r'/\w+$', text_before)

        if match:
            trigger = match.group()
            manager = self.get_snippet_manager()
            snippet = manager.get_snippet(trigger)

            if snippet:
                # Select the trigger text
                start_pos = cursor.block().position() + match.start()
                cursor.setPosition(start_pos)
                cursor.setPosition(
                    cursor.block().position() + col,
                    QTextCursor.MoveMode.KeepAnchor
                )

                # Insert expanded snippet
                content, placeholder_start, placeholder_end = manager.expand_snippet(snippet)
                insert_pos = cursor.position()
                cursor.insertText(content)

                # Select first placeholder if present
                if placeholder_start >= 0:
                    cursor.setPosition(insert_pos + placeholder_start)
                    cursor.setPosition(insert_pos + placeholder_end, QTextCursor.MoveMode.KeepAnchor)
                    self.setTextCursor(cursor)

                return True

        return False

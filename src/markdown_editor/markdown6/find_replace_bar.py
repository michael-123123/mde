"""Find and replace bar widget for the Markdown editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.enhanced_editor import EnhancedEditor


class FindReplaceBar(QWidget):
    """A find/replace bar widget."""

    def __init__(
        self,
        editor: EnhancedEditor,
        preview: QWidget,
        use_webengine: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.editor = editor
        self.preview = preview
        self._use_webengine = use_webengine
        self.last_search = ""
        self._editor_found = False
        self._preview_found = False
        self._find_generation = 0
        self._preview_active_match = 0  # which match WebEngine is on (1-based)
        self._init_ui()
        if self._use_webengine:
            self.whole_word_checkbox.setToolTip(
                "Whole word matching applies to editor only "
                "(not supported in WebEngine preview)"
            )
        self.hide()

    def _init_ui(self):
        """Set up the find/replace bar UI."""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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
        self.case_checkbox.stateChanged.connect(self._on_option_changed)
        self.whole_word_checkbox = QCheckBox("Whole word")
        self.whole_word_checkbox.stateChanged.connect(self._on_option_changed)

        self.find_prev_btn = QPushButton("Previous")
        self.find_prev_btn.clicked.connect(self.find_previous)
        self.find_next_btn = QPushButton("Next")
        self.find_next_btn.clicked.connect(self.find_next)

        self.match_label = QLabel("")
        self.match_label.setMinimumWidth(150)

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
        was_visible = self.isVisible()
        self.replace_row_widget.hide()
        self.show()
        self.find_input.setFocus()
        if was_visible:
            self.find_input.selectAll()
        else:
            self.find_input.clear()

    def show_replace(self):
        """Show the find and replace bar."""
        was_visible = self.isVisible()
        self.replace_row_widget.show()
        self.show()
        self.find_input.setFocus()
        if was_visible:
            self.find_input.selectAll()
        else:
            self.find_input.clear()

    def hide_bar(self):
        """Hide the find/replace bar."""
        self._clear_preview_search()
        self.hide()
        self.editor.setFocus()

    def _select_current_word(self):
        """Pre-fill search with selected text or word under cursor."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_input.setText(cursor.selectedText())
        else:
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            word = cursor.selectedText()
            if word:
                self.find_input.setText(word)

    def _on_search_text_changed(self, text: str):
        """Handle search text changes for live search."""
        if text:
            self._find(text, forward=True, wrap=True, from_start=True)
        else:
            self._clear_preview_search()
            self.match_label.setText("")

    def _get_find_flags(self) -> QTextDocument.FindFlag:
        """Get the current find flags based on checkboxes."""
        flags = QTextDocument.FindFlag(0)
        if self.case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_word_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags

    def _find(
        self,
        text: str,
        forward: bool = True,
        wrap: bool = True,
        from_start: bool = False,
    ) -> bool:
        """Perform the find operation in both editor and preview panes."""
        if not text:
            self._clear_preview_search()
            self.match_label.setText("")
            return False

        # --- Editor search (always, even when hidden, to keep in sync) ---
        editor_found = False
        flags = self._get_find_flags()
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward

        cursor = self.editor.textCursor()
        if from_start:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)

        editor_found = self.editor.find(text, flags)

        if not editor_found and wrap:
            cursor = self.editor.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            editor_found = self.editor.find(text, flags)

        if editor_found:
            self.editor.centerCursor()

        self._editor_found = editor_found

        # --- Preview search (always, even when hidden, to keep in sync) ---
        self._find_in_preview(text, forward)
        # Always update status immediately with editor result.
        # For WebEngine, _on_preview_find_result will update again when the
        # async callback fires with the preview result.
        self._update_match_status()

        self.last_search = text
        return editor_found

    def _find_in_preview(self, text: str, forward: bool = True):
        """Highlight matching text in the preview pane."""
        if not text:
            self._clear_preview_search()
            return

        if self._use_webengine:
            from PySide6.QtWebEngineCore import QWebEnginePage as _QWEPage

            # QWebEnginePage.findText() supports case-sensitive but NOT whole-word matching.
            flags = _QWEPage.FindFlag(0)
            if self.case_checkbox.isChecked():
                flags |= _QWEPage.FindFlag.FindCaseSensitively
            if not forward:
                flags |= _QWEPage.FindFlag.FindBackward

            self._find_generation += 1
            gen = self._find_generation
            self.preview.page().findText(
                text, flags, lambda found, g=gen: self._on_preview_find_result(found, g)
            )
        else:
            flags = QTextDocument.FindFlag(0)
            if self.case_checkbox.isChecked():
                flags |= QTextDocument.FindFlag.FindCaseSensitively
            if self.whole_word_checkbox.isChecked():
                flags |= QTextDocument.FindFlag.FindWholeWords
            if not forward:
                flags |= QTextDocument.FindFlag.FindBackward
            self._preview_found = self.preview.find(text, flags)
            if self._preview_found:
                # Center the match in the viewport
                cursor_rect = self.preview.cursorRect()
                viewport_height = self.preview.viewport().height()
                scrollbar = self.preview.verticalScrollBar()
                scrollbar.setValue(
                    scrollbar.value() + cursor_rect.center().y() - viewport_height // 2
                )

    def _on_preview_find_result(self, result, generation: int):
        """Callback for QWebEnginePage.findText() async result.

        In PySide6/Qt6, the callback receives a QWebEngineFindTextResult
        with numberOfMatches() and activeMatch(), not a plain bool.
        """
        if generation != self._find_generation:
            return  # stale result from an earlier search
        # Handle both QWebEngineFindTextResult (Qt6) and bool (older API)
        if hasattr(result, 'numberOfMatches'):
            found = result.numberOfMatches() > 0
            self._preview_active_match = result.activeMatch() if found else 0
        else:
            found = bool(result)
        self._preview_found = found
        if found and self._use_webengine:
            self.preview.page().runJavaScript(
                "(() => {"
                "  const sel = window.getSelection();"
                "  if (sel.rangeCount) {"
                "    const el = sel.getRangeAt(0).startContainer.parentElement;"
                "    if (el) el.scrollIntoView({block: 'center'});"
                "  }"
                "})()"
            )
        self._update_match_status()

    def _clear_preview_search(self):
        """Clear any active search highlighting in the preview."""
        self._preview_found = False
        if self._use_webengine:
            self.preview.page().findText("")  # empty string clears highlights

    def _update_match_status(self):
        """Update the match label based on results from both panes."""
        if self._editor_found or self._preview_found:
            parts = []
            if self._editor_found:
                parts.append("editor")
            if self._preview_found:
                parts.append("preview")
            self.match_label.setText(f"Found in {', '.join(parts)}")
            self.match_label.setStyleSheet("color: green;")
        else:
            self.match_label.setText("Not found")
            self.match_label.setStyleSheet("color: red;")

    def _on_option_changed(self):
        """Re-run search when find options change."""
        text = self.find_input.text()
        if text:
            self._find(text, forward=True, wrap=True, from_start=True)

    def sync_visible_panes(self):
        """Scroll newly-visible panes to show the current match.

        Call this after toggling editor/preview visibility. Uses the
        editor cursor line as the source of truth and syncs the preview
        to the same position via the main window's line-ratio scroll.
        """
        if not self.isVisible() or not self.last_search:
            return

        text = self.last_search

        # Re-find in editor: move cursor to start of current selection,
        # then find forward so the editor scrolls to the match.
        if self._editor_found:
            cursor = self.editor.textCursor()
            cursor.setPosition(cursor.anchor())
            self.editor.setTextCursor(cursor)
            flags = self._get_find_flags()
            if self.editor.find(text, flags):
                self.editor.centerCursor()

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
        cursor.movePosition(QTextCursor.MoveOperation.Start)
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
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
        elif event.key() == Qt.Key.Key_F3:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.find_previous()
            else:
                self.find_next()
        else:
            super().keyPressEvent(event)

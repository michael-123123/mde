"""A simple Qt5 Markdown editor with split-screen editing and preview."""

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QShortcut,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension


class MarkdownEditor(QMainWindow):
    """A split-screen Markdown editor with live preview."""

    def __init__(self):
        super().__init__()
        self.current_file: Path | None = None
        self.unsaved_changes = False
        self._init_markdown()
        self._init_ui()
        self._init_shortcuts()
        self._connect_signals()

    def _init_markdown(self):
        """Initialize the Markdown converter with extensions."""
        self.md = markdown.Markdown(
            extensions=[
                "extra",
                FencedCodeExtension(),
                CodeHiliteExtension(css_class="highlight", guess_lang=False),
                TableExtension(),
                TocExtension(),
                "nl2br",
                "sane_lists",
            ]
        )

    def _init_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Markdown Editor")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Enter Markdown here...")
        editor_font = QFont("Monospace", 11)
        editor_font.setStyleHint(QFont.Monospace)
        self.editor.setFont(editor_font)
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setTabStopDistance(
            self.editor.fontMetrics().horizontalAdvance(" ") * 4
        )

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setStyleSheet(self._get_preview_stylesheet())

        splitter.addWidget(self.editor)
        splitter.addWidget(self.preview)
        splitter.setSizes([600, 600])

        layout.addWidget(splitter)

        self._create_menu_bar()
        self._create_status_bar()

        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._render_markdown)

    def _get_preview_stylesheet(self) -> str:
        """Return CSS for the preview pane."""
        return """
            QTextBrowser {
                background-color: #ffffff;
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                font-size: 14px;
                line-height: 1.6;
            }
        """

    def _get_html_template(self, content: str) -> str:
        """Wrap rendered markdown in HTML with styling."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #24292e;
                    max-width: 100%;
                    padding: 20px;
                    margin: 0;
                }}
                h1 {{
                    font-size: 2em;
                    font-weight: 600;
                    border-bottom: 1px solid #eaecef;
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h2 {{
                    font-size: 1.5em;
                    font-weight: 600;
                    border-bottom: 1px solid #eaecef;
                    padding-bottom: 0.3em;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h3 {{
                    font-size: 1.25em;
                    font-weight: 600;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                h4, h5, h6 {{
                    font-weight: 600;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }}
                p {{
                    margin-top: 0;
                    margin-bottom: 16px;
                }}
                code {{
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 85%;
                    background-color: rgba(27, 31, 35, 0.05);
                    padding: 0.2em 0.4em;
                    border-radius: 3px;
                }}
                pre {{
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                    font-size: 85%;
                    background-color: #f6f8fa;
                    padding: 16px;
                    overflow: auto;
                    border-radius: 6px;
                    line-height: 1.45;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                    font-size: 100%;
                }}
                blockquote {{
                    margin: 0;
                    padding: 0 1em;
                    color: #6a737d;
                    border-left: 0.25em solid #dfe2e5;
                }}
                ul, ol {{
                    padding-left: 2em;
                    margin-top: 0;
                    margin-bottom: 16px;
                }}
                li {{
                    margin-top: 0.25em;
                }}
                table {{
                    border-collapse: collapse;
                    margin-top: 0;
                    margin-bottom: 16px;
                    width: 100%;
                }}
                th, td {{
                    padding: 6px 13px;
                    border: 1px solid #dfe2e5;
                }}
                th {{
                    font-weight: 600;
                    background-color: #f6f8fa;
                }}
                tr:nth-child(even) {{
                    background-color: #f6f8fa;
                }}
                hr {{
                    height: 0.25em;
                    padding: 0;
                    margin: 24px 0;
                    background-color: #e1e4e8;
                    border: 0;
                }}
                a {{
                    color: #0366d6;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                img {{
                    max-width: 100%;
                    box-sizing: border-box;
                }}
                .highlight {{
                    background-color: #f6f8fa;
                    border-radius: 6px;
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        new_action = file_menu.addAction("&New")
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_file)

        open_action = file_menu.addAction("&Open...")
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)

        save_action = file_menu.addAction("&Save")
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)

        save_as_action = file_menu.addAction("Save &As...")
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)

        edit_menu = menubar.addMenu("&Edit")

        undo_action = edit_menu.addAction("&Undo")
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.editor.undo)

        redo_action = edit_menu.addAction("&Redo")
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self.editor.redo)

        edit_menu.addSeparator()

        cut_action = edit_menu.addAction("Cu&t")
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self.editor.cut)

        copy_action = edit_menu.addAction("&Copy")
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.editor.copy)

        paste_action = edit_menu.addAction("&Paste")
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.editor.paste)

        view_menu = menubar.addMenu("&View")

        refresh_action = view_menu.addAction("&Refresh Preview")
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._render_markdown)

    def _create_status_bar(self):
        """Create the status bar."""
        self.statusBar().showMessage("Ready")

    def _init_shortcuts(self):
        """Set up keyboard shortcuts."""
        refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_shortcut.activated.connect(self._render_markdown)

    def _connect_signals(self):
        """Connect widget signals to slots."""
        self.editor.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        """Handle text changes in the editor."""
        self.unsaved_changes = True
        self._update_title()
        self.render_timer.start(300)

    def _update_title(self):
        """Update the window title to reflect current file and save state."""
        title = "Markdown Editor"
        if self.current_file:
            title = f"{self.current_file.name} - {title}"
        if self.unsaved_changes:
            title = f"*{title}"
        self.setWindowTitle(title)

    def _render_markdown(self):
        """Convert markdown to HTML and display in preview pane."""
        text = self.editor.toPlainText()
        self.md.reset()
        html_content = self.md.convert(text)
        full_html = self._get_html_template(html_content)
        self.preview.setHtml(full_html)

    def new_file(self):
        """Create a new empty document."""
        if not self._check_unsaved_changes():
            return
        self.editor.clear()
        self.current_file = None
        self.unsaved_changes = False
        self._update_title()
        self.statusBar().showMessage("New file created")

    def open_file(self, file_path: str | Path | None = None):
        """Open a markdown file.

        Args:
            file_path: Optional path to open. If None, shows file dialog.
        """
        if not self._check_unsaved_changes():
            return

        # Qt's triggered signal passes a bool; treat non-string/Path as None
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

        try:
            content = path.read_text(encoding="utf-8")
            self.editor.setPlainText(content)
            self.current_file = path
            self.unsaved_changes = False
            self._update_title()
            self._render_markdown()
            self.statusBar().showMessage(f"Opened: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file: {e}")

    def save_file(self) -> bool:
        """Save the current file.

        Returns:
            True if save was successful, False otherwise.
        """
        if self.current_file is None:
            return self.save_file_as()

        try:
            self.current_file.write_text(
                self.editor.toPlainText(), encoding="utf-8"
            )
            self.unsaved_changes = False
            self._update_title()
            self.statusBar().showMessage(f"Saved: {self.current_file}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")
            return False

    def save_file_as(self) -> bool:
        """Save the current file with a new name.

        Returns:
            True if save was successful, False otherwise.
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown File",
            "",
            "Markdown Files (*.md);;All Files (*)",
        )
        if not file_path:
            return False

        self.current_file = Path(file_path)
        return self.save_file()

    def _check_unsaved_changes(self) -> bool:
        """Check for unsaved changes and prompt user.

        Returns:
            True if it's safe to proceed, False if user cancelled.
        """
        if not self.unsaved_changes:
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save them?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if reply == QMessageBox.Save:
            return self.save_file()
        elif reply == QMessageBox.Cancel:
            return False
        return True

    def closeEvent(self, event):
        """Handle window close event."""
        if self._check_unsaved_changes():
            event.accept()
        else:
            event.ignore()


def main():
    """Run the Markdown editor application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    editor = MarkdownEditor()
    editor.show()

    if len(sys.argv) > 1:
        editor.open_file(sys.argv[1])

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

"""A feature-rich Qt6 Markdown editor with split-screen editing and preview."""

import sys
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QKeySequence, QTextCursor, QTextDocument, QShortcut, QAction, QPalette, QColor
from PySide6.QtWidgets import (
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
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEnginePage = None  # type: ignore

import re

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension
from pygments.formatters import HtmlFormatter

from markdown_editor.markdown6 import export_service

# Cache HtmlFormatter instances to avoid recreation on every render
_html_formatter_cache: dict[str, HtmlFormatter] = {}


def get_cached_html_formatter(style: str) -> HtmlFormatter:
    """Get a cached HtmlFormatter for the given style."""
    if style not in _html_formatter_cache:
        _html_formatter_cache[style] = HtmlFormatter(style=style, cssclass="highlight")
    return _html_formatter_cache[style]



# Shared executor for background diagram rendering (mermaid/graphviz)
_diagram_executor = ThreadPoolExecutor(max_workers=4)


def _render_diagram(kind: str, source: str, dark_mode: bool) -> tuple[str, str]:
    """Render a single diagram in a thread. Returns (svg_html, css_class)."""
    try:
        if kind == 'mermaid':
            from markdown_editor.markdown6 import mermaid_service
            svg, _error = mermaid_service.render_mermaid(source, dark_mode)
            return svg, 'mermaid-diagram'
        else:
            from markdown_editor.markdown6 import graphviz_service
            svg, _error = graphviz_service.render_dot(source, dark_mode)
            return svg, 'graphviz-diagram'
    except Exception as e:
        import html
        return f'<div class="diagram-loading">Error: {html.escape(str(e))}</div>', 'mermaid-diagram'


def _export_diagram_to_file(kind: str, source: str, dark_mode: bool) -> str | None:
    """Render diagram source to an SVG temp file. Returns the file path or None."""
    import json
    import subprocess
    from markdown_editor.markdown6.temp_files import create_temp_file, create_temp_dir

    if kind == 'mermaid':
        from markdown_editor.markdown6.tool_paths import get_mmdc_path
        mmdc = get_mmdc_path()
        if not mmdc:
            return None
        work_dir = create_temp_dir(prefix='mmdc_')
        input_path = work_dir / 'input.mmd'
        output_path = work_dir / 'output.svg'
        config_path = work_dir / 'config.json'
        input_path.write_text(source, encoding='utf-8')
        config_path.write_text(json.dumps({
            'htmlLabels': False,
            'flowchart': {'htmlLabels': False},
        }))
        theme = 'dark' if dark_mode else 'default'
        subprocess.run(
            [mmdc, '-i', str(input_path), '-o', str(output_path),
             '-t', theme, '-b', 'transparent', '--quiet',
             '-c', str(config_path)],
            capture_output=True, timeout=15,
        )
        if output_path.exists():
            svg_path = create_temp_file(suffix='.svg', prefix='diagram_',
                                        content=output_path.read_bytes())
            return str(svg_path)
        return None
    else:
        from markdown_editor.markdown6 import graphviz_service
        svg, error = graphviz_service.render_dot(source, dark_mode)
        if error:
            return None
        svg_path = create_temp_file(suffix='.svg', prefix='diagram_', content=svg)
        return str(svg_path)


def apply_application_theme(dark_mode: bool):
    """Apply a light or dark theme to the entire application."""
    app = QApplication.instance()
    if not app:
        return

    theme = get_theme(dark_mode)

    if dark_mode:
        # Dark palette
        palette = QPalette()
        dark_bg = QColor(53, 53, 53)
        palette.setColor(QPalette.ColorRole.Window, dark_bg)
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.AlternateBase, dark_bg)
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, dark_bg)
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(35, 35, 35))
        # Set 3D effect colors to match background (eliminates Fusion style separator lines)
        palette.setColor(QPalette.ColorRole.Light, dark_bg)
        palette.setColor(QPalette.ColorRole.Midlight, dark_bg)
        palette.setColor(QPalette.ColorRole.Dark, dark_bg)
        palette.setColor(QPalette.ColorRole.Mid, dark_bg)
        palette.setColor(QPalette.ColorRole.Shadow, dark_bg)
        # Disabled colors
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        app.setPalette(palette)

    else:
        # Reset to default light theme
        app.setPalette(app.style().standardPalette())

    # Apply comprehensive stylesheet for elements that don't fully respect palette
    app.setStyleSheet(
        StyleSheets.main_window(theme) +
        StyleSheets.menu_bar(theme) +
        StyleSheets.menu(theme) +
        StyleSheets.tab_widget(theme) +
        StyleSheets.status_bar(theme) +
        StyleSheets.splitter(theme) +
        f"""
            QToolTip {{
                color: {theme.text_primary};
                background-color: {theme.bg_tertiary};
                border: 1px solid {theme.border};
            }}
        """
    )


def convert_lists_for_qtextbrowser(html: str) -> str:
    """Convert HTML lists to div/p elements that QTextBrowser renders correctly.

    QTextBrowser has poor support for <ul>/<ol>/<li> elements. This function
    converts them to <div> blocks with bullet/number characters.
    """
    # Track list nesting for proper indentation
    def replace_ul(match):
        content = match.group(1)
        # Convert <li> items to <p> with bullet
        items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
        result = '<div style="margin: 8px 0;">'
        for item in items:
            result += f'<p style="margin: 2px 0; margin-left: 20px;">• {item.strip()}</p>'
        result += '</div>'
        return result

    def replace_ol(match):
        content = match.group(1)
        # Convert <li> items to <p> with numbers
        items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
        result = '<div style="margin: 8px 0;">'
        for i, item in enumerate(items, 1):
            result += f'<p style="margin: 2px 0; margin-left: 20px;">{i}. {item.strip()}</p>'
        result += '</div>'
        return result

    # Replace unordered lists
    html = re.sub(r'<ul[^>]*>(.*?)</ul>', replace_ul, html, flags=re.DOTALL | re.IGNORECASE)
    # Replace ordered lists
    html = re.sub(r'<ol[^>]*>(.*?)</ol>', replace_ol, html, flags=re.DOTALL | re.IGNORECASE)

    return html


from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
from markdown_editor.markdown6.settings import get_settings
from markdown_editor.markdown6.theme import get_theme, StyleSheets
from markdown_editor.markdown6.settings_dialog import SettingsDialog
from markdown_editor.markdown6.outline_panel import OutlinePanel
from markdown_editor.markdown6.references_panel import ReferencesPanel
from markdown_editor.markdown6.command_palette import CommandPalette, Command
from markdown_editor.markdown6.table_editor import TableEditorDialog
from markdown_editor.markdown6.snippets import get_snippet_manager, SnippetPopup
from markdown_editor.markdown6.project_manager import ProjectPanel
from markdown_editor.markdown6.sidebar import Sidebar
from markdown_editor.markdown6.search_panel import SearchPanel
from markdown_editor.markdown6.markdown_extensions import (
    BreaklessListExtension,
    CalloutExtension,
    LogseqExtension,
    WikiLinkExtension,
    MathExtension,
    MermaidExtension,
    GraphvizExtension,
    TaskListExtension,
    get_callout_css,
    get_math_js,
    get_mermaid_js,
    get_mermaid_css,
    get_tasklist_css,
)
from markdown_editor.markdown6 import graphviz_service
from markdown_editor.markdown6 import mermaid_service
from markdown_editor.markdown6.graph_export import GraphExportDialog


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


# Custom WebEnginePage to intercept link clicks
if HAS_WEBENGINE:
    class LinkInterceptPage(QWebEnginePage):
        """Custom QWebEnginePage that intercepts link clicks."""

        link_clicked = Signal(QUrl)
        open_image_requested = Signal(QUrl)

        def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
            """Intercept navigation requests to handle link clicks."""
            if url.scheme() == 'open-image':
                self.open_image_requested.emit(url)
                return False

            # Only intercept link clicks in the main frame
            if is_main_frame and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                self.link_clicked.emit(url)
                return False

            # Allow all other navigation (setHtml, reloads, etc.)
            return True


class DocumentTab(QWidget):
    """A single document tab with editor and preview panes."""

    link_clicked = Signal(QUrl)  # Emitted when a link is clicked in the preview

    def __init__(self, parent: "MarkdownEditor"):
        super().__init__()
        self.main_window = parent
        self.settings = get_settings()
        self.file_path: Path | None = None
        self.unsaved_changes = False
        self._sync_scrolling = True
        self._preview_needs_full_reload = True
        self._preview_zoom_factor = 1.0
        self._pending_render_generation = 0  # bumped on each render to discard stale results

        self._init_ui()
        self._init_timer()
        self._connect_signals()

    def _init_ui(self):
        """Set up the tab's user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter with editor and preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Editor container
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self.editor = EnhancedEditor()
        self.editor.setAcceptDrops(True)
        self.editor.setAccessibleName("Markdown Editor")

        editor_layout.addWidget(self.editor)

        # Preview pane - use QWebEngineView if available for better CSS support
        if HAS_WEBENGINE:
            self.preview = QWebEngineView()
            # Use custom page to intercept link clicks
            self._custom_page = LinkInterceptPage(self.preview)
            self._custom_page.link_clicked.connect(self._on_link_clicked)
            self._custom_page.open_image_requested.connect(self._on_open_image)
            self._custom_page.linkHovered.connect(self._on_link_hovered)
            self.preview.setPage(self._custom_page)
            self._use_webengine = True
        else:
            self.preview = QTextBrowser()
            # Don't auto-open external links, handle them manually
            self.preview.setOpenExternalLinks(False)
            self.preview.anchorClicked.connect(self._on_link_clicked)
            # Enable mouse tracking for link tooltips
            self.preview.setMouseTracking(True)
            self.preview.mouseMoveEvent = self._preview_mouse_move
            self._use_webengine = False
        self._apply_preview_style()

        self.splitter.addWidget(editor_container)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([600, 600])

        # Find/Replace bar spans both panes (below splitter)
        self.find_replace_bar = FindReplaceBar(
            self.editor, self.preview, self._use_webengine, self
        )

        layout.addWidget(self.splitter)
        layout.addWidget(self.find_replace_bar)

        # Apply settings
        self._apply_settings()

    def _apply_preview_style(self):
        """Apply styling to the preview pane."""
        theme = self.settings.get("view.theme", "light")

        # QWebEngineView - set page background color
        if self._use_webengine:
            from PySide6.QtGui import QColor
            if theme == "dark":
                self.preview.page().setBackgroundColor(QColor("#1e1e1e"))
            else:
                self.preview.page().setBackgroundColor(QColor("#ffffff"))
            return

        # QTextBrowser widget styling
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

    def _on_link_clicked(self, url: QUrl):
        """Handle link clicks in the preview, forwarding to the main window."""
        self.link_clicked.emit(url)

    def _on_open_image(self, url: QUrl):
        """Handle Ctrl+click on images/diagrams in the preview."""
        from urllib.parse import unquote, parse_qs

        host = url.host()
        if host == 'diagram':
            # Rendered diagram — get source from JS, re-render with native text
            kind = parse_qs(url.query()).get('kind', ['mermaid'])[0]
            self.preview.page().runJavaScript(
                'window._pendingDiagramSource || ""',
                lambda source, _kind=kind: self._export_diagram(source, _kind),
            )
        elif host == 'img':
            # Linked image — src is in query param
            src = unquote(url.query().replace('src=', '', 1)) if url.query().startswith('src=') else ''
            if not src:
                return
            img_url = QUrl(src)
            if img_url.isLocalFile():
                QDesktopServices.openUrl(img_url)
            elif img_url.scheme() in ('http', 'https'):
                QDesktopServices.openUrl(img_url)
            else:
                # Relative path — resolve against document dir
                if self.file_path:
                    resolved = self.file_path.parent / src
                    if resolved.exists():
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))

    def _export_diagram(self, source: str, kind: str):
        """Re-render diagram source to SVG with native text and open it."""
        if not source:
            return
        import html as html_mod
        source = html_mod.unescape(source)
        dark_mode = self.settings.get("view.theme") == "dark"

        # Override cursor app-wide — survives Ctrl keyup and CSS changes
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        future = _diagram_executor.submit(
            _export_diagram_to_file, kind, source, dark_mode,
        )

        def poll():
            if future.done():
                try:
                    svg_path = future.result()
                except Exception:
                    QApplication.restoreOverrideCursor()
                    return
                if svg_path:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(svg_path))
                QApplication.restoreOverrideCursor()
            else:
                QTimer.singleShot(100, poll)

        QTimer.singleShot(100, poll)

    def _on_link_hovered(self, url: str):
        """Handle link hover in the preview, showing URL as tooltip."""
        if url:
            self.preview.setToolTip(url)
        else:
            self.preview.setToolTip("")

    def _preview_mouse_move(self, event):
        """Handle mouse move in QTextBrowser to show link tooltips."""
        anchor = self.preview.anchorAt(event.pos())
        if anchor:
            self.preview.setToolTip(anchor)
        else:
            self.preview.setToolTip("")
        # Call the parent class method
        QTextBrowser.mouseMoveEvent(self.preview, event)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.show_preview":
            self.preview.setVisible(value)
        elif key == "view.sync_scrolling":
            self._sync_scrolling = value
        elif key == "view.theme":
            self._apply_preview_style()
            # Re-render preview with new theme (full reload needed)
            self._preview_needs_full_reload = True
            self.render_markdown()
        elif key == "view.preview_font_size":
            # Re-render preview with new font size (full reload needed)
            self._preview_needs_full_reload = True
            self.render_markdown()

    def preview_zoom_in(self):
        """Zoom in the preview pane (text + images + diagrams)."""
        if self._preview_zoom_factor < 5.0:
            self._preview_zoom_factor += 0.1
            self._apply_preview_zoom()

    def preview_zoom_out(self):
        """Zoom out the preview pane (text + images + diagrams)."""
        if self._preview_zoom_factor > 0.3:
            self._preview_zoom_factor -= 0.1
            self._apply_preview_zoom()

    def preview_zoom_reset(self):
        """Reset preview zoom to 1.0."""
        self._preview_zoom_factor = 1.0
        self._apply_preview_zoom()

    def _apply_preview_zoom(self):
        """Apply the current zoom factor to the preview.

        At 1x zoom, diagram SVGs use max-width:100% to fit the container.
        When zoomed (body.zoomed), CSS removes that constraint so
        setZoomFactor can scale them.
        """
        if self._use_webengine:
            self.preview.setZoomFactor(self._preview_zoom_factor)
            zoomed = "true" if abs(self._preview_zoom_factor - 1.0) > 0.01 else "false"
            self.preview.page().runJavaScript(
                f"document.body.classList.toggle('zoomed', {zoomed});"
            )

    def _on_text_changed(self):
        """Handle text changes in the editor."""
        if not self.unsaved_changes:
            self.unsaved_changes = True
            self.main_window.update_tab_title(self)
            self.main_window.update_window_title()
        self.render_timer.start(300)
        # Schedule debounced outline panel update
        if hasattr(self.main_window, '_schedule_outline_update'):
            self.main_window._schedule_outline_update()

    def _on_file_externally_modified(self):
        """Handle external file modification."""
        reply = QMessageBox.question(
            self,
            "File Changed",
            f"The file '{self.file_path.name}' has been modified outside the editor.\n"
            "Do you want to reload it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
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
        """Convert markdown to HTML and display in preview pane.

        Diagrams whose SVGs are already cached are inlined immediately.
        Uncached diagrams get a placeholder that is filled asynchronously
        by _render_pending_diagrams(), keeping the preview responsive.
        """
        import json

        text = self.editor.toPlainText()
        self.main_window.md.reset()
        self.main_window.md._pending_diagrams = []

        # Set diagram config before conversion
        dark_mode = self.settings.get("view.theme") == "dark"
        self.main_window.md.graphviz_dark_mode = dark_mode
        self.main_window.md.graphviz_base_path = str(self.file_path.parent) if self.file_path else None
        self.main_window.md.mermaid_dark_mode = dark_mode
        self.main_window.md.logseq_mode = self.settings.get("view.logseq_mode", False)

        html_content = self.main_window.md.convert(text)
        pending = self.main_window.md._pending_diagrams

        # For QWebEngineView: use incremental JS update to preserve scroll position
        if self._use_webengine and not self._preview_needs_full_reload:
            escaped = json.dumps(html_content)
            js = f"document.getElementById('md-content').innerHTML = {escaped};"
            js += """
            if (typeof renderMathInElement !== 'undefined') {
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '$', right: '$', display: false}
                    ]
                });
            }
            if (typeof mermaid !== 'undefined') {
                mermaid.init(undefined, document.querySelectorAll('.mermaid:not([data-processed])'));
            }
            """
            self.preview.page().runJavaScript(js)
            # Re-apply zoom max-width toggle for new SVGs
            self._apply_preview_zoom()
            self._render_pending_diagrams(pending)
            return

        # Convert lists for QTextBrowser since it doesn't render <ul>/<li> properly
        if not self._use_webengine:
            html_content = convert_lists_for_qtextbrowser(html_content)
        full_html = self.main_window.get_html_template(
            html_content, for_qtextbrowser=not self._use_webengine
        )
        # Set base URL for relative link resolution
        if self.file_path:
            base_url = QUrl.fromLocalFile(str(self.file_path.parent) + "/")
        else:
            base_url = QUrl()

        if not self._use_webengine:
            # QTextBrowser: save/restore scroll position around setHtml
            scrollbar = self.preview.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.preview.setHtml(full_html, base_url)
            scrollbar.setValue(scroll_pos)
        else:
            # Full reload for QWebEngineView (initial load or theme/font change)
            self.preview.setHtml(full_html, base_url)
            self._preview_needs_full_reload = False
            # Re-apply zoom factor after setHtml
            self._apply_preview_zoom()
            self._render_pending_diagrams(pending)

    def _render_pending_diagrams(self, pending: list):
        """Dispatch background workers for uncached diagram placeholders.

        Uses a ThreadPoolExecutor to render diagrams off the main thread.
        A QTimer polls for completed futures and injects results via JS.
        A generation counter discards results from stale renders.
        """
        if not pending or not self._use_webengine:
            return
        self._pending_render_generation += 1
        gen = self._pending_render_generation
        futures = []
        for idx, (kind, source, dark_mode) in enumerate(pending):
            future = _diagram_executor.submit(_render_diagram, kind, source, dark_mode)
            futures.append((idx, future))
        self._poll_diagram_futures(futures, gen)

    def _poll_diagram_futures(self, futures: list, generation: int):
        """Poll pending futures and inject completed diagrams into preview."""
        import json
        if generation != self._pending_render_generation:
            return
        remaining = []
        for idx, future in futures:
            if future.done():
                try:
                    svg_html, css_class = future.result()
                except Exception as e:
                    import html
                    svg_html = f'<div class="diagram-loading">Error: {html.escape(str(e))}</div>'
                    css_class = 'mermaid-diagram'
                escaped_svg = json.dumps(svg_html)
                js = f"""
                (function() {{
                    var el = document.getElementById('diagram-pending-{idx}');
                    if (el) {{
                        el.innerHTML = {escaped_svg};
                        el.classList.remove('diagram-loading');
                        el.classList.add('{css_class}');
                    }}
                }})();
                """
                self.preview.page().runJavaScript(js)
                self._apply_preview_zoom()
            else:
                remaining.append((idx, future))
        if remaining:
            QTimer.singleShot(
                100, lambda: self._poll_diagram_futures(remaining, generation)
            )

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
        self._set_application_icon()
        self._init_markdown()
        self._init_ui()
        self._init_actions()
        self._init_shortcuts()
        self._connect_signals()
        self.new_tab()
        self._update_recent_files_menu()
        self._restore_last_project()
        # Apply theme after all widgets are created
        self._apply_full_theme()

    def _set_application_icon(self):
        """Set the application icon for window and taskbar."""
        # Get the icons directory path
        icons_dir = Path(__file__).parent / "icons"

        # Create icon with multiple sizes for different displays
        icon = QIcon()

        # Add available PNG sizes (Qt will choose appropriate size)
        for png_file in ["208x128-solid.png", "66x40-solid.png", "48x30-solid.png"]:
            png_path = icons_dir / png_file
            if png_path.exists():
                icon.addFile(str(png_path))

        # Also try ICO file (contains multiple sizes, good for Windows)
        ico_path = icons_dir / "markdown-mark-solid-win10.ico"
        if ico_path.exists():
            icon.addFile(str(ico_path))

        # Set as window icon (appears in title bar and alt+tab)
        self.setWindowIcon(icon)

        # Also set as application icon for consistency
        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)

    def _init_markdown(self):
        """Initialize the Markdown converter with extensions."""
        self.md = markdown.Markdown(
            extensions=[
                "extra",
                LogseqExtension(),  # Priority 101 — strip Logseq syntax before everything else
                BreaklessListExtension(),  # Add blank lines before lists automatically
                FencedCodeExtension(),
                CodeHiliteExtension(css_class="highlight", guess_lang=True),
                TableExtension(),
                TocExtension(),
                CalloutExtension(),
                WikiLinkExtension(),
                MathExtension(),
                MermaidExtension(),
                GraphvizExtension(),
                TaskListExtension(),
            ]
        )

    def _init_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Markdown Editor")
        self.setGeometry(100, 100, 1400, 800)
        self.setAcceptDrops(True)

        # Main splitter: [Sidebar | Tab Widget]
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(1)
        self.setCentralWidget(self.main_splitter)

        # Sidebar with activity bar and panels
        self.sidebar = Sidebar()

        # Create panels
        self.project_panel = ProjectPanel()
        self.project_panel.file_double_clicked.connect(self.open_file)
        self.project_panel.graph_export_requested.connect(self._show_graph_export)
        self.project_panel.setAccessibleName("Project Files Panel")

        self.outline_panel = OutlinePanel()
        self.outline_panel.heading_clicked.connect(self._go_to_heading)
        self.outline_panel.setAccessibleName("Document Outline Panel")

        self.references_panel = ReferencesPanel()
        self.references_panel.reference_clicked.connect(self._go_to_reference)
        self.references_panel.setAccessibleName("References Panel")

        self.search_panel = SearchPanel()
        self.search_panel.file_requested.connect(self._on_search_file_requested)
        self.search_panel.setAccessibleName("Search Panel")

        # Add panels to sidebar (order matters for indices)
        self.sidebar.addPanel("Explorer", "📁", self.project_panel)      # index 0
        self.sidebar.addPanel("Outline", "📑", self.outline_panel)       # index 1
        self.sidebar.addPanel("References", "🔗", self.references_panel) # index 2
        self.sidebar.addPanel("Search", "🔍", self.search_panel)         # index 3

        # Connect sidebar signals
        self.sidebar.panel_changed.connect(self._on_sidebar_panel_changed)
        self.sidebar.collapsed_changed.connect(self._on_sidebar_collapsed_changed)
        self.sidebar.width_changed.connect(self._on_sidebar_width_changed)

        # Tab widget for documents
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.setAccessibleName("Document Tabs")

        # Add to splitter
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.tab_widget)

        # Set stretch factors (sidebar doesn't stretch, tab widget does)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        # View toggle buttons (editor/preview) in tab bar corner
        self._create_view_toggle_buttons()

        # Command palette
        self.command_palette = CommandPalette(self)

        self._create_menu_bar()
        self._create_status_bar()
        self._init_command_palette()
        self._init_debounce_timers()

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.new_action = file_menu.addAction("&New Tab")
        self.new_action.triggered.connect(self.new_tab)

        self.open_action = file_menu.addAction("&Open...")
        self.open_action.triggered.connect(self.open_file)

        self.open_project_action = file_menu.addAction("Open &Project Folder...")
        self.open_project_action.setShortcut(self.settings.get_shortcut("file.open_project"))
        self.open_project_action.triggered.connect(self._open_project)

        # Recent files submenu
        self.recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()

        self.save_action = file_menu.addAction("&Save")
        self.save_action.triggered.connect(self.save_file)

        self.save_as_action = file_menu.addAction("Save &As...")
        self.save_as_action.triggered.connect(self.save_file_as)

        file_menu.addSeparator()

        # Export submenu
        export_menu = QMenu("&Export", self)
        file_menu.addMenu(export_menu)

        self.export_html_action = export_menu.addAction("Export to &HTML...")
        self.export_html_action.triggered.connect(self._export_html)

        self.export_pdf_action = export_menu.addAction("Export to &PDF...")
        self.export_pdf_action.triggered.connect(self._export_pdf)

        self.export_docx_action = export_menu.addAction("Export to &DOCX...")
        self.export_docx_action.triggered.connect(self._export_docx)

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

        format_menu.addSeparator()

        # Insert submenu
        insert_menu = QMenu("&Insert", self)
        format_menu.addMenu(insert_menu)

        self.insert_table_action = insert_menu.addAction("&Table...")
        self.insert_table_action.triggered.connect(self._insert_table)

        self.insert_snippet_action = insert_menu.addAction("&Snippet...")
        self.insert_snippet_action.triggered.connect(self._show_snippet_popup)

        insert_menu.addSeparator()

        self.insert_math_action = insert_menu.addAction("&Math Block")
        self.insert_math_action.triggered.connect(self._insert_math)

        self.insert_mermaid_action = insert_menu.addAction("M&ermaid Diagram")
        self.insert_mermaid_action.triggered.connect(self._insert_mermaid)

        insert_menu.addSeparator()

        self.insert_callout_note_action = insert_menu.addAction("Callout: &Note")
        self.insert_callout_note_action.triggered.connect(lambda: self._insert_callout("NOTE"))

        self.insert_callout_warning_action = insert_menu.addAction("Callout: &Warning")
        self.insert_callout_warning_action.triggered.connect(lambda: self._insert_callout("WARNING"))

        self.insert_callout_tip_action = insert_menu.addAction("Callout: &Tip")
        self.insert_callout_tip_action.triggered.connect(lambda: self._insert_callout("TIP"))

        # View menu
        view_menu = menubar.addMenu("&View")

        # Command palette
        self.command_palette_action = view_menu.addAction("&Command Palette...")
        self.command_palette_action.triggered.connect(self._show_command_palette)

        view_menu.addSeparator()

        # Panels submenu
        panels_menu = QMenu("&Panels", self)
        view_menu.addMenu(panels_menu)

        self.toggle_outline_action = panels_menu.addAction("Toggle &Outline")
        self.toggle_outline_action.setCheckable(True)
        self.toggle_outline_action.setChecked(False)
        self.toggle_outline_action.triggered.connect(self._toggle_outline_panel)

        self.toggle_project_action = panels_menu.addAction("Toggle &Project Panel")
        self.toggle_project_action.setCheckable(True)
        self.toggle_project_action.setChecked(False)
        self.toggle_project_action.triggered.connect(self._toggle_project_panel)

        self.toggle_references_action = panels_menu.addAction("Toggle &References Panel")
        self.toggle_references_action.setCheckable(True)
        self.toggle_references_action.setChecked(False)
        self.toggle_references_action.triggered.connect(self._toggle_references_panel)

        self.toggle_search_action = panels_menu.addAction("Toggle &Search Panel")
        self.toggle_search_action.setCheckable(True)
        self.toggle_search_action.setChecked(False)
        self.toggle_search_action.triggered.connect(self._toggle_search_panel)

        panels_menu.addSeparator()

        self.toggle_sidebar_action = panels_menu.addAction("Toggle Si&debar")
        self.toggle_sidebar_action.triggered.connect(self._toggle_sidebar)

        view_menu.addSeparator()

        # Folding submenu
        folding_menu = QMenu("&Folding", self)
        view_menu.addMenu(folding_menu)

        self.fold_all_action = folding_menu.addAction("Fold &All")
        self.fold_all_action.triggered.connect(self._fold_all)

        self.unfold_all_action = folding_menu.addAction("&Unfold All")
        self.unfold_all_action.triggered.connect(self._unfold_all)

        view_menu.addSeparator()

        self.refresh_action = view_menu.addAction("&Refresh Preview")
        self.refresh_action.triggered.connect(self._refresh_preview)

        view_menu.addSeparator()

        self.toggle_preview_action = view_menu.addAction("Toggle &Preview")
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(self.settings.get("view.show_preview", True))
        self.toggle_preview_action.triggered.connect(self._toggle_preview)

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

        self.toggle_logseq_action = view_menu.addAction("&Logseq Mode")
        self.toggle_logseq_action.setCheckable(True)
        self.toggle_logseq_action.setChecked(self.settings.get("view.logseq_mode", False))
        self.toggle_logseq_action.triggered.connect(self._toggle_logseq_mode)

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

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        self.export_graph_action = tools_menu.addAction("Export Document &Graph...")
        self.export_graph_action.triggered.connect(self._show_graph_export)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = help_menu.addAction("&About")
        about_action.triggered.connect(self._show_about)

    def _init_actions(self):
        """Set shortcuts for actions based on settings."""
        action_map = {
            "file.new": self.new_action,
            "file.open": self.open_action,
            "file.open_project": self.open_project_action,
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
            "view.toggle_line_numbers": self.toggle_line_numbers_action,
            "view.toggle_word_wrap": self.toggle_word_wrap_action,
            "view.toggle_whitespace": self.toggle_whitespace_action,
            "view.toggle_logseq_mode": self.toggle_logseq_action,
            "view.zoom_in": self.zoom_in_action,
            "view.zoom_out": self.zoom_out_action,
            "view.zoom_reset": self.zoom_reset_action,
            "view.fullscreen": self.fullscreen_action,
            "view.command_palette": self.command_palette_action,
            "view.toggle_outline": self.toggle_outline_action,
            "view.toggle_project": self.toggle_project_action,
            "view.toggle_references": self.toggle_references_action,
            "view.toggle_search": self.toggle_search_action,
            "view.toggle_sidebar": self.toggle_sidebar_action,
            "view.fold_all": self.fold_all_action,
            "view.unfold_all": self.unfold_all_action,
            "insert.snippet": self.insert_snippet_action,
            "insert.table": self.insert_table_action,
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
        elif key == "view.theme":
            self._apply_full_theme()
        elif key == "editor.show_line_numbers":
            self.toggle_line_numbers_action.setChecked(value)
        elif key == "editor.word_wrap":
            self.toggle_word_wrap_action.setChecked(value)
        elif key == "editor.show_whitespace":
            self.toggle_whitespace_action.setChecked(value)
        elif key == "view.logseq_mode":
            self.toggle_logseq_action.setChecked(value)
            # Re-render preview to reflect the change
            tab = self.current_tab()
            if tab:
                tab.render_markdown()

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
            # Trigger initial updates (signals are connected once in new_tab)
            tab.editor._update_word_count()
            tab.editor._on_cursor_position_changed()
            # Focus the editor
            tab.editor.setFocus()
            # Update outline panel
            if self.outline_panel.isVisible():
                self._update_outline()
            # Update references panel
            self._update_references()

    def _update_word_count(self, words: int, chars: int):
        """Update word count in status bar."""
        self.word_count_label.setText(f"Words: {words} | Chars: {chars}")

    def _update_cursor_position(self, line: int, col: int):
        """Update cursor position in status bar."""
        self.cursor_pos_label.setText(f"Ln {line}, Col {col}")

    def update_window_title(self):
        """Update the window title to reflect current tab."""
        tab = self.current_tab()
        if tab and tab.file_path:
            full_path = tab.file_path.resolve()
            project_root = self.project_panel.project_path

            # Try to get relative path from project root
            if project_root:
                try:
                    relative_path = full_path.relative_to(project_root)
                    title = f"{project_root.name}/{relative_path}  ({full_path})"
                except ValueError:
                    # File is not under project root
                    title = f"{full_path.name}  ({full_path})"
            else:
                title = f"{full_path.name}  ({full_path})"
        elif tab:
            title = tab.get_tab_title()
        else:
            title = "Markdown Editor"
        self.setWindowTitle(title)

    def update_tab_title(self, tab: DocumentTab):
        """Update the title of a specific tab."""
        index = self.tab_widget.indexOf(tab)
        if index >= 0:
            self.tab_widget.setTabText(index, tab.get_tab_title())

    def get_html_template(self, content: str, for_qtextbrowser: bool = False) -> str:
        """Wrap rendered markdown in HTML with styling.

        Args:
            content: The HTML content to wrap.
            for_qtextbrowser: If True, generate simpler HTML for QTextBrowser.
        """
        theme = self.settings.get("view.theme", "light")
        dark_mode = theme == "dark"

        if dark_mode:
            bg_color = "#1e1e1e"
            text_color = "#d4d4d4"
            heading_border = "#333"
            code_bg = "#2d2d2d"
            blockquote_color = "#888"
            link_color = "#4ec9b0"
            pygments_style = "monokai"
            body_class = "dark"
        else:
            bg_color = "#ffffff"
            text_color = "#24292e"
            heading_border = "#eaecef"
            code_bg = "#f6f8fa"
            blockquote_color = "#6a737d"
            link_color = "#0366d6"
            pygments_style = "github-dark"
            body_class = "light"

        font_size = self.settings.get("view.preview_font_size", 14)

        # Generate Pygments CSS for syntax highlighting (use cached formatter)
        formatter = get_cached_html_formatter(pygments_style)
        pygments_css = formatter.get_style_defs(".highlight")

        # Get callout CSS
        callout_css = get_callout_css(dark_mode)

        # Get task list CSS
        tasklist_css = get_tasklist_css(dark_mode)

        # Get graphviz CSS and JS
        graphviz_css = graphviz_service.get_graphviz_css(dark_mode)
        graphviz_js = graphviz_service.get_graphviz_js() if not graphviz_service.has_graphviz() else ""

        # Get mermaid CSS and JS
        mermaid_css = get_mermaid_css(dark_mode)
        mermaid_js = get_mermaid_js()

        # Get math JS
        math_js = get_math_js()

        # QTextBrowser has limited CSS support, use simplified HTML
        if for_qtextbrowser:
            return f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-size: {font_size}px; color: {text_color}; background-color: {bg_color}; padding: 10px; }}
        h1 {{ font-size: 2em; font-weight: bold; }}
        h2 {{ font-size: 1.5em; font-weight: bold; }}
        h3 {{ font-size: 1.25em; font-weight: bold; }}
        code {{ background-color: {code_bg}; }}
        pre {{ background-color: {code_bg}; padding: 10px; }}
        blockquote {{ color: {blockquote_color}; margin-left: 20px; padding-left: 10px; border-left: 3px solid {heading_border}; }}
        a {{ color: {link_color}; }}
        table {{ border-collapse: collapse; }}
        th, td {{ border: 1px solid {heading_border}; padding: 5px; }}
        {pygments_css}
    </style>
</head>
<body>
{content}
</body>
</html>"""

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            {math_js}
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
                ul, ol {{
                    display: block;
                    padding-left: 2em;
                    margin-top: 0;
                    margin-bottom: 16px;
                    list-style-position: outside;
                }}
                ul {{ list-style-type: disc; }}
                ol {{ list-style-type: decimal; }}
                li {{
                    display: list-item;
                    margin-top: 0.25em;
                }}
                table {{ border-collapse: collapse; margin-top: 0; margin-bottom: 16px; width: 100%; }}
                th, td {{ padding: 6px 13px; border: 1px solid {heading_border}; }}
                th {{ font-weight: 600; background-color: {code_bg}; }}
                hr {{ height: 0.25em; padding: 0; margin: 24px 0; background-color: {heading_border}; border: 0; }}
                a {{ color: {link_color}; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                img {{ max-width: 100%; box-sizing: border-box; }}
                /* Wiki links */
                a.wiki-link {{
                    color: {link_color};
                    border-bottom: 1px dashed {link_color};
                }}
                a.wiki-link:hover {{
                    border-bottom-style: solid;
                }}
                /* Math blocks */
                .math-block {{
                    overflow-x: auto;
                    padding: 16px 0;
                }}
                .math-inline {{
                    padding: 0 2px;
                }}
                /* Mermaid diagrams */
                .mermaid {{
                    background: {code_bg};
                    padding: 16px;
                    border-radius: 6px;
                    margin: 16px 0;
                    text-align: center;
                }}
                /* Pygments syntax highlighting */
                {pygments_css}
                /* Callouts */
                {callout_css}
                /* Graphviz */
                {graphviz_css}
                /* Mermaid */
                {mermaid_css}
                /* Task lists */
                {tasklist_css}
                /* When zoomed, let diagram SVGs scale instead of fitting container */
                body.zoomed .mermaid-diagram svg,
                body.zoomed .graphviz-diagram svg {{
                    max-width: none;
                }}
                /* Diagram loading placeholder */
                .diagram-loading {{
                    padding: 16px;
                    border-radius: 6px;
                    background: {code_bg};
                    margin: 8px 0;
                    text-align: left;
                }}
                .diagram-loading-source {{
                    font-size: 80%;
                    opacity: 0.5;
                    max-height: 120px;
                    overflow: hidden;
                    margin: 0 0 8px 0;
                    background: transparent;
                    padding: 0;
                }}
                .diagram-loading-spinner {{
                    color: {blockquote_color};
                    font-style: italic;
                    font-size: 0.9em;
                }}
                /* Ctrl+hover hint — only the hovered element */
                body.ctrl-held img,
                body.ctrl-held .mermaid-diagram svg,
                body.ctrl-held .graphviz-diagram svg {{
                    cursor: pointer;
                }}
                body.ctrl-held img:hover,
                body.ctrl-held .mermaid-diagram:hover svg,
                body.ctrl-held .graphviz-diagram:hover svg {{
                    filter: drop-shadow(0 0 3px {link_color}) drop-shadow(0 0 1px {link_color});
                }}
            </style>
        </head>
        <body class="{body_class}">
            <div id="md-content">{content}</div>
            {mermaid_js}
            {graphviz_js}
            <script>
            /* Ctrl+click on images/diagrams → open in external app */
            document.addEventListener('mousemove', function(e) {{
                document.body.classList.toggle('ctrl-held', e.ctrlKey || e.metaKey);
            }});
            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Control' || e.key === 'Meta') document.body.classList.add('ctrl-held');
            }});
            document.addEventListener('keyup', function(e) {{
                if (e.key === 'Control' || e.key === 'Meta') document.body.classList.remove('ctrl-held');
            }});
            window.addEventListener('blur', function() {{
                document.body.classList.remove('ctrl-held');
            }});
            document.addEventListener('click', function(e) {{
                if (!e.ctrlKey && !e.metaKey) return;
                var el = e.target;
                while (el && el !== document.body) {{
                    if (el.tagName === 'IMG') {{
                        e.preventDefault();
                        e.stopPropagation();
                        window.location.href = 'open-image://img?src=' + encodeURIComponent(el.src);
                        return;
                    }}
                    if (el.tagName === 'svg' || (el.classList && (
                        el.classList.contains('mermaid-diagram') ||
                        el.classList.contains('graphviz-diagram')))) {{
                        var container = el.closest('.mermaid-diagram, .graphviz-diagram');
                        if (container && container.dataset.source) {{
                            e.preventDefault();
                            e.stopPropagation();
                            var kind = container.classList.contains('mermaid-diagram') ? 'mermaid' : 'graphviz';
                            window._pendingDiagramSource = container.dataset.source;
                            window.location.href = 'open-image://diagram?kind=' + kind;
                            return;
                        }}
                    }}
                    el = el.parentElement;
                }}
            }}, true);
            </script>
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
        dialog.exec()

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
        """Toggle preview visibility via menu - syncs with toggle button."""
        value = self.toggle_preview_action.isChecked()

        # Check if we can hide (editor must remain visible)
        if not value and not self.editor_toggle_btn.isChecked():
            # Can't hide both - re-check the action
            self.toggle_preview_action.setChecked(True)
            return

        # Update the toggle button (which will update visibility)
        self.preview_toggle_btn.setChecked(value)
        self._update_editor_preview_visibility()

    def _toggle_line_numbers(self):
        value = self.toggle_line_numbers_action.isChecked()
        self.settings.set("editor.show_line_numbers", value)

    def _toggle_word_wrap(self):
        value = self.toggle_word_wrap_action.isChecked()
        self.settings.set("editor.word_wrap", value)

    def _toggle_whitespace(self):
        value = self.toggle_whitespace_action.isChecked()
        self.settings.set("editor.show_whitespace", value)

    def _toggle_logseq_mode(self):
        value = self.toggle_logseq_action.isChecked()
        self.settings.set("view.logseq_mode", value)

    def _zoom_in(self):
        tab = self.current_tab()
        if tab:
            tab.editor.zoom_in()
            tab.preview_zoom_in()

    def _zoom_out(self):
        tab = self.current_tab()
        if tab:
            tab.editor.zoom_out()
            tab.preview_zoom_out()

    def _zoom_reset(self):
        tab = self.current_tab()
        if tab:
            tab.editor.zoom_reset()
            tab.preview_zoom_reset()

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self._is_fullscreen = True

    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        current = self.settings.get("view.theme", "light")
        new_theme = "dark" if current == "light" else "light"
        # Setting the theme triggers _on_setting_changed which calls _apply_full_theme
        self.settings.set("view.theme", new_theme)

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
        self._connect_tab_signals(tab)
        index = self.tab_widget.addTab(tab, tab.get_tab_title())
        self.tab_widget.setCurrentIndex(index)
        # Apply global visibility state to new tab
        self._apply_visibility_to_tab(tab)
        tab.editor.setFocus()
        self.status_bar.showMessage("New tab created")
        return tab

    def _connect_tab_signals(self, tab: DocumentTab):
        """Connect signals for a document tab."""
        tab.editor.word_count_changed.connect(self._update_word_count)
        tab.editor.cursor_position_changed.connect(self._update_cursor_position)
        tab.link_clicked.connect(self._handle_link_click)
        tab.editor.link_ctrl_clicked.connect(self._handle_editor_link_click)

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
                self._connect_tab_signals(tab)
                index = self.tab_widget.addTab(tab, "")
                self.tab_widget.setCurrentIndex(index)

                # Apply global visibility state to new tab
                self._apply_visibility_to_tab(tab)

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
            tab.editor._ignore_next_file_change = True
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
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            current_index = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentWidget(tab)
            result = self.save_file()
            self.tab_widget.setCurrentIndex(current_index)
            return result
        elif reply == QMessageBox.StandardButton.Cancel:
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
        self._save_open_files()
        event.accept()

    def _save_open_files(self):
        """Save the list of open file paths and active tab for session restore."""
        open_files = []
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab.file_path and tab.file_path.exists():
                open_files.append(str(tab.file_path.resolve()))
        self.settings.set("project.open_files", open_files)
        self.settings.set("project.active_tab", self.tab_widget.currentIndex())
        self.settings.set("sidebar.collapsed", self.sidebar.isCollapsed())
        self.settings.set("sidebar.active_panel", self.sidebar.activeIndex())
        self.project_panel.save_tree_state()

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Markdown Editor",
            "Markdown Editor (PySide6)\n\n"
            "A feature-rich Markdown editor with live preview.\n\n"
            "Features:\n"
            "• Split-screen editing and preview\n"
            "• Syntax highlighting\n"
            "• Multiple tabs\n"
            "• Find and replace\n"
            "• Customizable shortcuts\n"
            "• Dark/light themes\n"
            "• Outline/TOC panel\n"
            "• Command palette\n"
            "• Section folding\n"
            "• Math/LaTeX support\n"
            "• Mermaid diagrams\n"
            "• Callouts/admonitions\n"
            "• Wiki-style links\n"
            "• Snippets\n"
            "• Table editor\n"
            "• Project folders\n"
            "• And more!"
        )

    def _show_graph_export(self):
        """Show the document graph export dialog."""
        # Determine project root - prefer project panel, fall back to current file's directory
        project_root = None
        if hasattr(self, 'project_panel') and self.project_panel.project_path:
            project_root = self.project_panel.project_path
        else:
            tab = self.current_tab()
            if tab and tab.file_path:
                project_root = tab.file_path.parent

        if not project_root:
            QMessageBox.warning(
                self,
                "No Project",
                "Please open a project folder or save the current file first."
            )
            return

        # Get current file path if available
        current_file = None
        tab = self.current_tab()
        if tab and tab.file_path:
            current_file = tab.file_path

        dialog = GraphExportDialog(project_root, current_file, self)

        # Connect file click signal to open the file
        def open_file_from_graph(file_path: Path):
            self.open_file(str(file_path))

        dialog.file_clicked.connect(open_file_from_graph)

        dialog.exec()

    # ==================== COMMAND PALETTE ====================

    def _init_debounce_timers(self):
        """Initialize debounce timers for expensive operations."""
        # Outline panel update timer (debounce 500ms)
        self._outline_update_timer = QTimer()
        self._outline_update_timer.setSingleShot(True)
        self._outline_update_timer.timeout.connect(self._do_update_outline)

    def _schedule_outline_update(self):
        """Schedule a debounced outline update."""
        if self.outline_panel.isVisible():
            self._outline_update_timer.start(500)

    def _init_command_palette(self):
        """Initialize the command palette with available commands."""
        commands = []

        # File commands
        commands.append(Command("file.new", "New Tab", self.settings.get_shortcut("file.new"), self.new_tab, "File"))
        commands.append(Command("file.open", "Open File", self.settings.get_shortcut("file.open"), self.open_file, "File"))
        commands.append(Command("file.open_project", "Open Project Folder", self.settings.get_shortcut("file.open_project"), self._open_project, "File"))
        commands.append(Command("file.save", "Save", self.settings.get_shortcut("file.save"), self.save_file, "File"))
        commands.append(Command("file.save_as", "Save As", self.settings.get_shortcut("file.save_as"), self.save_file_as, "File"))

        # Edit commands
        commands.append(Command("edit.undo", "Undo", self.settings.get_shortcut("edit.undo"), self._undo, "Edit"))
        commands.append(Command("edit.redo", "Redo", self.settings.get_shortcut("edit.redo"), self._redo, "Edit"))
        commands.append(Command("edit.find", "Find", self.settings.get_shortcut("edit.find"), self._show_find, "Edit"))
        commands.append(Command("edit.replace", "Replace", self.settings.get_shortcut("edit.replace"), self._show_replace, "Edit"))
        commands.append(Command("edit.go_to_line", "Go to Line", self.settings.get_shortcut("edit.go_to_line"), self._go_to_line, "Edit"))

        # Format commands
        commands.append(Command("format.bold", "Bold", self.settings.get_shortcut("markdown.bold"), self._format_bold, "Format"))
        commands.append(Command("format.italic", "Italic", self.settings.get_shortcut("markdown.italic"), self._format_italic, "Format"))
        commands.append(Command("format.code", "Code", self.settings.get_shortcut("markdown.code"), self._format_code, "Format"))
        commands.append(Command("format.link", "Insert Link", self.settings.get_shortcut("markdown.link"), self._format_link, "Format"))
        commands.append(Command("format.image", "Insert Image", self.settings.get_shortcut("markdown.image"), self._format_image, "Format"))

        # Insert commands
        commands.append(Command("insert.table", "Insert Table", self.settings.get_shortcut("insert.table"), self._insert_table, "Insert"))
        commands.append(Command("insert.snippet", "Insert Snippet", self.settings.get_shortcut("insert.snippet"), self._show_snippet_popup, "Insert"))
        commands.append(Command("insert.math", "Insert Math Block", "", self._insert_math, "Insert"))
        commands.append(Command("insert.mermaid", "Insert Mermaid Diagram", "", self._insert_mermaid, "Insert"))
        commands.append(Command("insert.callout_note", "Insert Note Callout", "", lambda: self._insert_callout("NOTE"), "Insert"))
        commands.append(Command("insert.callout_warning", "Insert Warning Callout", "", lambda: self._insert_callout("WARNING"), "Insert"))
        commands.append(Command("insert.callout_tip", "Insert Tip Callout", "", lambda: self._insert_callout("TIP"), "Insert"))

        # View commands
        commands.append(Command("view.toggle_preview", "Toggle Preview", self.settings.get_shortcut("view.toggle_preview"), self._toggle_preview, "View"))
        commands.append(Command("view.toggle_outline", "Toggle Outline Panel", self.settings.get_shortcut("view.toggle_outline"), self._toggle_outline_panel, "View"))
        commands.append(Command("view.toggle_project", "Toggle Project Panel", self.settings.get_shortcut("view.toggle_project"), self._toggle_project_panel, "View"))
        commands.append(Command("view.toggle_references", "Toggle References Panel", self.settings.get_shortcut("view.toggle_references"), self._toggle_references_panel, "View"))
        commands.append(Command("view.toggle_search", "Toggle Search Panel", self.settings.get_shortcut("view.toggle_search"), self._toggle_search_panel, "View"))
        commands.append(Command("view.toggle_sidebar", "Toggle Sidebar", self.settings.get_shortcut("view.toggle_sidebar"), self._toggle_sidebar, "View"))
        commands.append(Command("view.fold_all", "Fold All", self.settings.get_shortcut("view.fold_all"), self._fold_all, "View"))
        commands.append(Command("view.unfold_all", "Unfold All", self.settings.get_shortcut("view.unfold_all"), self._unfold_all, "View"))
        commands.append(Command("view.zoom_in", "Zoom In", self.settings.get_shortcut("view.zoom_in"), self._zoom_in, "View"))
        commands.append(Command("view.zoom_out", "Zoom Out", self.settings.get_shortcut("view.zoom_out"), self._zoom_out, "View"))
        commands.append(Command("view.zoom_reset", "Reset Zoom", self.settings.get_shortcut("view.zoom_reset"), self._zoom_reset, "View"))

        # Settings
        commands.append(Command("settings", "Open Settings", "", self._show_settings, "Settings"))

        # Export commands
        commands.append(Command("export.html", "Export to HTML", "", self._export_html, "Export"))
        commands.append(Command("export.pdf", "Export to PDF", "", self._export_pdf, "Export"))
        commands.append(Command("export.docx", "Export to DOCX", "", self._export_docx, "Export"))

        # Tab commands
        commands.append(Command("tabs.close", "Close Current Tab", self.settings.get_shortcut("file.close_tab"), self._close_current_tab, "Tabs"))
        commands.append(Command("tabs.next", "Next Tab", self.settings.get_shortcut("tabs.next"), self._next_tab, "Tabs"))
        commands.append(Command("tabs.previous", "Previous Tab", self.settings.get_shortcut("tabs.previous"), self._prev_tab, "Tabs"))

        # Line operations
        commands.append(Command("edit.duplicate_line", "Duplicate Line", self.settings.get_shortcut("edit.duplicate_line"), self._duplicate_line, "Edit"))
        commands.append(Command("edit.delete_line", "Delete Line", self.settings.get_shortcut("edit.delete_line"), self._delete_line, "Edit"))
        commands.append(Command("edit.move_line_up", "Move Line Up", self.settings.get_shortcut("edit.move_line_up"), self._move_line_up, "Edit"))
        commands.append(Command("edit.move_line_down", "Move Line Down", self.settings.get_shortcut("edit.move_line_down"), self._move_line_down, "Edit"))
        commands.append(Command("edit.toggle_comment", "Toggle Comment", self.settings.get_shortcut("edit.toggle_comment"), self._toggle_comment, "Edit"))

        # Theme toggle
        commands.append(Command("view.toggle_theme", "Toggle Light/Dark Theme", "", self._toggle_theme, "View"))

        # Fullscreen
        commands.append(Command("view.fullscreen", "Toggle Fullscreen", self.settings.get_shortcut("view.fullscreen"), self._toggle_fullscreen, "View"))

        # More format commands
        commands.append(Command("format.heading_increase", "Increase Heading Level", self.settings.get_shortcut("markdown.heading_increase"), self._heading_increase, "Format"))
        commands.append(Command("format.heading_decrease", "Decrease Heading Level", self.settings.get_shortcut("markdown.heading_decrease"), self._heading_decrease, "Format"))

        self.command_palette.set_commands(commands)

    def _show_command_palette(self):
        """Show the command palette."""
        self.command_palette.exec()

    # ==================== OUTLINE PANEL ====================

    def _toggle_outline_panel(self):
        """Toggle the outline panel visibility and switch to Outline tab."""
        if not self.sidebar.isCollapsed() and self.sidebar.activeIndex() == 1:
            # Outline is showing, collapse sidebar
            self.sidebar.collapse()
        else:
            # Show sidebar and switch to Outline
            self.sidebar.setActivePanel(1)
            if self.sidebar.isCollapsed():
                self.sidebar.expand()
            self._update_outline()

    def _update_outline(self):
        """Update the outline panel (immediate, for tab switches etc.)."""
        self._do_update_outline()

    def _do_update_outline(self):
        """Actually update the outline panel with current document headings."""
        tab = self.current_tab()
        if tab:
            text = tab.editor.toPlainText()
            self.outline_panel.update_outline(text)

    def _go_to_heading(self, line: int):
        """Go to a heading in the current document."""
        tab = self.current_tab()
        if tab:
            tab.editor.go_to_line(line + 1)
            # Sync preview scroll after a short delay
            QTimer.singleShot(50, lambda: self._sync_preview_to_editor(tab))

    # ==================== REFERENCES PANEL ====================

    def _update_references(self):
        """Update the references panel with backlinks to current file."""
        tab = self.current_tab()
        if tab and tab.file_path:
            self.references_panel.set_current_file(tab.file_path)
        else:
            self.references_panel.set_current_file(None)

    def _go_to_reference(self, file_path: str, line: int):
        """Open a file and go to a specific line from the references panel."""
        # Open the file first
        self.open_file(file_path)

        # Defer line navigation to ensure file is fully loaded and tab is ready
        def navigate_and_update():
            tab = self.current_tab()
            if tab:
                if line >= 0:
                    tab.editor.go_to_line(line + 1)
                    # Sync preview after another short delay
                    QTimer.singleShot(50, lambda: self._sync_preview_to_editor(tab))
                # Update references for the newly opened file
                self._update_references()

        # Wait for file to load before navigating and updating references
        QTimer.singleShot(100, navigate_and_update)

    def _handle_editor_link_click(self, link: str):
        """Handle a Ctrl+click link from the editor pane."""
        # Convert string to QUrl
        if link.startswith(('http://', 'https://', 'mailto:', 'ftp://')):
            url = QUrl(link)
        else:
            # Treat as relative path
            tab = self.current_tab()
            if tab and tab.file_path:
                file_path = tab.file_path.parent / link
                url = QUrl.fromLocalFile(str(file_path))
            else:
                url = QUrl(link)
        self._handle_link_click(url)

    def _handle_link_click(self, url: QUrl):
        """Handle a link click from the preview pane."""
        try:
            self._do_handle_link_click(url)
        except Exception as e:
            self.status_bar.showMessage(f"Error handling link: {e}")
            import traceback
            traceback.print_exc()

    def _do_handle_link_click(self, url: QUrl):
        """Internal link click handler."""
        # Get current tab for resolving relative paths
        tab = self.current_tab()
        current_dir = tab.file_path.parent if tab and tab.file_path else Path.cwd()

        # Determine the file path from the URL
        file_path = None
        if url.isLocalFile():
            file_path = Path(url.toLocalFile())
        elif url.scheme() == "" or url.scheme() == "file":
            # Relative path - resolve relative to current document
            url_path = url.toString()
            # Remove any fragment (anchor)
            if "#" in url_path:
                url_path = url_path.split("#")[0]
            if url_path:
                file_path = current_dir / url_path

        # Check if it's a markdown file
        if file_path:
            # Resolve the path
            try:
                file_path = file_path.resolve()
            except (OSError, ValueError):
                pass

            if file_path.exists() and file_path.suffix.lower() in ('.md', '.markdown'):
                # Open markdown file in editor
                self.open_file(str(file_path))
                self.status_bar.showMessage(f"Opened: {file_path.name}")
                return

        # For all other links, open with default application
        if url.scheme() in ('http', 'https', 'mailto', 'ftp'):
            QDesktopServices.openUrl(url)
            self.status_bar.showMessage(f"Opened in browser: {url.toString()}")
        elif file_path and file_path.exists():
            # Open non-markdown file with default app
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))
            self.status_bar.showMessage(f"Opened with default app: {file_path.name}")
        else:
            # Try to open as-is
            QDesktopServices.openUrl(url)

    def _sync_preview_to_editor(self, tab: DocumentTab, retry_count: int = 0):
        """Sync the preview scroll position to match the editor's cursor line."""
        if not tab or not tab.preview.isVisible():
            return

        # Calculate ratio based on cursor line position, not scroll position
        # This is more accurate after go_to_line + centerCursor
        cursor = tab.editor.textCursor()
        current_line = cursor.blockNumber()
        total_lines = tab.editor.document().blockCount()

        if total_lines <= 1:
            ratio = 0.0
        else:
            ratio = current_line / (total_lines - 1)

        if tab._use_webengine:
            # Use JavaScript to scroll QWebEngineView
            # Wait for document to be ready before scrolling, with retry mechanism
            js = f"""
            (function() {{
                function doScroll() {{
                    var docHeight = document.body.scrollHeight;
                    var viewHeight = window.innerHeight;
                    // Only scroll if document has meaningful height (content loaded)
                    if (docHeight > viewHeight) {{
                        var targetY = docHeight * {ratio};
                        // Center the target position in the viewport
                        var scrollY = Math.max(0, targetY - viewHeight / 2);
                        window.scrollTo(0, scrollY);
                        return true;
                    }}
                    return false;
                }}
                // Try immediately
                if (!doScroll()) {{
                    // If doc not ready, try again after a short delay
                    setTimeout(doScroll, 100);
                }}
            }})();
            """
            tab.preview.page().runJavaScript(js)

            # For QWebEngineView, if this is the first attempt, retry after content loads
            if retry_count == 0:
                QTimer.singleShot(200, lambda: self._sync_preview_to_editor(tab, retry_count=1))
        else:
            preview_scrollbar = tab.preview.verticalScrollBar()
            # Calculate position to center the target line
            max_scroll = preview_scrollbar.maximum()
            page_step = preview_scrollbar.pageStep()
            target_pos = int(ratio * (max_scroll + page_step))
            # Adjust to center
            scroll_pos = max(0, target_pos - page_step // 2)
            preview_scrollbar.setValue(min(scroll_pos, max_scroll))

    def _toggle_references_panel(self):
        """Toggle the references panel visibility and switch to References tab."""
        if not self.sidebar.isCollapsed() and self.sidebar.activeIndex() == 2:
            # References is showing, collapse sidebar
            self.sidebar.collapse()
        else:
            # Show sidebar and switch to References
            self.sidebar.setActivePanel(2)
            if self.sidebar.isCollapsed():
                self.sidebar.expand()
            self._update_references()

    # ==================== PROJECT PANEL ====================

    def _toggle_project_panel(self):
        """Toggle the project panel visibility and switch to Project tab."""
        if not self.sidebar.isCollapsed() and self.sidebar.activeIndex() == 0:
            # Project is showing, collapse sidebar
            self.sidebar.collapse()
        else:
            # Show sidebar and switch to Project
            self.sidebar.setActivePanel(0)
            if self.sidebar.isCollapsed():
                self.sidebar.expand()

    def _toggle_search_panel(self):
        """Toggle the search panel visibility and switch to Search tab."""
        if not self.sidebar.isCollapsed() and self.sidebar.activeIndex() == 3:
            # Search is showing, collapse sidebar
            self.sidebar.collapse()
        else:
            # Show sidebar and switch to Search
            self.sidebar.setActivePanel(3)
            if self.sidebar.isCollapsed():
                self.sidebar.expand()
            self.search_panel.focus_search()

    def _open_project(self):
        """Open a project folder."""
        folder = QFileDialog.getExistingDirectory(
            self, "Open Project Folder", str(Path.home())
        )
        if folder:
            project_path = Path(folder)
            self.project_panel.set_project_path(project_path)
            self.references_panel.set_project_path(project_path)
            self.search_panel.set_project_path(project_path)
            self.sidebar.setActivePanel(0)  # Switch to Project tab
            if self.sidebar.isCollapsed():
                self.sidebar.expand()
            self._update_wiki_links()
            self._update_references()

    def _on_sidebar_collapsed_changed(self, collapsed: bool):
        """Handle sidebar collapse/expand."""
        # Guard: actions may not exist during init
        if not hasattr(self, 'toggle_project_action'):
            return

        if collapsed:
            self.toggle_project_action.setChecked(False)
            self.toggle_outline_action.setChecked(False)
            self.toggle_references_action.setChecked(False)
            self.toggle_search_action.setChecked(False)
        else:
            self._on_sidebar_panel_changed(self.sidebar.activeIndex())

    def _on_sidebar_width_changed(self, sidebar_width: int):
        """Handle sidebar width change (during animation)."""
        total_width = self.main_splitter.width()
        content_width = total_width - sidebar_width
        self.main_splitter.setSizes([sidebar_width, content_width])

    def _on_sidebar_panel_changed(self, index: int):
        """Handle sidebar panel change."""
        # Guard: actions may not exist during init
        if not hasattr(self, 'toggle_project_action'):
            return

        if not self.sidebar.isCollapsed():
            self.toggle_project_action.setChecked(index == 0)
            self.toggle_outline_action.setChecked(index == 1)
            self.toggle_references_action.setChecked(index == 2)
            self.toggle_search_action.setChecked(index == 3)
            if index == 1:
                self._update_outline()
            elif index == 2:
                self._update_references()

    def _toggle_sidebar(self):
        """Toggle sidebar visibility."""
        self.sidebar.toggle()

    def _on_search_file_requested(self, file_path: str, line_number: int):
        """Handle search result click - open file at line."""
        self.open_file(Path(file_path))
        tab = self.current_tab()
        if tab and line_number > 0:
            tab.editor.go_to_line(line_number + 1)

    def _apply_dock_theme(self):
        """Apply theme to the sidebar (no-op, sidebar handles its own theme)."""
        # Sidebar components handle their own theming via settings_changed signal
        pass

    def _apply_toggle_button_theme(self):
        """Apply theme to the editor/preview toggle buttons."""
        theme_name = self.settings.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        # Left button (editor toggle)
        self.editor_toggle_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {theme.border};
                border-right: none;
                border-top-left-radius: 3px;
                border-bottom-left-radius: 3px;
                padding: 4px 8px;
                background-color: {theme.bg_secondary};
            }}
            QToolButton:checked {{
                background-color: {theme.bg_tertiary};
            }}
            QToolButton:hover {{
                background-color: {theme.bg_input};
            }}
        """)

        # Right button (preview toggle)
        self.preview_toggle_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {theme.border};
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                padding: 4px 8px;
                background-color: {theme.bg_secondary};
            }}
            QToolButton:checked {{
                background-color: {theme.bg_tertiary};
            }}
            QToolButton:hover {{
                background-color: {theme.bg_input};
            }}
        """)

    def _apply_full_theme(self):
        """Apply complete theme to app and all widgets.

        Called at startup and when theme changes to ensure all UI
        elements are properly styled.
        """
        theme_name = self.settings.get("view.theme", "light")
        is_dark = theme_name == "dark"

        # Apply app-level theme (menus, tabs, etc.)
        apply_application_theme(is_dark)

        # Apply dock/panel theme
        self._apply_dock_theme()

        # Apply toggle button theme
        self._apply_toggle_button_theme()

        # Update all document tabs
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, '_apply_preview_style'):
                tab._apply_preview_style()

    # ==================== VIEW TOGGLE BUTTONS ====================

    def _create_view_toggle_buttons(self):
        """Create editor/preview toggle buttons in the tab bar corner."""
        # Container widget for the buttons
        corner_widget = QWidget()
        layout = QHBoxLayout(corner_widget)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(0)

        # Editor toggle button
        self.editor_toggle_btn = QToolButton()
        self.editor_toggle_btn.setCheckable(True)
        self.editor_toggle_btn.setChecked(self.settings.get("view.show_editor", True))
        self.editor_toggle_btn.setToolTip("Show/Hide Editor")
        self.editor_toggle_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.editor_toggle_btn.setAutoRaise(True)
        self.editor_toggle_btn.clicked.connect(self._on_editor_toggle)

        # Preview toggle button
        self.preview_toggle_btn = QToolButton()
        self.preview_toggle_btn.setCheckable(True)
        self.preview_toggle_btn.setChecked(self.settings.get("view.show_preview", True))
        self.preview_toggle_btn.setToolTip("Show/Hide Preview")
        self.preview_toggle_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.preview_toggle_btn.setAutoRaise(True)
        self.preview_toggle_btn.clicked.connect(self._on_preview_toggle)

        # Style the buttons (theme-aware styling applied in _apply_toggle_button_theme)
        self._apply_toggle_button_theme()

        layout.addWidget(self.editor_toggle_btn)
        layout.addWidget(self.preview_toggle_btn)

        # Add to tab widget corner
        self.tab_widget.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

    def _on_editor_toggle(self):
        """Handle editor toggle button click."""
        editor_visible = self.editor_toggle_btn.isChecked()
        preview_visible = self.preview_toggle_btn.isChecked()

        # Prevent hiding both - if trying to hide editor and preview is already hidden
        if not editor_visible and not preview_visible:
            # Re-check the editor button, can't hide both
            self.editor_toggle_btn.setChecked(True)
            return

        self._update_editor_preview_visibility()

    def _on_preview_toggle(self):
        """Handle preview toggle button click."""
        editor_visible = self.editor_toggle_btn.isChecked()
        preview_visible = self.preview_toggle_btn.isChecked()

        # Prevent hiding both - if trying to hide preview and editor is already hidden
        if not preview_visible and not editor_visible:
            # Re-check the preview button, can't hide both
            self.preview_toggle_btn.setChecked(True)
            return

        self._update_editor_preview_visibility()

    def _update_editor_preview_visibility(self):
        """Update editor and preview visibility for ALL tabs."""
        editor_visible = self.editor_toggle_btn.isChecked()
        preview_visible = self.preview_toggle_btn.isChecked()

        # Persist state for next startup
        self.settings.set("view.show_editor", editor_visible)
        self.settings.set("view.show_preview", preview_visible)

        # Apply to all tabs
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab:
                editor_container = tab.splitter.widget(0)
                preview_widget = tab.splitter.widget(1)

                if editor_container:
                    editor_container.setVisible(editor_visible)
                if preview_widget:
                    preview_widget.setVisible(preview_visible)

        # Re-center any active search match in newly-visible panes
        tab = self.tab_widget.currentWidget()
        if tab and tab.find_replace_bar.isVisible():
            # Short delay so the pane finishes layout before scrolling
            QTimer.singleShot(50, tab.find_replace_bar.sync_visible_panes)
            # Sync preview scroll to editor cursor line (handles reflow after resize)
            QTimer.singleShot(200, lambda: self._sync_preview_to_editor(tab))

        # Sync with menu action
        self.toggle_preview_action.setChecked(preview_visible)

    def _apply_visibility_to_tab(self, tab):
        """Apply the global editor/preview visibility state to a single tab."""
        editor_visible = self.editor_toggle_btn.isChecked()
        preview_visible = self.preview_toggle_btn.isChecked()

        editor_container = tab.splitter.widget(0)
        preview_widget = tab.splitter.widget(1)

        if editor_container:
            editor_container.setVisible(editor_visible)
        if preview_widget:
            preview_widget.setVisible(preview_visible)

    def _sync_view_toggle_buttons(self):
        """Sync toggle button states with current tab's visibility."""
        tab = self.current_tab()
        if not tab:
            return

        editor_container = tab.splitter.widget(0)
        preview_widget = tab.splitter.widget(1)

        # Block signals to prevent recursive updates
        self.editor_toggle_btn.blockSignals(True)
        self.preview_toggle_btn.blockSignals(True)

        # Use isVisibleTo(parent) which works before window is shown
        # or check if explicitly hidden via .isHidden()
        if editor_container:
            # If not explicitly hidden, consider it visible
            self.editor_toggle_btn.setChecked(not editor_container.isHidden())
        if preview_widget:
            self.preview_toggle_btn.setChecked(not preview_widget.isHidden())

        self.editor_toggle_btn.blockSignals(False)
        self.preview_toggle_btn.blockSignals(False)

    def _restore_last_project(self):
        """Restore the last opened project on startup."""
        last_path = self.settings.get("project.last_path")
        if last_path:
            path = Path(last_path)
            if path.exists() and path.is_dir():
                self.project_panel.set_project_path(path)
                self.references_panel.set_project_path(path)
                self.search_panel.set_project_path(path)
                self._update_wiki_links()
                # Don't auto-show the dock, just load the project data

    def restore_open_files(self):
        """Restore previously open files from the last session.

        Called externally (from cmd_gui) only when no explicit files were
        provided on the command line and the project matches last_path.
        """
        open_files = self.settings.get("project.open_files", [])
        if not open_files:
            return

        opened_any = False
        for file_str in open_files:
            path = Path(file_str)
            if path.exists():
                self.open_file(path)
                opened_any = True

        if opened_any:
            # Remove the initial empty tab if it's still untouched
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if (
                    tab.file_path is None
                    and not tab.unsaved_changes
                    and not tab.editor.toPlainText()
                ):
                    self.tab_widget.removeTab(i)
                    break

            # Restore active tab
            active = self.settings.get("project.active_tab", 0)
            if 0 <= active < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(active)

        # Restore sidebar state
        active_panel = self.settings.get("sidebar.active_panel", 0)
        if 0 <= active_panel < self.sidebar.stack.count():
            self.sidebar.setActivePanel(active_panel)
        if self.settings.get("sidebar.collapsed", False):
            self.sidebar.setCollapsed(True, animated=False)

    def _update_wiki_links(self):
        """Update available wiki links from project files."""
        if not self.project_panel.project_path:
            return

        links = []
        for md_file in self.project_panel.get_project_files():
            # Add filename without extension
            links.append(md_file.stem)

        # Update all tab editors
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'editor'):
                tab.editor.set_available_links(links)

    # ==================== FOLDING ====================

    def _fold_all(self):
        """Fold all sections in the current document."""
        tab = self.current_tab()
        if tab:
            tab.editor.fold_all()

    def _unfold_all(self):
        """Unfold all sections in the current document."""
        tab = self.current_tab()
        if tab:
            tab.editor.unfold_all()

    # ==================== EXPORT ====================

    def _export_pdf(self):
        """Export the current document to PDF."""
        tab = self.current_tab()
        if not tab:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to PDF",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not file_path:
            return

        title = tab.file_path.stem if tab.file_path else "Document"
        try:
            export_service.export_pdf(tab.editor.toPlainText(), file_path, title)
            self.status_bar.showMessage(f"Exported to: {file_path}")
        except export_service.ExportError as e:
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {e}")

    def _export_docx(self):
        """Export the current document to DOCX."""
        tab = self.current_tab()
        if not tab:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to DOCX",
            "",
            "Word Documents (*.docx);;All Files (*)",
        )
        if not file_path:
            return

        title = tab.file_path.stem if tab.file_path else "Document"
        try:
            export_service.export_docx(tab.editor.toPlainText(), file_path, title)
            self.status_bar.showMessage(f"Exported to: {file_path}")
        except export_service.ExportError as e:
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {e}")

    # ==================== INSERT FEATURES ====================

    def _insert_table(self):
        """Show the table editor dialog."""
        tab = self.current_tab()
        if not tab:
            return

        dialog = TableEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            markdown_table = dialog.get_markdown()
            if markdown_table:
                cursor = tab.editor.textCursor()
                cursor.insertText("\n" + markdown_table + "\n")

    def _show_snippet_popup(self):
        """Show the snippet selection popup."""
        tab = self.current_tab()
        if not tab:
            return

        manager = get_snippet_manager()
        snippets = manager.get_all_snippets()

        popup = SnippetPopup(snippets, self)
        if popup.exec() == QDialog.DialogCode.Accepted and popup.selected_snippet:
            content, placeholder_start, placeholder_end = manager.expand_snippet(popup.selected_snippet)
            cursor = tab.editor.textCursor()
            insert_pos = cursor.position()
            cursor.insertText(content)

            # Select first placeholder if present
            if placeholder_start >= 0:
                cursor.setPosition(insert_pos + placeholder_start)
                cursor.setPosition(insert_pos + placeholder_end, QTextCursor.MoveMode.KeepAnchor)
                tab.editor.setTextCursor(cursor)

    def _insert_math(self):
        """Insert a math block."""
        tab = self.current_tab()
        if tab:
            cursor = tab.editor.textCursor()
            cursor.insertText("\n$$\n\n$$\n")
            # Position cursor inside the block
            cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.MoveAnchor, 2)
            tab.editor.setTextCursor(cursor)

    def _insert_mermaid(self):
        """Insert a mermaid diagram block."""
        tab = self.current_tab()
        if tab:
            cursor = tab.editor.textCursor()
            cursor.insertText("\n```mermaid\ngraph TD\n    A[Start] --> B[End]\n```\n")

    def _insert_callout(self, callout_type: str):
        """Insert a callout block."""
        tab = self.current_tab()
        if tab:
            cursor = tab.editor.textCursor()
            cursor.insertText(f"\n> [!{callout_type}]\n> \n")


def main():
    """Run the Markdown editor application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    # Apply saved theme at startup
    from markdown_editor.markdown6.settings import get_settings
    settings = get_settings()
    apply_application_theme(settings.get("view.theme", "light") == "dark")

    editor = MarkdownEditor()
    editor.show()

    if sys.argv[1:]:
        for arg in sys.argv[1:]:
            editor.open_file(arg)
    else:
        editor.restore_open_files()

    # Grab focus and set cursor in editor
    editor.activateWindow()
    editor.raise_()
    tab = editor.current_tab()
    if tab:
        tab.editor.setFocus()

    ret = app.exec()
    del editor
    sys.exit(ret)


if __name__ == "__main__":
    main()

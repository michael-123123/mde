"""A feature-rich Qt6 Markdown editor with split-screen editing and preview."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QIcon, QKeySequence,
                           QPalette, QShortcut, QTextCursor)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QSplitter, QStyle, QTabWidget, QToolButton,
                               QWidget)

from markdown_editor.markdown6 import export_service
from markdown_editor.markdown6.actions import (_action_attr, _shortcut_id,
                                               apply_shortcuts,
                                               build_command_palette,
                                               build_menu_bar)
from markdown_editor.markdown6.plugins import api as plugin_api
from markdown_editor.markdown6.plugins.document_handle import DocumentHandle
from markdown_editor.markdown6.plugins.editor_integration import (
    apply_disabled_set, apply_panel_disabled_set, inject_plugin_actions,
    install_plugin_panels, plugin_palette_commands_filtered,
    register_existing_menu)
from markdown_editor.markdown6.plugins.loader import load_all
from markdown_editor.markdown6.plugins.plugin import PluginSource
from markdown_editor.markdown6.plugins.signals import SignalKind, dispatch as plugin_dispatch



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
        StyleSheets.tooltip(theme)
    )



from markdown_editor.markdown6 import graphviz_service
from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.components.command_palette import CommandPalette
from markdown_editor.markdown6.components.document_tab import DocumentTab
from markdown_editor.markdown6.components.graph_export import GraphExportDialog
from markdown_editor.markdown6.components.outline_panel import OutlinePanel
from markdown_editor.markdown6.components.references_panel import \
    ReferencesPanel
from markdown_editor.markdown6.components.search_panel import SearchPanel
from markdown_editor.markdown6.components.settings_dialog import SettingsDialog
from markdown_editor.markdown6.components.sidebar import Sidebar
from markdown_editor.markdown6.components.table_editor import TableEditorDialog
from markdown_editor.markdown6.html_renderer_core import (
    build_markdown, get_cached_html_formatter, wrap_html_in_full_template)
from markdown_editor.markdown6.extensions import (
    get_callout_css, get_math_js, get_mermaid_css, get_mermaid_js,
    get_tasklist_css)
from markdown_editor.markdown6.project_manager import ProjectPanel
from markdown_editor.markdown6.snippets import (SnippetPopup,
                                                get_snippet_manager)
from markdown_editor.markdown6.templates.preview import \
    PREVIEW_TEMPLATE_SIMPLE
from markdown_editor.markdown6.theme import (StyleSheets, get_theme,
                                             get_theme_from_ctx)


class MarkdownEditor(QMainWindow):
    """A tabbed Markdown editor with split-screen editing and preview."""

    def __init__(self, extra_plugin_dirs: list[Path] | None = None):
        super().__init__()
        self.ctx = get_app_context()
        # Extra plugin roots layered on top of builtin + user dirs. CLI
        # passes its --plugins-dir values here; settings-derived dirs
        # are read from `plugins.extra_dirs` inside `_plugin_roots()`.
        self._extra_plugin_dirs: list[Path] = list(extra_plugin_dirs or [])
        self._is_fullscreen = False
        self._diagram_executor = ThreadPoolExecutor(max_workers=4)
        self._set_application_icon()
        self._init_markdown()
        self._init_ui()
        self._init_actions()
        self._init_shortcuts()
        self._connect_signals()
        self._init_autosave()
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
        """Initialize the Markdown converter with the shared extension stack.

        Delegates to `html_renderer_core.build_markdown()` — the single
        source of truth for "preview-grade rendering". The live preview
        and export paths build Markdown instances via the same factory
        so their extension sets can never drift apart.

        Plugin-registered ``markdown.Extension`` instances (via
        ``plugins.api.register_markdown_extension``) are appended after
        the built-in stack — those from currently-disabled plugins are
        excluded. The plugin-fence dispatcher (``PluginFenceExtension``)
        is also added with the current disabled set captured.
        """
        from markdown_editor.markdown6.plugins.fence import PluginFenceExtension
        disabled = set(self.ctx.get("plugins.disabled", []) or [])
        extras = list(
            plugin_api._REGISTRY.active_markdown_extensions(disabled=disabled)
        )
        extras.append(PluginFenceExtension(disabled=disabled))
        self.md = build_markdown(extra_extensions=extras)

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
        self.sidebar = Sidebar(self.ctx)

        # Create panels
        self.project_panel = ProjectPanel(self.ctx)
        self.project_panel.file_double_clicked.connect(self.open_file)
        self.project_panel.graph_export_requested.connect(self._show_graph_export)
        self.project_panel.setAccessibleName("Project Files Panel")

        self.outline_panel = OutlinePanel(self.ctx)
        self.outline_panel.heading_clicked.connect(self._go_to_heading)
        self.outline_panel.setAccessibleName("Document Outline Panel")

        self.references_panel = ReferencesPanel(self.ctx)
        self.references_panel.reference_clicked.connect(self._go_to_reference)
        self.references_panel.setAccessibleName("References Panel")

        self.search_panel = SearchPanel(self.ctx)
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
        self.command_palette = CommandPalette(ctx=self.ctx, parent=self)

        self._create_menu_bar()
        self._create_status_bar()
        self._load_plugins()
        self._init_command_palette()
        self._init_debounce_timers()

    def _create_menu_bar(self):
        """Create the application menu bar from the declarative action registry."""
        self._action_defs = build_menu_bar(self)
        self._ensure_plugins_menu_slot()

    def _ensure_plugins_menu_slot(self):
        """Reserve the top-level "Plugins" menu just before "Help".

        Always present, even when no plugin is installed — gives users
        a stable place to find plugin commands and a stable target for
        plugin-supplied menu paths (which are namespaced under it).
        """
        from PySide6.QtWidgets import QMenu
        plugins_menu = QMenu("Plugins", self)
        help_menu = self._top_level_menus.get("&Help") or self._top_level_menus.get("Help")
        if help_menu is not None:
            self.menuBar().insertMenu(help_menu.menuAction(), plugins_menu)
        else:
            self.menuBar().addMenu(plugins_menu)
        self._top_level_menus["Plugins"] = plugins_menu
        register_existing_menu(self, "Plugins", plugins_menu)

    def _init_actions(self):
        """Apply shortcuts from the action registry."""
        apply_shortcuts(self, self._action_defs)

    def _create_status_bar(self):
        """Create the status bar."""
        from markdown_editor.markdown6.components.notification_bell import (
            NotificationBellButton, NotificationDrawer,
        )

        self.status_bar = self.statusBar()

        # Word count label
        self.word_count_label = QLabel("Words: 0 | Chars: 0")
        self.status_bar.addPermanentWidget(self.word_count_label)

        # Cursor position label
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        self.status_bar.addPermanentWidget(self.cursor_pos_label)

        # Notification bell + drawer (Phase 3). Bell lives in the
        # status bar's permanent-widget area; drawer is a popup
        # anchored under the bell on click.
        self.notification_bell = NotificationBellButton(self.ctx.notifications)
        self.notification_drawer = NotificationDrawer(self.ctx.notifications)
        self.notification_bell.clicked.connect(self._show_notification_drawer)
        self.status_bar.addPermanentWidget(self.notification_bell)

        self.status_bar.showMessage("Ready")

    def _show_notification_drawer(self):
        """Pop the drawer up so its bottom edge sits just above the
        status bar (the bell's top edge). Preserves the user's current
        drawer size across opens — no ``adjustSize()`` call, because
        that would fight the user's drag-resize via the size grip.
        Marks all notifications read.
        """
        bell = self.notification_bell
        drawer = self.notification_drawer
        global_top_right = bell.mapToGlobal(bell.rect().topRight())

        # Clamp the drawer's height so it can't extend above the top of
        # the app window — otherwise a user who resized it tall on a
        # small screen would see it spill off the top.
        win_top_y = self.mapToGlobal(self.rect().topLeft()).y()
        max_height = max(220, global_top_right.y() - win_top_y)
        if drawer.height() > max_height:
            drawer.resize(drawer.width(), max_height)

        drawer.move(
            global_top_right.x() - drawer.width(),
            global_top_right.y() - drawer.height(),
        )
        drawer.show_drawer()

    def _init_shortcuts(self):
        """Set up additional keyboard shortcuts."""
        # Tab navigation shortcuts (Alt+1-9)
        for i in range(1, 10):
            shortcut_key = self.ctx.get_shortcut(f"tabs.go_to_{i}")
            if shortcut_key:
                shortcut = QShortcut(QKeySequence(shortcut_key), self)
                shortcut.activated.connect(lambda idx=i - 1: self._go_to_tab(idx))

        # Find next/previous
        find_next_key = self.ctx.get_shortcut("find.next")
        if find_next_key:
            find_next_shortcut = QShortcut(QKeySequence(find_next_key), self)
            find_next_shortcut.activated.connect(self._find_next)

        find_prev_key = self.ctx.get_shortcut("find.previous")
        if find_prev_key:
            find_prev_shortcut = QShortcut(QKeySequence(find_prev_key), self)
            find_prev_shortcut.activated.connect(self._find_previous)

    def _connect_signals(self):
        """Connect settings signals."""
        self.ctx.shortcut_changed.connect(self._on_shortcut_changed)
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _on_shortcut_changed(self, action_id: str, shortcut: str):
        """Handle shortcut change."""
        for aid, adef in self._action_defs.items():
            if _shortcut_id(adef) == action_id:
                qaction = getattr(self, _action_attr(adef), None)
                if qaction:
                    qaction.setShortcut(QKeySequence(shortcut))
                break

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
        elif key == "editor.auto_save":
            self._configure_autosave()
        elif key == "editor.auto_save_interval":
            self._configure_autosave()
        elif key == "plugins.disabled":
            self._refresh_plugin_enabled_state()

    def _refresh_plugin_enabled_state(self):
        """React to a toggle in Settings → Plugins without a restart.

        Hides/shows already-loaded plugins' menu entries, rebuilds the
        command palette with the filtered set, and re-initializes the
        markdown converter so plugin-registered ``markdown.Extension``
        instances are added/removed from the preview pipeline.
        Re-enabling a plugin that wasn't loaded at startup (e.g. it
        was in the disabled set when the editor launched) still
        requires a restart — there's nothing in memory to bring back.
        """
        disabled = set(self.ctx.get("plugins.disabled", []) or [])
        apply_disabled_set(self, disabled)
        apply_panel_disabled_set(self.sidebar, disabled)
        static = build_command_palette(self, self._action_defs)
        static.extend(plugin_palette_commands_filtered(self, disabled))
        self.command_palette.set_commands(static)
        # Rebuild self.md so plugin extensions take effect for next render
        self._init_markdown()
        # Re-render the active tab so the change is visible immediately
        active = self.current_tab()
        if active is not None:
            active.render_markdown()

    def _init_autosave(self):
        """Initialize the autosave timer."""
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._auto_save_all)
        self._configure_autosave()

    def _configure_autosave(self):
        """Start or stop the autosave timer based on settings."""
        if self.ctx.get("editor.auto_save", False):
            interval_s = self.ctx.get("editor.auto_save_interval", 60)
            self._autosave_timer.start(interval_s * 1000)
        else:
            self._autosave_timer.stop()

    def _auto_save_all(self):
        """Save all tabs that have a file path and unsaved changes."""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and tab.file_path and tab.unsaved_changes:
                try:
                    tab.editor._ignore_next_file_change = True
                    tab.file_path.write_text(
                        tab.editor.toPlainText(), encoding="utf-8"
                    )
                    # modificationChanged(False) → DocumentTab updates
                    # ``unsaved_changes`` and tab title automatically.
                    tab.editor.document().setModified(False)
                    self.update_tab_title(tab)
                except OSError:
                    logger.exception(f"Autosave failed for {tab.file_path}")
        self.update_window_title()

    def _update_recent_files_menu(self):
        """Update the recent files menu."""
        self.recent_menu.clear()

        recent_files = self.ctx.get_recent_files()

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
        self.ctx.clear_recent_files()
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

    def get_html_template(self, content: str, for_qtextbrowser: bool = False, total_lines: int = 0) -> str:
        """Wrap rendered markdown in HTML with styling.

        Args:
            content: The HTML content to wrap.
            for_qtextbrowser: If True, generate simpler HTML for QTextBrowser.

        FULL case delegates to `html_renderer_core.wrap_html_in_full_template`
        — the single source of truth for the full preview/export template.
        SIMPLE case (QTextBrowser preview fallback) stays local because the
        simple template is preview-only and never shared with exports.
        """
        if not for_qtextbrowser:
            return wrap_html_in_full_template(content, self.ctx, total_lines)

        theme = self.ctx.get("view.theme", "light")
        dark_mode = theme == "dark"
        scroll_past_end = self.ctx.get("editor.scroll_past_end", True)

        colors = get_theme(dark_mode)
        bg_color = colors.editor_bg
        text_color = colors.editor_text
        heading_border = colors.preview_heading_border
        code_bg = colors.code_bg
        blockquote_color = colors.preview_blockquote
        link_color = colors.link
        pygments_style = "monokai" if dark_mode else "github-dark"
        body_class = "dark" if dark_mode else "light"

        font_size = self.ctx.get("view.preview_font_size", 14)

        _DEFAULT_BODY_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
        _DEFAULT_CODE_FONT = '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace'

        body_font_setting = self.ctx.get("preview.body_font_family", "")
        body_font = f'"{body_font_setting}", sans-serif' if body_font_setting else _DEFAULT_BODY_FONT

        code_font_setting = self.ctx.get("preview.code_font_family", "")
        code_font = f'"{code_font_setting}", monospace' if code_font_setting else _DEFAULT_CODE_FONT

        heading_font_setting = self.ctx.get("preview.heading_font_family", "")
        heading_font = f'"{heading_font_setting}", sans-serif' if heading_font_setting else ""
        line_height = self.ctx.get("preview.line_height", 1.5)

        def _sz(key_prefix):
            """Build a CSS font-size value from a size + unit setting pair."""
            val = self.ctx.get(f"preview.{key_prefix}_size", 1.0)
            unit = self.ctx.get(f"preview.{key_prefix}_size_unit", "em")
            return f"{val}{unit}"

        h1_size = _sz("h1")
        h2_size = _sz("h2")
        h3_size = _sz("h3")
        h4_size = _sz("h4")
        h5_size = _sz("h5")
        h6_size = _sz("h6")
        code_size = _sz("code")
        heading_font_css = f'font-family: {heading_font};' if heading_font else ""

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

        scroll_past_end_div = "<div style='height: 80vh;'></div>" if scroll_past_end else ""

        template_vars = dict(
            body_font=body_font, code_font=code_font, font_size=font_size,
            line_height=line_height, text_color=text_color, bg_color=bg_color,
            heading_border=heading_border, code_bg=code_bg,
            blockquote_color=blockquote_color, link_color=link_color,
            heading_font_css=heading_font_css,
            h1_size=h1_size, h2_size=h2_size, h3_size=h3_size,
            h4_size=h4_size, h5_size=h5_size, h6_size=h6_size,
            code_size=code_size, body_class=body_class,
            pygments_css=pygments_css, callout_css=callout_css,
            graphviz_css=graphviz_css, mermaid_css=mermaid_css,
            tasklist_css=tasklist_css,
            math_js=math_js, mermaid_js=mermaid_js, graphviz_js=graphviz_js,
            content=content, total_lines=total_lines,
            scroll_past_end_div=scroll_past_end_div,
        )

        # QTextBrowser fallback — limited CSS support, use the simple
        # template. The FULL path was handled by the early return at
        # the top of this method.
        return PREVIEW_TEMPLATE_SIMPLE.format(**template_vars)

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
            if tab.preview_has_focus():
                tab.preview_copy()
            else:
                tab.editor.copy()

    def _paste(self):
        tab = self.current_tab()
        if tab:
            tab.editor.paste()

    def _select_all(self):
        tab = self.current_tab()
        if tab:
            if tab.preview_has_focus():
                tab.preview_select_all()
            else:
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
        dialog = SettingsDialog(ctx=self.ctx, parent=self)
        # The Plugins page runs its own discover-only reload via the
        # ``plugin_roots_provider`` injected in SettingsDialog so the
        # user gets inline feedback (the bell in the status bar is
        # invisible while the dialog is modal). The command palette
        # entry ("Reload Plugins") still goes through
        # :meth:`_reload_plugins` for non-dialog reloads.
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
        self.ctx.set("editor.show_line_numbers", value)

    def _toggle_word_wrap(self):
        value = self.toggle_word_wrap_action.isChecked()
        self.ctx.set("editor.word_wrap", value)

    def _toggle_whitespace(self):
        value = self.toggle_whitespace_action.isChecked()
        self.ctx.set("editor.show_whitespace", value)

    def _toggle_logseq_mode(self):
        value = self.toggle_logseq_action.isChecked()
        self.ctx.set("view.logseq_mode", value)

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
        current = self.ctx.get("view.theme", "light")
        new_theme = "dark" if current == "light" else "light"
        # Setting the theme triggers _on_setting_changed which calls _apply_full_theme
        self.ctx.set("view.theme", new_theme)

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
        # Fan out content-change events to plugin signal handlers (if any).
        tab.editor.textChanged.connect(
            lambda _t=tab: self._dispatch_plugin_signal(SignalKind.CONTENT_CHANGED, _t)
        )

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
            # Reset the modification baseline to the just-loaded content.
            tab.editor.document().setModified(False)
            self.update_tab_title(tab)
            self.update_window_title()
            tab.render_markdown()

            # Add to recent files
            self.ctx.add_recent_file(path)
            self._update_recent_files_menu()

            self.status_bar.showMessage(f"Opened: {path}")
            self._dispatch_plugin_signal(SignalKind.FILE_OPENED, tab)
        except Exception as e:
            logger.exception(f"Could not open file: {path}")
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
            # modificationChanged(False) → DocumentTab clears unsaved_changes.
            tab.editor.document().setModified(False)
            self.update_tab_title(tab)
            self.update_window_title()
            self.status_bar.showMessage(f"Saved: {tab.file_path}")
            self._dispatch_plugin_signal(SignalKind.SAVE, tab)
            return True
        except Exception as e:
            logger.exception(f"Could not save file: {tab.file_path}")
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
        """Export the current document to HTML via the shared export_service.

        Routes through `export_service.export_html` (a thin adapter over
        `html_renderer_core`) so single-file export, project export, and
        CLI export all produce identical preview-grade HTML. Export-side
        overrides (scroll-past-end=False) are applied inside the service
        via an ephemeral ctx copy; the live ctx is not mutated.
        """
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
            content = tab.editor.toPlainText()
            title = tab.file_path.stem if tab.file_path else "Document"
            export_service.export_html(
                content, file_path, title=title, ctx=self.ctx,
                source_path=tab.file_path,
            )
            self.status_bar.showMessage(f"Exported to: {file_path}")
        except Exception as e:
            logger.exception(f"Could not export HTML to {file_path}")
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

        # Notify plugins BEFORE the tab is removed so handlers can still
        # introspect the document (e.g. log final word count).
        self._dispatch_plugin_signal(SignalKind.FILE_CLOSED, tab)

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
        self._diagram_executor.shutdown(wait=False, cancel_futures=True)
        event.accept()

    def _save_open_files(self):
        """Save the list of open file paths and active tab for session restore."""
        open_files = []
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab.file_path and tab.file_path.exists():
                open_files.append(str(tab.file_path.resolve()))
        self.ctx.set("project.open_files", open_files)
        self.ctx.set("project.active_tab", self.tab_widget.currentIndex())
        self.ctx.set("sidebar.collapsed", self.sidebar.isCollapsed())
        self.ctx.set("sidebar.active_panel", self.sidebar.activeIndex())
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

        dialog = GraphExportDialog(project_root, current_file, ctx=self.ctx, parent=self)

        # Connect file click signal to open the file
        def open_file_from_graph(file_path: Path):
            self.open_file(str(file_path))

        dialog.file_clicked.connect(open_file_from_graph)

        dialog.exec()

    # ==================== COMMAND PALETTE ====================

    def _init_debounce_timers(self):
        """Initialize debounce timers for expensive operations."""
        # Outline panel update timer (debounce 500ms)
        self._outline_update_timer = QTimer(self)
        self._outline_update_timer.setSingleShot(True)
        self._outline_update_timer.timeout.connect(self._do_update_outline)

    def _schedule_outline_update(self):
        """Schedule a debounced outline update."""
        if self.outline_panel.isVisible():
            self._outline_update_timer.start(500)

    def _init_command_palette(self):
        """Initialize the command palette from the action registry."""
        commands = build_command_palette(self, self._action_defs)
        disabled = set(self.ctx.get("plugins.disabled", []) or [])
        commands.extend(plugin_palette_commands_filtered(self, disabled))
        self.command_palette.set_commands(commands)

    def _load_plugins(self):
        """Discover and import builtin + user plugins, wire their actions in.

        Runs after the static menu bar is built (so plugin menu paths
        like "Edit/Transform" can find the real Edit menu) and before
        :meth:`_init_command_palette` (so plugin-registered palette
        commands are included in the initial command list).

        The loader never raises — plugins that fail to load are simply
        recorded with an error status in ``self._plugins`` and shown
        in Settings → Plugins.
        """
        # Expose the static top-level menus to the plugin integration
        # cache so plugins can attach under "Edit", "File", etc.
        for name, menu in getattr(self, "_top_level_menus", {}).items():
            register_existing_menu(self, name, menu)

        # Fresh registry for this editor's lifetime — clear any leftover
        # state from a previous init (important for tests that recreate
        # the editor inside the same process).
        plugin_api._REGISTRY.clear()
        plugin_api._set_active_document_provider(
            self._get_active_document_handle
        )
        plugin_api._set_all_documents_provider(self._get_all_document_handles)
        plugin_api._set_main_window_provider(lambda: self)

        disabled = set(self.ctx.get("plugins.disabled", []) or [])
        self._plugins = load_all(self._plugin_roots(), user_disabled=disabled)

        self._plugin_palette_commands = []
        inject_plugin_actions(
            self, plugin_api.get_registry(), self._plugin_palette_commands
        )

        # Materialize plugin sidebar panels (`register_panel`). Disabled
        # plugins' panels are still installed (so live re-enable can
        # reveal them) but their activity-bar tab is hidden.
        install_plugin_panels(
            self.sidebar, plugin_api.get_registry(), disabled=disabled,
        )

        # Apply the initial disabled-set to hide already-loaded plugins
        # that the user had toggled off in a previous session. This is
        # what lets re-enabling them later flip visibility instantly —
        # their QActions were created up-front, just hidden.
        apply_disabled_set(self, disabled)

        # Rebuild the markdown converter so any plugin-registered
        # ``markdown.Extension`` instances actually reach the preview
        # pipeline. (`_init_markdown` ran in __init__ before plugins
        # were loaded, so its first build had no plugin extensions.)
        self._init_markdown()

        # Publish to AppContext so the Plugins settings tab can read the list.
        self.ctx.set_plugins(self._plugins)

    def _get_active_document_handle(self):
        """Callback used by plugin_api.get_active_document()."""
        tab = self.current_tab()
        return DocumentHandle(tab) if tab is not None else None

    def _reload_plugins(self):
        """Re-discover plugins on disk and post a notification with the diff.

        Wired to the "Reload Plugins" command palette entry and to the
        Reload button on the Plugins settings page. Discovery-only —
        does NOT hot-reload existing plugins; the notification tells
        the user to restart for changes to take effect. See
        ``plugins/reload.py`` for the rationale.
        """
        from markdown_editor.markdown6.plugins.reload import reload_plugins
        reload_plugins(self.ctx, self._plugin_roots())

    def _plugin_roots(self):
        """Return the (path, source) pairs the loader uses at startup.

        Built from three sources, in scan order:
        1. ``markdown6/builtin_plugins/`` — anything shipped with the
           editor (currently empty by default).
        2. ``<config_dir>/plugins/`` — the user's installed plugins.
        3. Extra dirs — constructor arg (CLI ``--plugins-dir``) +
           ``plugins.extra_dirs`` setting. Both are additive; neither
           replaces the defaults. Extra dirs are tagged
           :data:`PluginSource.USER`.
        """
        import markdown_editor.markdown6 as pkg
        builtin_root = Path(pkg.__file__).resolve().parent / "builtin_plugins"
        user_root = self.ctx.config_dir / "plugins"
        roots: list[tuple[Path, PluginSource]] = [
            (builtin_root, PluginSource.BUILTIN),
            (user_root, PluginSource.USER),
        ]
        for extra in self._extra_plugin_dirs:
            roots.append((Path(extra), PluginSource.USER))
        for raw in self.ctx.get("plugins.extra_dirs", []) or []:
            roots.append((Path(raw), PluginSource.USER))
        return roots

    def _get_all_document_handles(self):
        """Callback used by plugin_api.get_all_documents()."""
        out = []
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab is not None:
                out.append(DocumentHandle(tab))
        return out

    def _dispatch_plugin_signal(self, kind: SignalKind, tab) -> None:
        """Wrap a tab as a DocumentHandle and fan out to plugin handlers."""
        if tab is None:
            return
        disabled = set(self.ctx.get("plugins.disabled", []) or [])
        plugin_dispatch(kind, DocumentHandle(tab), disabled=disabled)

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
            logger.exception(f"Error handling link: {url.toString()}")
            self.status_bar.showMessage(f"Error handling link: {e}")

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

        cursor = tab.editor.textCursor()
        current_line = cursor.blockNumber()

        if tab._use_webengine:
            js = f"""
            (function() {{
                function doScroll() {{
                    if (typeof scrollToSourceLine === 'function' &&
                        document.querySelectorAll('[data-source-line]').length > 0) {{
                        scrollToSourceLine({current_line});
                        return true;
                    }}
                    return false;
                }}
                if (!doScroll()) {{
                    setTimeout(doScroll, 100);
                }}
            }})();
            """
            tab.preview.page().runJavaScript(js)

            if retry_count == 0:
                QTimer.singleShot(200, lambda: self._sync_preview_to_editor(tab, retry_count=1))
        else:
            total_lines = tab.editor.document().blockCount()
            ratio = current_line / (total_lines - 1) if total_lines > 1 else 0.0
            preview_scrollbar = tab.preview.verticalScrollBar()
            max_scroll = preview_scrollbar.maximum()
            page_step = preview_scrollbar.pageStep()
            target_pos = int(ratio * (max_scroll + page_step))
            scroll_pos = max(0, target_pos - page_step // 2)
            preview_scrollbar.setValue(min(scroll_pos, max_scroll))

    def _restore_preview_scroll_after_resize(self, tab: DocumentTab):
        """Restore preview scroll position after a pane visibility toggle.

        Reads the scroll ratio saved in JS global window._preResizeScrollRatio
        (set before the resize) and scrolls to the same relative position.
        """
        if not tab._use_webengine:
            return
        tab.preview.page().runJavaScript(
            "if (typeof window._preResizeScrollRatio === 'number') {"
            "  var maxScroll = document.body.scrollHeight - window.innerHeight;"
            "  if (maxScroll > 0) {"
            "    window.scrollTo(0, window._preResizeScrollRatio * maxScroll);"
            "  }"
            "  delete window._preResizeScrollRatio;"
            "}"
        )

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
        theme = get_theme_from_ctx(self.ctx)
        self.editor_toggle_btn.setStyleSheet(StyleSheets.toggle_button_left(theme))
        self.preview_toggle_btn.setStyleSheet(StyleSheets.toggle_button_right(theme))

    def _apply_full_theme(self):
        """Apply complete theme to app and all widgets.

        Called at startup and when theme changes to ensure all UI
        elements are properly styled.
        """
        theme_name = self.ctx.get("view.theme", "light")
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
        self.editor_toggle_btn.setChecked(self.ctx.get("view.show_editor", True))
        self.editor_toggle_btn.setToolTip("Show/Hide Editor")
        self.editor_toggle_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.editor_toggle_btn.setAutoRaise(True)
        self.editor_toggle_btn.clicked.connect(self._on_editor_toggle)

        # Preview toggle button
        self.preview_toggle_btn = QToolButton()
        self.preview_toggle_btn.setCheckable(True)
        self.preview_toggle_btn.setChecked(self.ctx.get("view.show_preview", True))
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
        self.ctx.set("view.show_editor", editor_visible)
        self.ctx.set("view.show_preview", preview_visible)

        # Save preview scroll ratio in JS before resizing (reflow changes positions).
        # This JS executes in the renderer before the resize event arrives.
        current_tab = self.tab_widget.currentWidget()
        if current_tab and current_tab._use_webengine:
            current_tab.preview.page().runJavaScript(
                "window._preResizeScrollRatio ="
                " document.body.scrollHeight > window.innerHeight"
                " ? window.scrollY / (document.body.scrollHeight - window.innerHeight)"
                " : 0;"
            )

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

        # Restore preview scroll position after reflow
        if current_tab and current_tab._use_webengine:
            QTimer.singleShot(150, lambda: self._restore_preview_scroll_after_resize(current_tab))

        # Apply any scroll position deferred while the preview was hidden
        if preview_visible and current_tab and current_tab._pending_scroll_line is not None:
            line = current_tab._pending_scroll_line
            current_tab._pending_scroll_line = None
            if current_tab._use_webengine:
                QTimer.singleShot(
                    200,
                    lambda: current_tab.preview.page().runJavaScript(
                        f"if (typeof scrollToSourceLine === 'function') scrollToSourceLine({line});"
                    ),
                )

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
        last_path = self.ctx.get("project.last_path")
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
        open_files = self.ctx.get("project.open_files", [])
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
            active = self.ctx.get("project.active_tab", 0)
            if 0 <= active < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(active)

        # Restore sidebar state
        active_panel = self.ctx.get("sidebar.active_panel", 0)
        if 0 <= active_panel < self.sidebar.stack.count():
            self.sidebar.setActivePanel(active_panel)
        if self.ctx.get("sidebar.collapsed", False):
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
            logger.warning(f"PDF export error: {e}")
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            logger.exception(f"PDF export failed: {file_path}")
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
            logger.warning(f"DOCX export error: {e}")
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            logger.exception(f"DOCX export failed: {file_path}")
            QMessageBox.critical(self, "Error", f"Export failed: {e}")

    # ==================== INSERT FEATURES ====================

    def _insert_table(self):
        """Show the table editor dialog."""
        tab = self.current_tab()
        if not tab:
            return

        dialog = TableEditorDialog(ctx=self.ctx, parent=self)
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

        popup = SnippetPopup(snippets, ctx=self.ctx, parent=self)
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
    import logging

    from markdown_editor.markdown6.logger import setup as setup_logging
    setup_logging(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")

    # Apply saved theme at startup
    from markdown_editor.markdown6.app_context import get_app_context
    ctx = get_app_context()
    apply_application_theme(ctx.get("view.theme", "light") == "dark")

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

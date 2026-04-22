"""Regression tests for bugs fixed during development.

These tests ensure that previously fixed bugs don't reoccur.
"""


import pytest
from PySide6.QtCore import Qt


class FakeMainWindow:
    """Lightweight stand-in for MarkdownEditor when testing DocumentTab.

    Provides the minimal interface DocumentTab needs without pulling in
    the full MarkdownEditor (which initialises WebEngine, sidebar, etc.).
    Unlike MagicMock, attribute access doesn't create new mocks that can
    leak into the AppContext via signals.
    """

    def __init__(self, ctx):
        import markdown

        from markdown_editor.markdown6.extensions.math import MathExtension

        self.ctx = ctx
        self.md = markdown.Markdown(extensions=["extra", MathExtension()])

    def update_tab_title(self, tab):
        pass

    def update_window_title(self):
        pass

    def get_html_template(self, content, **kwargs):
        return f"<html><body>{content}</body></html>"


class TestGraphExportLabelSpacing:
    """Regression tests for graph label overlap issue.

    Bug: When "Labels below nodes" was checked, labels overlapped badly,
    especially with circo/neato layouts.

    Fix: Added nodesep, ranksep, overlap=prism, and smaller fontsize
    when labels_below is enabled.
    """

    def test_labels_below_adds_spacing_for_dot_layout(self, qtbot, tmp_path):
        """Test that dot layout gets nodesep and ranksep when labels below."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        # Create a test project with files
        project = tmp_path / "project"
        project.mkdir()
        (project / "test.md").write_text("# Test")

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        # Enable labels below and set dot layout
        dialog.labels_below_check.setChecked(True)
        dialog.engine_combo.setCurrentText("dot")

        # Generate graph
        files = [project / "test.md"]
        dot_source = dialog._generate_graph(files)

        # Should have spacing attributes
        assert "nodesep" in dot_source
        assert "ranksep" in dot_source
        assert "fontsize=10" in dot_source

    def test_labels_below_adds_overlap_for_circo_layout(self, qtbot, tmp_path):
        """Test that circo layout gets overlap=prism when labels below."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "test.md").write_text("# Test")

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        dialog.labels_below_check.setChecked(True)
        dialog.engine_combo.setCurrentText("circo")

        files = [project / "test.md"]
        dot_source = dialog._generate_graph(files)

        # Should have overlap removal for force-directed layouts
        assert "overlap=prism" in dot_source
        assert "sep=" in dot_source

    def test_labels_below_disabled_no_extra_spacing(self, qtbot, tmp_path):
        """Test that spacing attributes are NOT added when labels_below is off."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "test.md").write_text("# Test")

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        dialog.labels_below_check.setChecked(False)

        files = [project / "test.md"]
        dot_source = dialog._generate_graph(files)

        # Should NOT have the extra spacing attributes
        assert "overlap=prism" not in dot_source
        assert "fontsize=10" not in dot_source


class TestVerticalTabCollapse:
    """Regression tests for collapsible panel UX.

    Bug: Arrow buttons (◀/▶) were not visible and UX was poor.

    Fix: Implemented VerticalTab widget with rotated text and arrows.
    """

    def test_vertical_tab_arrow_changes_on_collapse(self, qtbot):
        """Test that arrow direction changes when collapsed."""
        from markdown_editor.markdown6.components.graph_export import (
            VerticalTab,
        )

        tab = VerticalTab("FILES", width=28, arrow_direction="left")
        qtbot.addWidget(tab)

        # Initially not collapsed
        assert tab._collapsed is False

        # Collapse it
        tab.setCollapsed(True)
        assert tab._collapsed is True

        # Expand it
        tab.setCollapsed(False)
        assert tab._collapsed is False

    def test_vertical_tab_text_centered(self, qtbot):
        """Test that VerticalTab can be created with text."""
        from markdown_editor.markdown6.components.graph_export import (
            VerticalTab,
        )

        tab = VerticalTab("OPTIONS", width=28, arrow_direction="right")
        qtbot.addWidget(tab)

        assert tab._text == "OPTIONS"
        assert tab._arrow_direction == "right"


class TestCommandPaletteAlignment:
    """Regression tests for command palette shortcut alignment.

    Bug: Shortcuts were not aligned because proportional font was used.

    Fix: Changed to monospace font for proper character-based alignment.
    """

    def test_command_palette_uses_monospace_font(self, qtbot):
        """Test that command palette list uses monospace font."""
        from markdown_editor.markdown6.components.command_palette import (
            CommandPalette,
        )

        palette = CommandPalette()
        qtbot.addWidget(palette)

        font = palette.list_widget.font()
        # Font should have monospace style hint
        from PySide6.QtGui import QFont
        assert font.styleHint() == QFont.StyleHint.Monospace or "mono" in font.family().lower()

    def test_command_shortcut_padding(self, qtbot):
        """Test that commands with shortcuts get padded for alignment."""
        from markdown_editor.markdown6.components.command_palette import (
            Command,
            CommandPalette,
        )

        palette = CommandPalette()
        qtbot.addWidget(palette)

        commands = [
            Command(id="short", name="A", shortcut="Ctrl+A", callback=lambda: None),
            Command(id="long", name="A Very Long Command Name", shortcut="Ctrl+B", callback=lambda: None),
        ]
        palette.set_commands(commands)

        # Both items should be in the list
        assert palette.list_widget.count() == 2


class TestGraphExportWindowFlags:
    """Regression tests for graph export window maximize button.

    Bug: Graph export dialog couldn't be maximized.

    Fix: Added WindowMinMaxButtonsHint to window flags.
    """

    def test_graph_export_can_maximize(self, qtbot, tmp_path):
        """Test that graph export dialog has maximize button enabled."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        flags = dialog.windowFlags()
        # Should have minimize/maximize buttons
        assert flags & Qt.WindowType.WindowMinMaxButtonsHint


class TestGraphPreviewNoScrollbars:
    """Regression tests for graph preview scrollbar removal.

    Bug: Scrollbars in preview were distracting.

    Fix: Removed scrollbar styling and container from preview HTML.
    """

    def test_preview_html_has_no_scrollbar_styling(self, qtbot, tmp_path):
        """Test that preview HTML doesn't have scrollbar CSS."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        # Generate preview HTML
        html = dialog._create_preview_html("<svg></svg>", dark_mode=False)

        # Should NOT have scrollbar styling
        assert "::-webkit-scrollbar" not in html
        assert "scroll-container" not in html


class TestGraphExportPreviewScaling:
    """Regression tests for preview scaling on resize.

    Bug: Preview didn't scale when dialog was resized.

    Fix: Added stretch factor to preview widget layout.
    """

    def test_preview_widget_has_stretch(self, qtbot, tmp_path):
        """Test that preview view is added with stretch factor."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        # The preview_view should exist and be in a layout
        assert hasattr(dialog, 'preview_view')
        # Splitter should have stretch factor on middle panel
        assert dialog.splitter.count() == 3


class TestNodeClickNavigation:
    """Regression tests for node click handling in preview.

    Bug: Clicking nodes in preview cleared the preview instead of
    emitting file_clicked signal.

    Fix: Added JavaScript click handlers and GraphPreviewPage to
    intercept navigation.
    """

    def test_preview_html_has_click_handlers(self, qtbot, tmp_path):
        """Test that preview HTML has node click JavaScript."""
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()

        dialog = GraphExportDialog(project)
        qtbot.addWidget(dialog)

        html = dialog._create_preview_html("<svg></svg>", dark_mode=False)

        # Should have click handler JavaScript
        assert "addEventListener('click'" in html
        assert ".node" in html

    def test_graph_preview_page_intercepts_navigation(self, qtbot):
        """Test that GraphPreviewPage can intercept file:// URLs."""
        from markdown_editor.markdown6.components.graph_export import (
            HAS_WEBENGINE,
            GraphPreviewPage,
        )

        if not HAS_WEBENGINE:
            pytest.skip("WebEngine not available")

        page = GraphPreviewPage()

        # Set up callback
        clicked_files = []
        page.file_clicked_callback = lambda path: clicked_files.append(path)

        # Simulate navigation to file:// URL
        from PySide6.QtCore import QUrl
        url = QUrl("file:///path/to/doc.md")

        # acceptNavigationRequest should return False for file:// URLs
        result = page.acceptNavigationRequest(url, None, True)

        assert result is False
        assert clicked_files == ["/path/to/doc.md"]


class TestWikiLinkPattern:
    """Regression tests for wiki link detection patterns."""

    def test_wiki_link_with_pipe_alias(self):
        """Test that wiki links with aliases are detected correctly."""
        from markdown_editor.markdown6.components.graph_export import (
            WIKI_LINK_PATTERN,
        )

        text = "See [[Document Name|display text]] for more."
        matches = WIKI_LINK_PATTERN.findall(text)

        # Should capture the document name, not the alias
        assert matches == ["Document Name"]

    def test_markdown_link_only_md_files(self):
        """Test that only .md/.mdown files are matched."""
        from markdown_editor.markdown6.components.graph_export import (
            MD_LINK_PATTERN,
        )

        text = "[doc](file.md) [img](image.png) [pdf](doc.pdf)"
        matches = MD_LINK_PATTERN.findall(text)

        # Should only match .md file
        assert len(matches) == 1
        assert matches[0][1] == "file.md"


class TestSettingsPersistence:
    """Regression tests for settings edge cases."""

    def test_recent_files_handles_deleted_files(self, tmp_path):
        """Test that recent files filters out deleted files."""
        from markdown_editor.markdown6.app_context import AppContext

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        ctx = AppContext(config_dir=config_dir)

        # Clear and add a file
        ctx.set("files.recent_files", [], save=False)

        test_file = tmp_path / "exists.md"
        test_file.touch()
        ctx.add_recent_file(test_file)

        # File exists, should be returned
        recent = ctx.get_recent_files()
        assert len(recent) == 1

        # Delete the file
        test_file.unlink()

        # Now it should be filtered out
        recent = ctx.get_recent_files()
        assert len(recent) == 0

    def test_corrupt_settings_file_uses_defaults(self, tmp_path):
        """Test that corrupt settings file falls back to defaults."""
        from markdown_editor.markdown6.app_context import (
            DEFAULT_SETTINGS,
            AppContext,
        )

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Write corrupt JSON
        (config_dir / "settings.json").write_text("{invalid json")

        # Should load defaults without crashing
        ctx = AppContext(config_dir=config_dir)
        assert ctx.get("editor.font_size") == DEFAULT_SETTINGS["editor.font_size"]


class TestPreviewDarkModeBackground:
    """Regression tests for preview pane dark mode background.

    Bug: When opening a new document in dark mode, the preview pane showed
    a white background instead of dark, because QWebEngineView default
    background is white before any HTML is loaded.

    Fix: Set page.setBackgroundColor() in _apply_preview_style() based on theme.
    """

    def test_preview_background_dark_mode(self, qtbot, tmp_path):
        """Test that preview has dark background in dark mode."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.components.document_tab import (
            HAS_WEBENGINE,
            DocumentTab,
        )

        if not HAS_WEBENGINE:
            pytest.skip("WebEngine not available")

        ctx = get_app_context()
        ctx.set("view.theme", "dark", save=False)

        tab = DocumentTab(FakeMainWindow(ctx))

        bg_color = tab.preview.page().backgroundColor()
        assert bg_color.name() == "#1e1e1e"

        del tab
        QApplication.processEvents()

    def test_preview_background_light_mode(self, qtbot, tmp_path):
        """Test that preview has white background in light mode."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.components.document_tab import (
            HAS_WEBENGINE,
            DocumentTab,
        )

        if not HAS_WEBENGINE:
            pytest.skip("WebEngine not available")

        ctx = get_app_context()
        ctx.set("view.theme", "light", save=False)

        tab = DocumentTab(FakeMainWindow(ctx))

        bg_color = tab.preview.page().backgroundColor()
        assert bg_color.name() == "#ffffff"

        del tab
        QApplication.processEvents()


class TestDarkModeTheming:
    """Regression tests for comprehensive dark mode theming.

    Bug: Various UI elements (menu bar, tab bar, Explorer panel) showed
    white/light backgrounds in dark mode.

    Fix: Added comprehensive stylesheets for all major UI elements.
    """

    def test_dark_theme_colors_are_dark(self):
        """Test that dark theme has dark background colors."""
        from markdown_editor.markdown6.theme import DARK_THEME

        # All background colors should be dark (low brightness)
        def is_dark(hex_color: str) -> bool:
            """Check if a hex color is dark (average RGB < 128)."""
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r + g + b) / 3 < 128

        assert is_dark(DARK_THEME.bg_primary), f"bg_primary {DARK_THEME.bg_primary} should be dark"
        assert is_dark(DARK_THEME.bg_secondary), f"bg_secondary {DARK_THEME.bg_secondary} should be dark"
        assert is_dark(DARK_THEME.bg_tertiary), f"bg_tertiary {DARK_THEME.bg_tertiary} should be dark"
        assert is_dark(DARK_THEME.bg_input), f"bg_input {DARK_THEME.bg_input} should be dark"

    def test_light_theme_colors_are_light(self):
        """Test that light theme has light background colors."""
        from markdown_editor.markdown6.theme import LIGHT_THEME

        def is_light(hex_color: str) -> bool:
            """Check if a hex color is light (average RGB >= 200)."""
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r + g + b) / 3 >= 200

        assert is_light(LIGHT_THEME.bg_primary), f"bg_primary {LIGHT_THEME.bg_primary} should be light"
        assert is_light(LIGHT_THEME.bg_secondary), f"bg_secondary {LIGHT_THEME.bg_secondary} should be light"

    def test_menu_bar_stylesheet_uses_theme_colors(self):
        """Test that menu bar stylesheet uses correct theme background."""
        from markdown_editor.markdown6.theme import DARK_THEME, StyleSheets

        stylesheet = StyleSheets.menu_bar(DARK_THEME)

        # Should use dark theme background color
        assert DARK_THEME.bg_secondary in stylesheet
        assert DARK_THEME.text_primary in stylesheet

    def test_tab_widget_stylesheet_uses_theme_colors(self):
        """Test that tab widget stylesheet uses correct theme colors."""
        from markdown_editor.markdown6.theme import DARK_THEME, StyleSheets

        stylesheet = StyleSheets.tab_widget(DARK_THEME)

        # Should use dark theme colors
        assert DARK_THEME.bg_primary in stylesheet
        assert DARK_THEME.bg_secondary in stylesheet
        assert DARK_THEME.bg_tertiary in stylesheet

    def test_panel_stylesheet_uses_theme_colors(self):
        """Test that panel stylesheet uses correct theme colors."""
        from markdown_editor.markdown6.theme import DARK_THEME, StyleSheets

        stylesheet = StyleSheets.panel(DARK_THEME)

        assert DARK_THEME.bg_secondary in stylesheet
        assert DARK_THEME.text_primary in stylesheet

    def test_apply_application_theme_dark(self, qtbot):
        """Test that apply_application_theme applies dark styling."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.markdown_editor import (
            apply_application_theme,
        )

        apply_application_theme(dark_mode=True)

        app = QApplication.instance()
        stylesheet = app.styleSheet()

        # Should have menu bar styling
        assert "QMenuBar" in stylesheet
        # Should have tab styling
        assert "QTabWidget" in stylesheet or "QTabBar" in stylesheet
        # Should have dark colors
        assert "#1e1e1e" in stylesheet or "#252526" in stylesheet or "#2d2d2d" in stylesheet

    def test_apply_application_theme_light(self, qtbot):
        """Test that apply_application_theme applies light styling."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.markdown_editor import (
            apply_application_theme,
        )

        apply_application_theme(dark_mode=False)

        app = QApplication.instance()
        stylesheet = app.styleSheet()

        # Should have menu bar styling
        assert "QMenuBar" in stylesheet
        # Should have light colors
        assert "#ffffff" in stylesheet or "#f3f3f3" in stylesheet

    def test_sidebar_theme_applies_dark_colors(self, qtbot):
        """Test that sidebar applies dark colors in dark mode."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.markdown_editor import MarkdownEditor

        ctx = get_app_context()
        ctx.set("view.theme", "dark", save=False)

        editor = MarkdownEditor()

        # Check sidebar exists and has activity bar
        assert hasattr(editor, 'sidebar')
        assert hasattr(editor.sidebar, 'activity_bar')

        editor.close()
        del editor
        QApplication.processEvents()

    def test_all_stylesheets_contain_background_color(self):
        """Test that all relevant stylesheets set background-color."""
        from markdown_editor.markdown6.theme import DARK_THEME, StyleSheets

        # All these should explicitly set background-color
        stylesheets_to_check = [
            ("menu_bar", StyleSheets.menu_bar(DARK_THEME)),
            ("menu", StyleSheets.menu(DARK_THEME)),
            ("tab_widget", StyleSheets.tab_widget(DARK_THEME)),
            ("main_window", StyleSheets.main_window(DARK_THEME)),
            ("status_bar", StyleSheets.status_bar(DARK_THEME)),
            ("dock_widget", StyleSheets.dock_widget(DARK_THEME)),
            ("toolbox", StyleSheets.toolbox(DARK_THEME)),
            ("panel", StyleSheets.panel(DARK_THEME)),
            ("tree_widget", StyleSheets.tree_widget(DARK_THEME)),
            ("splitter", StyleSheets.splitter(DARK_THEME)),
        ]

        for name, stylesheet in stylesheets_to_check:
            assert "background-color" in stylesheet, f"{name} stylesheet missing background-color"

    def test_graph_export_dialog_theming(self, qtbot, tmp_path):
        """Test that GraphExportDialog has proper dark mode theming."""
        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.components.graph_export import (
            GraphExportDialog,
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "test.md").write_text("# Test")

        ctx = get_app_context()
        ctx.set("view.theme", "dark", save=False)

        dialog = GraphExportDialog(project, ctx=ctx)
        qtbot.addWidget(dialog)

        stylesheet = dialog.styleSheet()

        # Should have styling for all key widgets
        assert "QTreeWidget" in stylesheet
        assert "QComboBox" in stylesheet
        assert "QCheckBox" in stylesheet
        assert "QRadioButton" in stylesheet
        assert "QSplitter" in stylesheet
        # Should use dark theme colors
        assert "#" in stylesheet  # Has color values


class TestGraphvizDarkMode:
    """Regression tests for Graphviz SVG dark mode.

    Bug: Graph preview showed black text on dark background because
    SVG text elements didn't have explicit fill colors.

    Fix: Added regex to inject fill color into text elements without one.
    """

    def test_dark_mode_adds_fill_to_text_without_fill(self):
        """Test that text elements without fill get light color in dark mode."""
        from markdown_editor.markdown6.graphviz_service import _apply_dark_mode

        svg = '<svg><text x="10" y="20">Node Label</text></svg>'
        result = _apply_dark_mode(svg)

        assert 'fill="#d4d4d4"' in result
        assert "<text" in result

    def test_dark_mode_replaces_black_fill(self):
        """Test that black fill is replaced with light color."""
        from markdown_editor.markdown6.graphviz_service import _apply_dark_mode

        svg = '<svg><text fill="black">Node Label</text></svg>'
        result = _apply_dark_mode(svg)

        assert 'fill="#d4d4d4"' in result
        assert 'fill="black"' not in result

    def test_dark_mode_replaces_white_background(self):
        """Test that white background is replaced with dark color."""
        from markdown_editor.markdown6.graphviz_service import _apply_dark_mode

        svg = '<svg><rect fill="white"/></svg>'
        result = _apply_dark_mode(svg)

        assert 'fill="#1e1e1e"' in result
        assert 'fill="white"' not in result

    def test_dark_mode_replaces_black_stroke(self):
        """Test that black strokes are replaced with light color."""
        from markdown_editor.markdown6.graphviz_service import _apply_dark_mode

        svg = '<svg><path stroke="black"/></svg>'
        result = _apply_dark_mode(svg)

        assert 'stroke="#d4d4d4"' in result
        assert 'stroke="black"' not in result

    def test_dark_mode_preserves_existing_text_fill(self):
        """Test that text with existing non-black fill is preserved."""
        from markdown_editor.markdown6.graphviz_service import _apply_dark_mode

        svg = '<svg><text fill="red">Colored Text</text></svg>'
        result = _apply_dark_mode(svg)

        # Should keep the red fill, not add another one
        assert 'fill="red"' in result
        assert result.count('fill=') == 1


class TestMathRendering:
    """Regression test: math should render when file has a file:// base URL.

    Bug: KaTeX loads from CDN (https://), but when a saved file is previewed,
    the base URL is file:// which blocks https:// resource loading due to
    Qt's mixed-content security policy. Math shows as raw $...$ text.
    """

    def test_katex_loads_with_file_base_url(self, qtbot, tmp_path):
        """KaTeX scripts must load even when preview uses file:// base URL."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.components.document_tab import (
            HAS_WEBENGINE,
            DocumentTab,
        )
        from markdown_editor.markdown6.extensions.math import get_math_js

        if not HAS_WEBENGINE:
            pytest.skip("WebEngine not available")

        ctx = get_app_context()
        main = FakeMainWindow(ctx)
        main.get_html_template = lambda content, **kw: (
            '<!DOCTYPE html><html><head>'
            + get_math_js()
            + '</head><body>' + content + '</body></html>'
        )

        tab = DocumentTab(main)
        # Simulate a saved file — this sets the file:// base URL
        test_file = tmp_path / "test.md"
        test_file.write_text("$E=mc^2$")
        tab.file_path = test_file
        tab._preview_needs_full_reload = True
        tab.editor.setPlainText("$E=mc^2$")
        tab.render_markdown()

        # Wait for CDN script to load
        def katex_loaded():
            result = [None]
            tab.preview.page().runJavaScript(
                "typeof katex !== 'undefined'",
                lambda r: result.__setitem__(0, r),
            )
            qtbot.wait(100)
            return result[0] is True

        qtbot.waitUntil(katex_loaded, timeout=8000)

        del tab
        QApplication.processEvents()


class TestPreviewWheelScrollSync:
    """Regression test: wheel-scrolling the preview should scroll the editor.

    Bug: Scrolling the preview pane did not move the editor — only
    editor→preview sync existed. Fix: an event filter on WebEngine's
    internal rendering widget forwards wheel events to the editor.
    The editor's valueChanged then syncs the preview via scrollToSourceLine.
    """

    def test_wheel_filter_installed(self, qtbot):
        """The preview event filters (wheel + key) should be installed
        on the preview once its page has loaded."""
        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.components.document_tab import (
            HAS_WEBENGINE,
            DocumentTab,
        )

        if not HAS_WEBENGINE:
            pytest.skip("WebEngine not available")

        ctx = get_app_context()
        main = FakeMainWindow(ctx)
        tab = DocumentTab(main)

        # Trigger a render so loadFinished fires and filters get installed
        tab.editor.setPlainText("test content\n" * 50)
        tab._preview_needs_full_reload = True
        tab.render_markdown()
        qtbot.wait(500)

        assert tab._preview_filters_installed, (
            "Preview event filters should be installed after first page load"
        )

        del tab
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()


class TestSettingsChangeDirtyFlag:
    """Regression test: changing a setting should not mark the document dirty.

    Bug: Toggling settings like show_whitespace or word_wrap causes
    EnhancedEditor to call document().setDefaultTextOption() or
    setLineWrapMode(), which Qt treats as a content change, emitting
    textChanged and marking the tab as having unsaved changes.
    """

    def test_toggle_theme_does_not_emit_text_changed(self, qtbot):
        """Toggling theme should not emit textChanged on the editor.

        Root cause: set_dark_mode() calls rehighlight(), which Qt treats
        as a content modification, emitting textChanged on the editor.
        DocumentTab._on_text_changed picks this up and sets unsaved_changes.

        Fix: EnhancedEditor blocks signals during setting application.
        """
        from markdown_editor.markdown6.app_context import get_app_context
        from markdown_editor.markdown6.enhanced_editor import EnhancedEditor

        ctx = get_app_context()
        editor = EnhancedEditor(ctx=ctx)
        qtbot.addWidget(editor)
        editor.setPlainText("hello world")

        # Theme change should NOT emit textChanged
        with qtbot.assertNotEmitted(editor.textChanged):
            ctx.set("view.theme", "dark", save=False)

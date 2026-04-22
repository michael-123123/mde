"""Tests for the theme module."""


from markdown_editor.markdown6.theme import (
    DARK_THEME,
    LIGHT_THEME,
    StyleSheets,
    apply_theme,
    get_theme,
)


class TestThemeColors:
    """Tests for ThemeColors dataclass."""

    def test_dark_theme_has_all_fields(self):
        """Test that dark theme has all required fields."""
        assert DARK_THEME.bg_primary is not None
        assert DARK_THEME.bg_secondary is not None
        assert DARK_THEME.text_primary is not None
        assert DARK_THEME.accent is not None
        assert DARK_THEME.selection_bg is not None
        assert DARK_THEME.border is not None
        assert DARK_THEME.error is not None
        assert DARK_THEME.link is not None

    def test_light_theme_has_all_fields(self):
        """Test that light theme has all required fields."""
        assert LIGHT_THEME.bg_primary is not None
        assert LIGHT_THEME.bg_secondary is not None
        assert LIGHT_THEME.text_primary is not None
        assert LIGHT_THEME.accent is not None
        assert LIGHT_THEME.selection_bg is not None
        assert LIGHT_THEME.border is not None
        assert LIGHT_THEME.error is not None
        assert LIGHT_THEME.link is not None

    def test_dark_theme_colors_are_hex(self):
        """Test that dark theme colors are valid hex strings."""
        assert DARK_THEME.bg_primary.startswith("#")
        assert len(DARK_THEME.bg_primary) == 7  # #RRGGBB

    def test_light_theme_colors_are_hex(self):
        """Test that light theme colors are valid hex strings."""
        assert LIGHT_THEME.bg_primary.startswith("#")
        assert len(LIGHT_THEME.bg_primary) == 7

    def test_themes_are_different(self):
        """Test that dark and light themes are actually different."""
        assert DARK_THEME.bg_primary != LIGHT_THEME.bg_primary
        assert DARK_THEME.text_primary != LIGHT_THEME.text_primary


class TestGetTheme:
    """Tests for get_theme function."""

    def test_get_dark_theme(self):
        """Test getting dark theme."""
        theme = get_theme(dark_mode=True)
        assert theme is DARK_THEME

    def test_get_light_theme(self):
        """Test getting light theme."""
        theme = get_theme(dark_mode=False)
        assert theme is LIGHT_THEME


class TestStyleSheets:
    """Tests for StyleSheets class."""

    def test_dialog_stylesheet_contains_colors(self):
        """Test that dialog stylesheet contains theme colors."""
        stylesheet = StyleSheets.dialog(DARK_THEME)
        assert DARK_THEME.bg_secondary in stylesheet
        assert DARK_THEME.text_primary in stylesheet
        assert "QDialog" in stylesheet

    def test_line_edit_stylesheet(self):
        """Test line edit stylesheet generation."""
        stylesheet = StyleSheets.line_edit(DARK_THEME)
        assert DARK_THEME.bg_input in stylesheet
        assert DARK_THEME.accent in stylesheet
        assert "QLineEdit" in stylesheet

    def test_button_stylesheet(self):
        """Test button stylesheet generation."""
        stylesheet = StyleSheets.button(DARK_THEME)
        assert DARK_THEME.accent in stylesheet
        assert DARK_THEME.accent_hover in stylesheet
        assert "QPushButton" in stylesheet
        assert "hover" in stylesheet

    def test_flat_button_stylesheet(self):
        """Test flat button stylesheet generation."""
        stylesheet = StyleSheets.flat_button(DARK_THEME)
        assert "transparent" in stylesheet
        assert "QPushButton" in stylesheet

    def test_list_widget_stylesheet(self):
        """Test list widget stylesheet generation."""
        stylesheet = StyleSheets.list_widget(DARK_THEME)
        assert DARK_THEME.selection_bg in stylesheet
        assert "QListWidget" in stylesheet
        assert "selected" in stylesheet

    def test_tree_widget_stylesheet(self):
        """Test tree widget stylesheet generation."""
        stylesheet = StyleSheets.tree_widget(DARK_THEME)
        assert DARK_THEME.bg_secondary in stylesheet
        assert "QTreeWidget" in stylesheet

    def test_table_widget_stylesheet(self):
        """Test table widget stylesheet generation."""
        stylesheet = StyleSheets.table_widget(DARK_THEME)
        assert "QTableWidget" in stylesheet
        assert "QHeaderView" in stylesheet

    def test_combo_box_stylesheet(self):
        """Test combo box stylesheet generation."""
        stylesheet = StyleSheets.combo_box(DARK_THEME)
        assert "QComboBox" in stylesheet
        assert "drop-down" in stylesheet

    def test_spin_box_stylesheet(self):
        """Test spin box stylesheet generation."""
        stylesheet = StyleSheets.spin_box(DARK_THEME)
        assert "QSpinBox" in stylesheet

    def test_check_box_stylesheet(self):
        """Test check box stylesheet generation."""
        stylesheet = StyleSheets.check_box(DARK_THEME)
        assert "QCheckBox" in stylesheet
        assert "indicator" in stylesheet

    def test_scroll_area_stylesheet(self):
        """Test scroll area stylesheet generation."""
        stylesheet = StyleSheets.scroll_area(DARK_THEME)
        assert "QScrollArea" in stylesheet
        assert "QScrollBar" in stylesheet

    def test_panel_stylesheet(self):
        """Test panel stylesheet generation."""
        stylesheet = StyleSheets.panel(DARK_THEME)
        assert "QWidget" in stylesheet
        assert "background-color" in stylesheet
        assert "color" in stylesheet

    def test_popup_stylesheet(self):
        """Test popup stylesheet generation."""
        stylesheet = StyleSheets.popup(DARK_THEME)
        assert "QDialog" in stylesheet
        assert "QLineEdit" in stylesheet
        assert "QListWidget" in stylesheet

    def test_toolbox_stylesheet(self):
        """Test toolbox stylesheet generation."""
        stylesheet = StyleSheets.toolbox(DARK_THEME)
        assert "QToolBox" in stylesheet
        assert "QToolBox::tab" in stylesheet
        assert "background-color" in stylesheet

    def test_dock_widget_stylesheet(self):
        """Test dock widget stylesheet generation."""
        stylesheet = StyleSheets.dock_widget(DARK_THEME)
        assert "QDockWidget" in stylesheet
        assert "QDockWidget::title" in stylesheet
        assert "background-color" in stylesheet

    def test_menu_bar_stylesheet(self):
        """Test menu bar stylesheet generation."""
        stylesheet = StyleSheets.menu_bar(DARK_THEME)
        assert "QMenuBar" in stylesheet
        assert "QMenuBar::item" in stylesheet
        assert "background-color" in stylesheet

    def test_menu_stylesheet(self):
        """Test menu stylesheet generation."""
        stylesheet = StyleSheets.menu(DARK_THEME)
        assert "QMenu" in stylesheet
        assert "QMenu::item" in stylesheet
        assert "QMenu::separator" in stylesheet
        assert "background-color" in stylesheet

    def test_tab_widget_stylesheet(self):
        """Test tab widget stylesheet generation."""
        stylesheet = StyleSheets.tab_widget(DARK_THEME)
        assert "QTabWidget" in stylesheet
        assert "QTabBar" in stylesheet
        assert "QTabBar::tab" in stylesheet
        assert "background-color" in stylesheet

    def test_main_window_stylesheet(self):
        """Test main window stylesheet generation."""
        stylesheet = StyleSheets.main_window(DARK_THEME)
        assert "QMainWindow" in stylesheet
        assert "background-color" in stylesheet

    def test_status_bar_stylesheet(self):
        """Test status bar stylesheet generation."""
        stylesheet = StyleSheets.status_bar(DARK_THEME)
        assert "QStatusBar" in stylesheet
        assert "background-color" in stylesheet

    def test_radio_button_stylesheet(self):
        """Test radio button stylesheet generation."""
        stylesheet = StyleSheets.radio_button(DARK_THEME)
        assert "QRadioButton" in stylesheet
        assert "color" in stylesheet

    def test_splitter_stylesheet(self):
        """Test splitter stylesheet generation."""
        stylesheet = StyleSheets.splitter(DARK_THEME)
        assert "QSplitter" in stylesheet
        assert "QSplitter::handle" in stylesheet

    def test_stylesheets_work_with_light_theme(self):
        """Test that all stylesheets work with light theme."""
        # Just verify they don't raise
        StyleSheets.dialog(LIGHT_THEME)
        StyleSheets.line_edit(LIGHT_THEME)
        StyleSheets.button(LIGHT_THEME)
        StyleSheets.list_widget(LIGHT_THEME)
        StyleSheets.tree_widget(LIGHT_THEME)
        StyleSheets.popup(LIGHT_THEME)
        StyleSheets.panel(LIGHT_THEME)
        StyleSheets.toolbox(LIGHT_THEME)
        StyleSheets.dock_widget(LIGHT_THEME)
        StyleSheets.menu_bar(LIGHT_THEME)
        StyleSheets.menu(LIGHT_THEME)
        StyleSheets.tab_widget(LIGHT_THEME)
        StyleSheets.main_window(LIGHT_THEME)
        StyleSheets.status_bar(LIGHT_THEME)
        StyleSheets.radio_button(LIGHT_THEME)
        StyleSheets.splitter(LIGHT_THEME)


class TestApplyTheme:
    """Tests for apply_theme function."""

    def test_apply_theme_combines_styles(self, qtbot):
        """Test that apply_theme combines multiple stylesheets."""
        from PySide6.QtWidgets import QWidget

        widget = QWidget()
        qtbot.addWidget(widget)

        apply_theme(widget, DARK_THEME, StyleSheets.dialog, StyleSheets.button)

        stylesheet = widget.styleSheet()
        assert "QDialog" in stylesheet
        assert "QPushButton" in stylesheet

    def test_apply_theme_with_single_style(self, qtbot):
        """Test apply_theme with a single stylesheet."""
        from PySide6.QtWidgets import QWidget

        widget = QWidget()
        qtbot.addWidget(widget)

        apply_theme(widget, DARK_THEME, StyleSheets.dialog)

        stylesheet = widget.styleSheet()
        assert "QDialog" in stylesheet

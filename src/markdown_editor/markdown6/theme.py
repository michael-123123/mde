"""Centralized theme system for the Markdown editor."""

from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtGui import QColor


@dataclass
class ThemeColors:
    """Color definitions for a theme."""
    # Backgrounds
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_input: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str

    # Accents
    accent: str
    accent_hover: str

    # Selection
    selection_bg: str
    selection_text: str

    # Borders
    border: str
    border_light: str

    # Status
    success: str
    warning: str
    error: str
    info: str

    # Code
    code_bg: str

    # Links
    link: str


# Dark theme colors
DARK_THEME = ThemeColors(
    bg_primary="#1e1e1e",
    bg_secondary="#252526",
    bg_tertiary="#2d2d2d",
    bg_input="#3c3c3c",
    text_primary="#cccccc",
    text_secondary="#999999",
    text_muted="#808080",
    accent="#0e639c",
    accent_hover="#1177bb",
    selection_bg="#094771",
    selection_text="#ffffff",
    border="#454545",
    border_light="#333333",
    success="#3fb950",
    warning="#d29922",
    error="#f85149",
    info="#58a6ff",
    code_bg="#2d2d2d",
    link="#4ec9b0",
)

# Light theme colors
LIGHT_THEME = ThemeColors(
    bg_primary="#ffffff",
    bg_secondary="#f3f3f3",
    bg_tertiary="#e8e8e8",
    bg_input="#ffffff",
    text_primary="#333333",
    text_secondary="#666666",
    text_muted="#999999",
    accent="#0078d4",
    accent_hover="#106ebe",
    selection_bg="#cce8ff",
    selection_text="#000000",
    border="#cccccc",
    border_light="#e0e0e0",
    success="#1a7f37",
    warning="#9a6700",
    error="#cf222e",
    info="#0969da",
    code_bg="#f6f8fa",
    link="#0366d6",
)


def get_theme(dark_mode: bool) -> ThemeColors:
    """Get the theme colors for the given mode."""
    return DARK_THEME if dark_mode else LIGHT_THEME


def get_theme_from_ctx(ctx) -> ThemeColors:
    """Get the current theme from an AppContext."""
    return get_theme(ctx.get("view.theme", "light") == "dark")


class StyleSheets:
    """Pre-built stylesheets for common widget types."""

    @staticmethod
    def dialog(theme: ThemeColors) -> str:
        """Stylesheet for dialog windows."""
        return f"""
            QDialog {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
            }}
            QWidget {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
            }}
            QLabel {{
                color: {theme.text_primary};
                background-color: transparent;
            }}
            QGroupBox {{
                background-color: {theme.bg_secondary};
                border: 1px solid {theme.border};
                border-radius: 4px;
                margin-top: 12px;
                padding: 12px 8px 8px 8px;
                color: {theme.text_primary};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 4px;
                color: {theme.text_primary};
                background-color: {theme.bg_secondary};
            }}
            QStackedWidget {{
                background-color: {theme.bg_secondary};
            }}
            QScrollArea {{
                background-color: {theme.bg_secondary};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {theme.bg_secondary};
            }}
        """

    @staticmethod
    def line_edit(theme: ThemeColors) -> str:
        """Stylesheet for line edits."""
        return f"""
            QLineEdit {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                padding: 6px;
                border-radius: 2px;
            }}
            QLineEdit:focus {{
                border-color: {theme.accent};
            }}
        """

    @staticmethod
    def button(theme: ThemeColors) -> str:
        """Stylesheet for buttons."""
        return f"""
            QPushButton {{
                background-color: {theme.accent};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 2px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent};
            }}
            QPushButton:disabled {{
                background-color: {theme.bg_tertiary};
                color: {theme.text_muted};
            }}
        """

    @staticmethod
    def flat_button(theme: ThemeColors) -> str:
        """Stylesheet for flat/text buttons."""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.text_primary};
                border: none;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {theme.bg_tertiary};
            }}
        """

    @staticmethod
    def list_widget(theme: ThemeColors) -> str:
        """Stylesheet for list widgets."""
        return f"""
            QListWidget {{
                background-color: {theme.bg_primary};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                outline: none;
            }}
            QListWidget::item {{
                color: {theme.text_primary};
            }}
            QListWidget::item:selected {{
                background-color: {theme.selection_bg};
                color: {theme.selection_text};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {theme.bg_tertiary};
            }}
        """

    @staticmethod
    def tree_widget(theme: ThemeColors) -> str:
        """Stylesheet for tree widgets."""
        return f"""
            QTreeWidget, QTreeView {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                border: none;
                outline: none;
                font-size: 13px;
            }}
            QTreeWidget::item, QTreeView::item {{
                padding: 6px 4px;
                color: {theme.text_primary};
            }}
            QTreeWidget::item:selected, QTreeView::item:selected {{
                background-color: {theme.selection_bg};
                color: {theme.selection_text};
            }}
            QTreeWidget::item:hover, QTreeView::item:hover {{
                background-color: {theme.bg_tertiary};
            }}
        """

    @staticmethod
    def table_widget(theme: ThemeColors) -> str:
        """Stylesheet for table widgets."""
        return f"""
            QTableWidget {{
                background-color: {theme.bg_primary};
                color: {theme.text_primary};
                gridline-color: {theme.border};
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {theme.selection_bg};
                color: {theme.selection_text};
            }}
            QHeaderView::section {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                padding: 4px;
                border: 1px solid {theme.border};
            }}
        """

    @staticmethod
    def combo_box(theme: ThemeColors) -> str:
        """Stylesheet for combo boxes."""
        return f"""
            QComboBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                padding: 4px 8px;
                border-radius: 2px;
            }}
            QComboBox:hover {{
                border-color: {theme.accent};
            }}
            QComboBox::drop-down {{
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.bg_primary};
                color: {theme.text_primary};
                selection-background-color: {theme.selection_bg};
            }}
        """

    @staticmethod
    def spin_box(theme: ThemeColors) -> str:
        """Stylesheet for spin boxes.

        Only style colors — avoid border/padding overrides that break
        native up/down button rendering on some platforms (e.g. GTK).
        """
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
            }}
        """

    @staticmethod
    def check_box(theme: ThemeColors) -> str:
        """Stylesheet for check boxes."""
        return f"""
            QCheckBox {{
                color: {theme.text_primary};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
        """

    @staticmethod
    def radio_button(theme: ThemeColors) -> str:
        """Stylesheet for radio buttons."""
        return f"""
            QRadioButton {{
                color: {theme.text_primary};
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
            }}
        """

    @staticmethod
    def splitter(theme: ThemeColors) -> str:
        """Stylesheet for QSplitter."""
        return f"""
            QSplitter {{
                background-color: {theme.bg_secondary};
                border: none;
            }}
            QSplitter::handle {{
                background-color: {theme.bg_tertiary};
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
            QSplitter::handle:vertical {{
                height: 1px;
            }}
        """

    @staticmethod
    def scroll_area(theme: ThemeColors) -> str:
        """Stylesheet for scroll areas."""
        return f"""
            QScrollArea {{
                background-color: {theme.bg_primary};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {theme.bg_secondary};
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme.bg_tertiary};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme.text_muted};
            }}
        """

    @staticmethod
    def panel(theme: ThemeColors) -> str:
        """Stylesheet for side panels."""
        return f"""
            QWidget {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
            }}
        """

    @staticmethod
    def toolbox(theme: ThemeColors) -> str:
        """Stylesheet for QToolBox (sidebar container)."""
        return f"""
            QToolBox {{
                background-color: {theme.bg_secondary};
            }}
            QToolBox::tab {{
                background-color: {theme.bg_tertiary};
                color: {theme.text_primary};
                padding: 6px 12px;
                border: none;
                border-bottom: 1px solid {theme.border};
            }}
            QToolBox::tab:selected {{
                background-color: {theme.bg_secondary};
                font-weight: bold;
            }}
            QToolBox::tab:hover {{
                background-color: {theme.bg_input};
            }}
        """

    @staticmethod
    def dock_widget(theme: ThemeColors) -> str:
        """Stylesheet for QDockWidget."""
        return f"""
            QDockWidget {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }}
            QDockWidget::title {{
                background-color: {theme.bg_tertiary};
                color: {theme.text_primary};
                padding: 6px;
                border-bottom: 1px solid {theme.border};
            }}
        """

    @staticmethod
    def menu_bar(theme: ThemeColors) -> str:
        """Stylesheet for QMenuBar."""
        return f"""
            QMenuBar {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                border: none;
                padding: 2px;
            }}
            QMenuBar::item {{
                background-color: transparent;
                color: {theme.text_primary};
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {theme.bg_tertiary};
            }}
            QMenuBar::item:pressed {{
                background-color: {theme.selection_bg};
            }}
        """

    @staticmethod
    def menu(theme: ThemeColors) -> str:
        """Stylesheet for QMenu (dropdown menus)."""
        return f"""
            QMenu {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {theme.text_primary};
                padding: 6px 24px 6px 8px;
            }}
            QMenu::item:selected {{
                background-color: {theme.selection_bg};
                color: {theme.selection_text};
            }}
            QMenu::item:disabled {{
                color: {theme.text_muted};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {theme.border};
                margin: 4px 8px;
            }}
        """

    @staticmethod
    def tab_widget(theme: ThemeColors) -> str:
        """Stylesheet for QTabWidget and QTabBar."""
        return f"""
            QTabWidget {{
                background-color: {theme.bg_secondary};
                border: none;
            }}
            QTabWidget::pane {{
                background-color: {theme.bg_primary};
                border: none;
            }}
            QTabWidget::tab-bar {{
                alignment: left;
                background-color: {theme.bg_secondary};
            }}
            QTabBar {{
                background-color: {theme.bg_secondary};
                border: none;
            }}
            QTabBar::tab {{
                background-color: {theme.bg_tertiary};
                color: {theme.text_secondary};
                border: none;
                padding: 6px 12px;
                margin-right: 1px;
            }}
            QTabBar::tab:selected {{
                background-color: {theme.bg_primary};
                color: {theme.text_primary};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {theme.bg_input};
            }}
            QTabBar::close-button {{
                subcontrol-position: right;
            }}
            QTabBar QToolButton {{
                background-color: {theme.bg_secondary};
                border: none;
            }}
        """

    @staticmethod
    def main_window(theme: ThemeColors) -> str:
        """Stylesheet for QMainWindow."""
        return f"""
            QMainWindow {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
            }}
            QMainWindow::separator {{
                background-color: {theme.bg_secondary};
                width: 0px;
                height: 0px;
            }}
        """

    @staticmethod
    def status_bar(theme: ThemeColors) -> str:
        """Stylesheet for QStatusBar."""
        return f"""
            QStatusBar {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                border-top: 1px solid {theme.border};
            }}
            QStatusBar::item {{
                border: none;
            }}
            QStatusBar QLabel {{
                color: {theme.text_secondary};
                padding: 2px 4px;
            }}
        """

    @staticmethod
    def popup(theme: ThemeColors) -> str:
        """Stylesheet for popup dialogs."""
        return f"""
            QDialog {{
                background-color: {theme.bg_secondary};
                border: 1px solid {theme.border};
                border-radius: 6px;
            }}
            QLineEdit {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: none;
                padding: 12px;
                font-size: 14px;
            }}
            QListWidget {{
                background-color: {theme.bg_secondary};
                color: {theme.text_primary};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                color: {theme.text_primary};
            }}
            QListWidget::item:selected {{
                background-color: {theme.selection_bg};
                color: {theme.selection_text};
            }}
            QListWidget::item:hover {{
                background-color: {theme.bg_tertiary};
            }}
        """


def apply_theme(widget, theme: ThemeColors, *style_funcs):
    """Apply multiple stylesheet functions to a widget.

    Example:
        apply_theme(dialog, theme, StyleSheets.dialog, StyleSheets.button)
    """
    styles = "\n".join(func(theme) for func in style_funcs)
    widget.setStyleSheet(styles)

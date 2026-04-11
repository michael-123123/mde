"""Sidebar container with activity bar and collapsible tool window.

Provides VSCode/PyCharm-style sidebar with:
- Activity bar (always visible)
- Tool window (collapsible with animation)
- Click active tab to collapse, click other tab to switch/expand
"""

from PySide6.QtCore import Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QFrame,
    QLabel,
    QSizePolicy,
)
from PySide6.QtGui import QFont

from markdown_editor.markdown6.activity_bar import ActivityBar

from markdown_editor.markdown6.theme import get_theme


class Sidebar(QWidget):
    """Sidebar with activity bar and collapsible tool window."""

    # Emitted when a panel should be shown (index)
    panel_changed = Signal(int)

    # Emitted when sidebar is collapsed/expanded
    collapsed_changed = Signal(bool)

    # Emitted when sidebar width changes (for parent splitter updates)
    width_changed = Signal(int)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

        self._collapsed = False
        self._active_index = 0
        self._tool_width = 280  # Default tool window width
        self._min_tool_width = 200
        self._animation: QVariantAnimation | None = None
        self._panel_titles: list[str] = []

        self._init_ui()
        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def _init_ui(self):
        """Initialize the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Activity bar (always visible)
        self.activity_bar = ActivityBar(self.ctx, width=48, parent=self)
        self.activity_bar.tab_clicked.connect(self._on_tab_clicked)
        layout.addWidget(self.activity_bar)

        # Tool window (collapsible)
        self.tool_window = QFrame()
        self.tool_window.setObjectName("ToolWindow")
        self.tool_window.setMinimumWidth(0)
        self.tool_window.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        tool_layout = QVBoxLayout(self.tool_window)
        tool_layout.setContentsMargins(0, 0, 0, 0)
        tool_layout.setSpacing(0)

        # Header
        self._header_frame = QFrame()
        self._header_frame.setObjectName("ToolWindowHeader")
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)

        self._header_label = QLabel()
        header_font = QFont(self._header_label.font())
        header_font.setBold(True)
        self._header_label.setFont(header_font)
        header_layout.addWidget(self._header_label)
        header_layout.addStretch()

        tool_layout.addWidget(self._header_frame)

        # Stacked widget for panels
        self.stack = QStackedWidget()
        tool_layout.addWidget(self.stack, 1)

        layout.addWidget(self.tool_window)

        # Set initial width
        self.tool_window.setFixedWidth(self._tool_width)

        # Set initial sidebar size constraints
        initial_width = 48 + self._tool_width
        self.setFixedWidth(initial_width)

    def addPanel(self, title: str, icon: str, widget: QWidget) -> int:
        """Add a panel to the sidebar.

        Args:
            title: Panel title shown in header
            icon: Emoji icon for the activity bar tab
            widget: The panel widget

        Returns:
            The index of the new panel
        """
        index = self.activity_bar.addTab(icon, title)
        self.stack.addWidget(widget)
        self._panel_titles.append(title)

        # Set header for first panel
        if index == 0:
            self._header_label.setText(title)

        return index

    def setActivePanel(self, index: int):
        """Set the active panel by index."""
        if 0 <= index < self.stack.count():
            self._active_index = index
            self.activity_bar.setActiveTab(index)
            self.stack.setCurrentIndex(index)
            if index < len(self._panel_titles):
                self._header_label.setText(self._panel_titles[index])
            self.panel_changed.emit(index)

    def activeIndex(self) -> int:
        """Return the active panel index."""
        return self._active_index

    def isCollapsed(self) -> bool:
        """Return whether the sidebar is collapsed."""
        return self._collapsed

    def setCollapsed(self, collapsed: bool, animated: bool = True):
        """Set the collapsed state."""
        if collapsed:
            self.collapse(animated)
        else:
            self.expand(animated)

    def collapse(self, animated: bool = True):
        """Collapse the tool window."""
        if self._collapsed:
            return

        # Store current width for restore
        current_width = self.tool_window.width()
        if current_width > self._min_tool_width:
            self._tool_width = current_width

        self._collapsed = True
        self.activity_bar.clearSelection()

        if animated:
            self._animate_width(0)
        else:
            self.tool_window.setFixedWidth(0)
            self._update_size_constraints()

        self.collapsed_changed.emit(True)

    def expand(self, animated: bool = True):
        """Expand the tool window."""
        if not self._collapsed:
            return

        target_width = max(self._tool_width, self._min_tool_width)

        self._collapsed = False
        self.activity_bar.setActiveTab(self._active_index)

        if animated:
            self._animate_width(target_width)
        else:
            self.tool_window.setFixedWidth(target_width)
            self._update_size_constraints()

        self.collapsed_changed.emit(False)

    def toggle(self):
        """Toggle collapsed state."""
        if self._collapsed:
            self.expand()
        else:
            self.collapse()

    def _animate_width(self, target_width: int, duration: int = 150):
        """Animate the tool window width."""
        if self._animation is not None:
            self._animation.stop()

        start_width = self.tool_window.width()

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(duration)
        self._animation.setStartValue(start_width)
        self._animation.setEndValue(target_width)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_value_changed(value):
            self.tool_window.setFixedWidth(int(value))
            self._update_size_constraints()

        self._animation.valueChanged.connect(on_value_changed)
        self._animation.start()

    def _update_size_constraints(self):
        """Update widget size constraints based on current state."""
        bar_width = self.activity_bar.width()
        tool_width = self.tool_window.width()
        total_width = bar_width + tool_width

        # Set fixed width to force the splitter to respect our size
        self.setFixedWidth(total_width)
        self.updateGeometry()

        # Notify parent to update splitter
        self.width_changed.emit(total_width)

    def _on_tab_clicked(self, index: int):
        """Handle activity bar tab click."""
        if self._collapsed:
            # Expand and show the clicked panel
            self._active_index = index
            self.stack.setCurrentIndex(index)
            if index < len(self._panel_titles):
                self._header_label.setText(self._panel_titles[index])
            self.expand()
            self.panel_changed.emit(index)
        elif index == self._active_index:
            # Clicking active tab collapses
            self.collapse()
        else:
            # Switch to different panel
            self.setActivePanel(index)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.tool_window.setStyleSheet(f"""
            #ToolWindow {{
                background-color: {theme.bg_secondary};
                border-right: 1px solid {theme.border};
            }}
            #ToolWindowHeader {{
                background-color: {theme.bg_tertiary};
                border-bottom: 1px solid {theme.border};
            }}
            #ToolWindowHeader QLabel {{
                color: {theme.text_primary};
            }}
        """)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

    def sizeHint(self):
        """Return the preferred size."""
        from PySide6.QtCore import QSize
        width = self.activity_bar.width()
        if not self._collapsed:
            width += self._tool_width
        return QSize(width, 400)

"""Activity bar with vertical tabs for the sidebar.

Provides VSCode/PyCharm-style activity bar with:
- Vertical emoji tabs
- Hover/pressed/selected states
- Theme-aware styling
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QFontMetrics, QColor, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame


from markdown_editor.markdown6.theme import get_theme, ThemeColors


class ActivityTab(QWidget):
    """A single vertical tab in the activity bar."""

    clicked = Signal(int)  # index

    def __init__(
        self,
        label: str,
        tooltip: str,
        index: int,
        width: int = 48,
        height: int = 48,
        parent=None,
    ):
        super().__init__(parent)
        self.label = label
        self.tooltip_text = tooltip
        self.index = index

        self._selected = False
        self._hover = False
        self._pressed = False
        self._theme: ThemeColors | None = None

        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip(tooltip)

        # Larger font for emoji
        f = QFont(self.font())
        f.setPointSize(16)
        self.setFont(f)

    def setSelected(self, selected: bool):
        """Set the selected state."""
        if self._selected != selected:
            self._selected = selected
            self.update()

    def isSelected(self) -> bool:
        """Return whether this tab is selected."""
        return self._selected

    def setTheme(self, theme: ThemeColors):
        """Set the theme colors."""
        self._theme = theme
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit(self.index)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Get theme colors
        if self._theme:
            bg_base = QColor(self._theme.bg_secondary)
            bg_hover = QColor(self._theme.bg_tertiary)
            bg_pressed = QColor(self._theme.bg_input)
            bg_selected = QColor(self._theme.selection_bg)
            accent = QColor(self._theme.accent)
            border = QColor(self._theme.border)
        else:
            # Fallback light theme colors
            bg_base = QColor("#f3f4f6")
            bg_hover = QColor("#e5e7eb")
            bg_pressed = QColor("#d1d5db")
            bg_selected = QColor("#dbeafe")
            accent = QColor("#3b82f6")
            border = QColor("#e5e7eb")

        # Pick background based on state
        bg = bg_base
        if self._selected:
            bg = bg_selected
        if self._hover and not self._pressed:
            bg = bg_hover if not self._selected else bg_selected.lighter(105)
        if self._pressed:
            bg = bg_pressed

        # Fill background
        p.fillRect(self.rect(), bg)

        # Draw right border
        p.setPen(border)
        p.drawLine(self.rect().topRight(), self.rect().bottomRight())

        # Draw left accent stripe when selected
        if self._selected:
            p.setPen(accent)
            p.setBrush(accent)
            p.drawRect(0, 0, 3, self.height())

        # Draw centered emoji/text
        p.setFont(self.font())
        fm = QFontMetrics(p.font())
        text_rect = fm.boundingRect(self.label)

        x = (self.width() - text_rect.width()) // 2
        y = (self.height() + fm.ascent() - fm.descent()) // 2

        p.setPen(QColor(self._theme.text_primary if self._theme else "#1f2937"))
        p.drawText(x, y, self.label)


class ActivityBar(QFrame):
    """Vertical activity bar with tabs."""

    tab_clicked = Signal(int)  # index

    def __init__(self, ctx, width: int = 48, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._tabs: list[ActivityTab] = []
        self._active_index = 0
        self._bar_width = width

        self.setFixedWidth(width)
        self.setObjectName("ActivityBar")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        self._apply_theme()
        self.ctx.settings_changed.connect(self._on_setting_changed)

    def addTab(self, label: str, tooltip: str) -> int:
        """Add a tab to the activity bar.

        Returns the index of the new tab.
        """
        index = len(self._tabs)
        tab = ActivityTab(
            label=label,
            tooltip=tooltip,
            index=index,
            width=self._bar_width,
            height=self._bar_width,
            parent=self,
        )
        tab.clicked.connect(self._on_tab_clicked)

        # Apply current theme
        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")
        tab.setTheme(theme)

        self._tabs.append(tab)

        # Insert before the stretch
        self._layout.insertWidget(self._layout.count() - 1, tab)

        # Select first tab by default
        if index == 0:
            tab.setSelected(True)

        return index

    def setActiveTab(self, index: int):
        """Set the active tab by index."""
        if 0 <= index < len(self._tabs):
            self._active_index = index
            for i, tab in enumerate(self._tabs):
                tab.setSelected(i == index)

    def activeIndex(self) -> int:
        """Return the active tab index."""
        return self._active_index

    def clearSelection(self):
        """Clear selection from all tabs (used when collapsed)."""
        for tab in self._tabs:
            tab.setSelected(False)

    def _on_tab_clicked(self, index: int):
        """Handle tab click."""
        self.tab_clicked.emit(index)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.ctx.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")

        self.setStyleSheet(f"""
            #ActivityBar {{
                background-color: {theme.bg_secondary};
                border-right: 1px solid {theme.border};
            }}
        """)

        for tab in self._tabs:
            tab.setTheme(theme)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.theme":
            self._apply_theme()

"""Notification bell button (status bar) + dropdown drawer.

The bell is a small toolbutton living in the editor's status bar that
shows the unread notification count and acts as a click-target to open
the drawer. The drawer is a popup widget listing the full notification
history newest-first; opening it marks all currently-unread items as
read so the bell's indicator clears.

Both widgets are driven by a :class:`NotificationCenter` - they observe
its ``notification_added`` and ``unread_count_changed`` signals and
update reactively.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.notifications import (
    Notification,
    NotificationCenter,
    Severity,
)

_SEVERITY_GLYPH = {
    Severity.INFO: "ℹ",
    Severity.WARNING: "⚠",
    Severity.ERROR: "✖",
}


# ---------------------------------------------------------------------------
# Bell button
# ---------------------------------------------------------------------------


class NotificationBellButton(QToolButton):
    """Small status-bar button showing unread notification count.

    Plays no role in *opening* the drawer - that's the parent widget's
    job. We just expose a Qt-style ``clicked`` signal (inherited from
    QToolButton); wire it to whatever dialog/drawer you want to show.
    """

    def __init__(self, center: NotificationCenter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._center = center
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Notifications")
        self.setProperty("hasUnread", False)
        self._refresh_appearance(center.unread_count())

        # Reactive: refresh whenever the unread count changes
        center.unread_count_changed.connect(self._refresh_appearance)

    def unread_count(self) -> int:
        return self._center.unread_count()

    def _refresh_appearance(self, unread: int) -> None:
        # Two distinct glyphs so the state change is obvious at a
        # glance, not just a count number:
        #   🛎  U+1F6CE BELLHOP BELL - static, "idle" read state.
        #   🔔  U+1F514 BELL - most fonts render with motion lines,
        #       i.e. a "ringing" bell for the unread state.
        if unread > 0:
            self.setText(f"🔔 {unread}")
            self.setProperty("hasUnread", True)
        else:
            self.setText("🛎")
            self.setProperty("hasUnread", False)
        # Re-polish so QSS [hasUnread="true"] picks up the new state
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------------------
# Drawer
# ---------------------------------------------------------------------------


class _NotificationRow(QFrame):
    """One notification entry inside the drawer."""

    def __init__(self, n: Notification, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.severity = n.severity
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(8)
        glyph = QLabel(_SEVERITY_GLYPH.get(n.severity, ""))
        header.addWidget(glyph)
        title = QLabel(f"<b>{n.title}</b>")
        header.addWidget(title)
        header.addStretch()
        ts = QLabel(_format_timestamp(n.timestamp))
        ts.setObjectName("MutedLabel")
        small = QFont(ts.font())
        small.setPointSizeF(small.pointSizeF() * 0.85)
        ts.setFont(small)
        header.addWidget(ts)
        layout.addLayout(header)

        if n.message:
            msg = QLabel(n.message)
            msg.setWordWrap(True)
            msg.setObjectName("MutedLabel")
            layout.addWidget(msg)

        if n.source:
            src = QLabel(f"source: {n.source}")
            src.setObjectName("MutedLabel")
            small2 = QFont(src.font())
            small2.setPointSizeF(small2.pointSizeF() * 0.8)
            src.setFont(small2)
            layout.addWidget(src)


def _format_timestamp(ts: datetime) -> str:
    today = datetime.now().date()
    if ts.date() == today:
        return ts.strftime("%H:%M:%S")
    return ts.strftime("%Y-%m-%d %H:%M")


class NotificationDrawer(QWidget):
    """Popup widget listing notifications newest-first."""

    def __init__(self, center: NotificationCenter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._center = center
        self._rows: list[_NotificationRow] = []
        self._empty_text = "No notifications yet."
        self._init_ui()
        center.notification_added.connect(lambda *_args: self.refresh())

    # ------------------------------------------------------------------
    # Public API used by tests + status bar wiring
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        # Tear down existing rows
        for r in self._rows:
            r.setParent(None)
            r.deleteLater()
        self._rows.clear()

        items = list(reversed(self._center.all()))
        self._empty_label.setVisible(not items)

        for n in items:
            row = _NotificationRow(n)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)

    def show_drawer(self) -> None:
        """Show the drawer and mark all current items read.

        Called by the bell-click hookup. Tests call this directly to
        exercise the read-clearing behavior without simulating clicks.
        """
        self._center.mark_all_read()
        self.refresh()
        self.show()

    def row_count(self) -> int:
        return len(self._rows)

    def rows(self) -> list[_NotificationRow]:
        return list(self._rows)

    def row_titles(self) -> list[str]:
        # Each row's first QLabel-with-bold is the title
        out = []
        for r in self._rows:
            for child in r.findChildren(QLabel):
                txt = child.text()
                if txt.startswith("<b>") and txt.endswith("</b>"):
                    out.append(txt[3:-4])
                    break
        return out

    def empty_text(self) -> str:
        return self._empty_text

    def clear_all(self) -> None:
        self._center.clear()
        self.refresh()

    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setMinimumSize(360, 220)
        # Default opening size - user can drag the top-left grip to
        # grow the drawer (bottom-right is anchored to the bell, so
        # growing naturally happens upward + leftward). No hard
        # maximum so long messages get a fair shake.
        self.resize(460, 360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top-left size grip. Placed before the header row so it sits
        # in the top-left corner. Qt.Popup windows have no native
        # resize frame, so a grip is the only way to drag-resize;
        # putting it top-left matches the bottom-right anchor -
        # dragging up/left enlarges the drawer without moving the
        # bottom edge off its pinned spot.
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.setSpacing(0)
        tl_grip = QSizeGrip(self)
        grip_row.addWidget(tl_grip, 0, Qt.AlignmentFlag.AlignTop)
        grip_row.addStretch()
        outer.addLayout(grip_row)

        # Header with title + Clear button
        header = QHBoxLayout()
        header.setContentsMargins(10, 0, 10, 8)
        header_label = QLabel("<b>Notifications</b>")
        header.addWidget(header_label)
        header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_all)
        header.addWidget(clear_btn)
        outer.addLayout(header)

        # Scroll area containing the rows
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        body = QWidget()
        self._list_layout = QVBoxLayout(body)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)

        self._empty_label = QLabel(self._empty_text)
        self._empty_label.setObjectName("MutedLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.addWidget(self._empty_label)

        self._list_layout.addStretch()
        scroll.setWidget(body)

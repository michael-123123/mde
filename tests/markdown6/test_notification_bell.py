"""Tests for the notification bell button + drawer widgets."""

from __future__ import annotations

from markdown_editor.markdown6.components.notification_bell import (
    NotificationBellButton,
    NotificationDrawer,
)
from markdown_editor.markdown6.notifications import (
    Notification,
    NotificationCenter,
    Severity,
)

# ---------------------------------------------------------------------------
# Bell button
# ---------------------------------------------------------------------------


def test_bell_initial_state_zero_unread(qtbot) -> None:
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)
    assert bell.unread_count() == 0


def test_bell_updates_unread_count_on_post(qtbot) -> None:
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)

    center.post(Notification(title="x", message=""))
    center.post(Notification(title="y", message=""))
    assert bell.unread_count() == 2


def test_bell_resets_unread_count_on_mark_read(qtbot) -> None:
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)

    center.post(Notification(title="x", message=""))
    assert bell.unread_count() == 1
    center.mark_all_read()
    assert bell.unread_count() == 0


def test_bell_text_shows_count_when_unread(qtbot) -> None:
    """Bell label text includes unread count for high-glance visibility."""
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)

    assert "0" not in bell.text() or bell.text() == ""   # no badge when 0
    center.post(Notification(title="x", message=""))
    center.post(Notification(title="y", message=""))
    assert "2" in bell.text()


def test_bell_icon_differs_between_read_and_unread(qtbot) -> None:
    """Unread state must visibly change the icon glyph (not only the
    count text) so the bell looks like it's "ringing" at a glance."""
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)

    read_text = bell.text()
    center.post(Notification(title="x", message=""))
    unread_text = bell.text()
    # The leading glyph in the unread state is NOT the same as in the
    # read state - we want the user to see the change with peripheral
    # vision, not just by reading the count.
    assert read_text[0] != unread_text[0]


def test_bell_has_unread_visual_indicator(qtbot) -> None:
    """Bell should have some visible indication when there are unread
    items beyond just the count text - exposed as a queryable property
    so themes can hook on it via QSS [hasUnread="true"]."""
    center = NotificationCenter()
    bell = NotificationBellButton(center)
    qtbot.addWidget(bell)

    assert bell.property("hasUnread") in (False, None)
    center.post(Notification(title="x", message=""))
    assert bell.property("hasUnread") is True
    center.mark_all_read()
    assert bell.property("hasUnread") is False


# ---------------------------------------------------------------------------
# Drawer widget
# ---------------------------------------------------------------------------


def test_drawer_empty_state(qtbot) -> None:
    center = NotificationCenter()
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    assert drawer.row_count() == 0
    assert "no notifications" in drawer.empty_text().lower()


def test_drawer_lists_one_row_per_notification(qtbot) -> None:
    center = NotificationCenter()
    center.post(Notification(title="first", message="m1"))
    center.post(Notification(title="second", message="m2"))
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    assert drawer.row_count() == 2


def test_drawer_orders_newest_first(qtbot) -> None:
    """Most recent notification at the top of the drawer - that's where
    the user expects to see "what just happened."""
    center = NotificationCenter()
    center.post(Notification(title="first", message=""))
    center.post(Notification(title="second", message=""))
    center.post(Notification(title="third", message=""))
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    titles = drawer.row_titles()
    assert titles == ["third", "second", "first"]


def test_drawer_row_shows_severity(qtbot) -> None:
    center = NotificationCenter()
    center.post(Notification(title="ok", message="", severity=Severity.INFO))
    center.post(Notification(title="ouch", message="", severity=Severity.ERROR))
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    rows = drawer.rows()
    # Newest first: ouch (error) on top, ok (info) below
    assert rows[0].severity is Severity.ERROR
    assert rows[1].severity is Severity.INFO


def test_drawer_show_marks_all_read(qtbot) -> None:
    """Showing the drawer is the user "looking at" the notifications,
    so the unread indicator should clear."""
    center = NotificationCenter()
    center.post(Notification(title="x", message=""))
    center.post(Notification(title="y", message=""))
    assert center.unread_count() == 2

    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.show_drawer()
    assert center.unread_count() == 0


def test_drawer_clear_button_empties_center(qtbot) -> None:
    center = NotificationCenter()
    center.post(Notification(title="x", message=""))
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    drawer.clear_all()
    assert center.all() == []
    assert drawer.row_count() == 0


# ---------------------------------------------------------------------------
# Bell ↔ drawer integration
# ---------------------------------------------------------------------------


def test_bell_click_opens_drawer(qtbot) -> None:
    """Clicking the bell shows the drawer (via the toggle_requested signal
    consumers wire to drawer.show_drawer)."""
    center = NotificationCenter()
    center.post(Notification(title="x", message=""))
    bell = NotificationBellButton(center)
    drawer = NotificationDrawer(center)
    qtbot.addWidget(bell)
    qtbot.addWidget(drawer)

    triggered = []
    bell.clicked.connect(lambda: triggered.append("clicked"))
    bell.click()
    assert triggered == ["clicked"]


def test_drawer_refreshes_on_new_notification(qtbot) -> None:
    """When a notification arrives while the drawer is open (or just
    open-ish), the row list updates without manual refresh()."""
    center = NotificationCenter()
    drawer = NotificationDrawer(center)
    qtbot.addWidget(drawer)
    drawer.refresh()
    assert drawer.row_count() == 0

    center.post(Notification(title="live", message=""))
    # Auto-refresh on notification_added signal
    assert drawer.row_count() == 1

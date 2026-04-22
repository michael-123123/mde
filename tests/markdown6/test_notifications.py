"""Tests for the notification center (storage + signals, no UI).

The UI bell + drawer are tested separately; this file covers the
plumbing that drives them: appending notifications, tracking
read/unread state, emitting Qt signals when the unread count changes.
The notification center is the foundation that plugin errors and
future non-plugin notification sources route through.
"""

from __future__ import annotations

from markdown_editor.markdown6.notifications import (
    Notification,
    NotificationCenter,
    Severity,
)

# ---------------------------------------------------------------------------
# Notification dataclass
# ---------------------------------------------------------------------------


def test_notification_minimal_construction() -> None:
    n = Notification(title="Test", message="Body text")
    assert n.title == "Test"
    assert n.message == "Body text"
    assert n.severity is Severity.INFO
    assert n.source == ""
    assert n.read is False
    assert n.timestamp is not None


def test_notification_severities_are_distinct() -> None:
    assert {Severity.INFO, Severity.WARNING, Severity.ERROR} == set(Severity)


# ---------------------------------------------------------------------------
# NotificationCenter — basic add / list / clear
# ---------------------------------------------------------------------------


def test_post_adds_notification() -> None:
    c = NotificationCenter()
    c.post(Notification(title="A", message="aa"))
    assert len(c.all()) == 1
    assert c.all()[0].title == "A"


def test_all_returns_in_arrival_order() -> None:
    c = NotificationCenter()
    c.post(Notification(title="first", message=""))
    c.post(Notification(title="second", message=""))
    c.post(Notification(title="third", message=""))
    titles = [n.title for n in c.all()]
    assert titles == ["first", "second", "third"]


def test_clear_empties_the_center() -> None:
    c = NotificationCenter()
    c.post(Notification(title="x", message=""))
    c.post(Notification(title="y", message=""))
    c.clear()
    assert c.all() == []


# ---------------------------------------------------------------------------
# Unread tracking
# ---------------------------------------------------------------------------


def test_new_notifications_are_unread_by_default() -> None:
    c = NotificationCenter()
    c.post(Notification(title="x", message=""))
    c.post(Notification(title="y", message=""))
    assert c.unread_count() == 2


def test_mark_all_read_zeros_the_count() -> None:
    c = NotificationCenter()
    c.post(Notification(title="x", message=""))
    c.post(Notification(title="y", message=""))
    c.mark_all_read()
    assert c.unread_count() == 0
    # The notifications themselves are flagged read (not deleted)
    assert all(n.read is True for n in c.all())


def test_post_after_mark_read_increments_unread() -> None:
    c = NotificationCenter()
    c.post(Notification(title="x", message=""))
    c.mark_all_read()
    c.post(Notification(title="y", message=""))
    assert c.unread_count() == 1


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_notification_added_signal_fires(qtbot) -> None:
    c = NotificationCenter()
    received = []
    c.notification_added.connect(received.append)

    n = Notification(title="hello", message="world")
    c.post(n)
    assert received == [n]


def test_unread_count_changed_signal_fires_on_post(qtbot) -> None:
    c = NotificationCenter()
    counts = []
    c.unread_count_changed.connect(counts.append)

    c.post(Notification(title="a", message=""))
    c.post(Notification(title="b", message=""))
    assert counts == [1, 2]


def test_unread_count_changed_signal_fires_on_mark_read(qtbot) -> None:
    c = NotificationCenter()
    c.post(Notification(title="a", message=""))
    c.post(Notification(title="b", message=""))

    counts = []
    c.unread_count_changed.connect(counts.append)
    c.mark_all_read()
    assert counts == [0]


def test_mark_all_read_with_no_unread_does_not_emit_signal(qtbot) -> None:
    c = NotificationCenter()
    counts = []
    c.unread_count_changed.connect(counts.append)
    c.mark_all_read()   # nothing was unread
    assert counts == []


def test_clear_emits_unread_count_changed_when_unread_were_present(qtbot) -> None:
    c = NotificationCenter()
    c.post(Notification(title="a", message=""))
    counts = []
    c.unread_count_changed.connect(counts.append)
    c.clear()
    assert counts == [0]


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def test_post_info_helper() -> None:
    c = NotificationCenter()
    c.post_info("hello", "world", source="test")
    [n] = c.all()
    assert n.title == "hello"
    assert n.message == "world"
    assert n.severity is Severity.INFO
    assert n.source == "test"


def test_post_warning_helper() -> None:
    c = NotificationCenter()
    c.post_warning("careful", "foo", source="t")
    [n] = c.all()
    assert n.severity is Severity.WARNING


def test_post_error_helper() -> None:
    c = NotificationCenter()
    c.post_error("oops", "stack trace…", source="plugin:bad")
    [n] = c.all()
    assert n.severity is Severity.ERROR
    assert n.source == "plugin:bad"


# ---------------------------------------------------------------------------
# History cap (avoid unbounded growth)
# ---------------------------------------------------------------------------


def test_notifications_capped_at_history_limit() -> None:
    """Center caps at a configurable max to avoid unbounded growth.
    Oldest notifications are dropped first."""
    c = NotificationCenter(max_history=5)
    for i in range(10):
        c.post(Notification(title=f"n{i}", message=""))
    titles = [n.title for n in c.all()]
    assert titles == ["n5", "n6", "n7", "n8", "n9"]


def test_default_history_cap_is_reasonable() -> None:
    """Default cap should be high enough that normal use never trims,
    but low enough to bound memory."""
    c = NotificationCenter()
    # Don't pin the exact value — just sanity-check it's in the ballpark.
    assert 50 <= c.max_history <= 1000

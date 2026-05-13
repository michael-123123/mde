"""The sidebar must remain resizable via the main QSplitter handle.

Bug: `Sidebar._update_size_constraints` calls `self.setFixedWidth(...)`
to lock the sidebar at its computed width. `setFixedWidth` sets both
`minimumWidth` and `maximumWidth` to the same value — which makes
QSplitter unable to resize the widget when the user drags the handle.

The sidebar should expose a *range* (min = activity-bar width so the
user can collapse to bar-only; max = unbounded) and let the parent
splitter decide the actual width. The internal animation can still
use `setFixedWidth` on the inner `tool_window` for smooth animation,
but that must be released after the animation completes so the user
can drag-resize.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

from markdown_editor.markdown6.app_context import init_app_context
from markdown_editor.markdown6.components.sidebar import Sidebar


def _make_sidebar(qtbot):
    ctx = init_app_context(ephemeral=True)
    s = Sidebar(ctx)
    qtbot.addWidget(s)
    s.show()
    return s


def test_expanded_sidebar_is_not_fixed_width(qtbot):
    """When expanded, the sidebar's width range must be open at the top
    so the parent QSplitter can drag-resize it."""
    sidebar = _make_sidebar(qtbot)
    assert not sidebar.isCollapsed()
    assert sidebar.maximumWidth() > sidebar.minimumWidth(), (
        f"sidebar is locked at fixed width: "
        f"min={sidebar.minimumWidth()} == max={sidebar.maximumWidth()}; "
        f"QSplitter can't resize it"
    )


def test_splitter_can_resize_expanded_sidebar(qtbot):
    """End-to-end: put the sidebar in a QSplitter, ask the splitter to
    give it a different size, and verify the size actually changes.
    With `setFixedWidth` in play, the splitter's request is ignored."""
    sidebar = _make_sidebar(qtbot)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    qtbot.addWidget(splitter)
    splitter.addWidget(sidebar)
    splitter.addWidget(QWidget())
    splitter.resize(1200, 600)
    splitter.show()
    qtbot.wait(50)

    initial = sidebar.width()
    target = initial + 100
    splitter.setSizes([target, 1200 - target])
    qtbot.wait(50)

    assert abs(sidebar.width() - target) < 10, (
        f"splitter.setSizes({target}, ...) was ignored: "
        f"sidebar.width() went from {initial} to {sidebar.width()}, "
        f"expected ~{target}"
    )
    sidebar.setParent(None)


def test_resize_absorbs_into_tool_window_not_into_gap(qtbot):
    """When the user drags the splitter to widen the sidebar, the
    extra width must go INTO the tool window — not become a dead gap
    between the activity bar and the tool window.

    Bug pre-fix: `tool_window` had `setFixedWidth(_tool_width)` left
    over from init; the sidebar's horizontal layout couldn't grow it,
    so the splitter widened the outer Sidebar but the additional
    pixels showed up as an empty column. Releasing tool_window's
    fixed-width after init / at animation-end lets the Expanding
    size-policy soak up the extra width.
    """
    sidebar = _make_sidebar(qtbot)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    qtbot.addWidget(splitter)
    splitter.addWidget(sidebar)
    splitter.addWidget(QWidget())
    splitter.resize(1200, 600)
    splitter.show()
    qtbot.wait(50)

    bar_w = sidebar.activity_bar.width()
    tool_w_before = sidebar.tool_window.width()
    initial_sidebar_w = sidebar.width()
    grow_by = 120
    splitter.setSizes([initial_sidebar_w + grow_by, 1200 - initial_sidebar_w - grow_by])
    qtbot.wait(50)

    new_sidebar_w = sidebar.width()
    new_tool_w = sidebar.tool_window.width()
    # The activity bar stayed the same; the tool window absorbed the growth.
    assert sidebar.activity_bar.width() == bar_w
    assert new_tool_w > tool_w_before, (
        f"tool window did not absorb the resize: "
        f"tool_window width went {tool_w_before} -> {new_tool_w}, "
        f"sidebar width went {initial_sidebar_w} -> {new_sidebar_w}"
    )
    # bar + tool should account for ~ the whole sidebar.
    assert new_tool_w + bar_w >= new_sidebar_w - 5, (
        f"there's a gap: bar={bar_w} + tool={new_tool_w} = "
        f"{bar_w + new_tool_w} but sidebar is {new_sidebar_w}"
    )
    sidebar.setParent(None)

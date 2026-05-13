"""Hover tooltips on sidebar items.

Two separate behaviours, intentionally divergent because the panels
carry different *kinds* of information:

1. ProjectPanel: the displayed text is just the basename, but the
   project-relative path is genuinely useful info (folder context,
   disambiguating same-named files). Tooltip is set unconditionally to
   the relative path - hovering always reveals where the file lives,
   regardless of whether the basename is truncated.

2. Outline / References / Search panels: the displayed text *is* the
   information (heading text, line preview, etc). There's nothing the
   tooltip can add except the part hidden by truncation. Tooltip
   appears only when the item is visually truncated.

The truncation detector is a shared event filter
(``TruncationToolTipFilter``) installed on the view's viewport so all
three panels share one implementation.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

from markdown_editor.markdown6.components.tooltip_helpers import (
    TruncationToolTipFilter,
    _is_index_truncated,
)

# ───────────────────────── ProjectPanel: rel-path tooltip ─────────────────────────


@pytest.mark.timeout(15, method="thread")
def test_project_panel_tooltip_is_relative_path(qtbot, tmp_path):
    """Tooltip on a file in the project is its path relative to the
    project root - regardless of whether the basename is truncated.
    """
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.project_manager import ProjectPanel

    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "plugin-api-versioning.md"
    target.write_text("# x")

    panel = ProjectPanel(get_app_context())
    qtbot.addWidget(panel)
    panel.set_project_path(tmp_path)
    QApplication.processEvents()

    index = panel.file_model.index(str(target))
    tooltip = panel.file_model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert tooltip == "docs/plugin-api-versioning.md", (
        f"expected project-relative path, got {tooltip!r}"
    )


@pytest.mark.timeout(15, method="thread")
def test_project_panel_tooltip_for_root_file(qtbot, tmp_path):
    """A file directly under the project root has just its basename as
    relative path (no leading folder)."""
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.project_manager import ProjectPanel

    target = tmp_path / "README.md"
    target.write_text("# x")

    panel = ProjectPanel(get_app_context())
    qtbot.addWidget(panel)
    panel.set_project_path(tmp_path)
    QApplication.processEvents()

    index = panel.file_model.index(str(target))
    tooltip = panel.file_model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert tooltip == "README.md"


@pytest.mark.timeout(15, method="thread")
def test_project_panel_tooltip_outside_project_falls_back(qtbot, tmp_path):
    """Edge case: index resolves to a path outside the project root
    (shouldn't happen via UI but a hardened model returns an absolute
    path rather than blowing up).
    """
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.project_manager import ProjectPanel

    outside = tmp_path / "outside.md"
    outside.write_text("# x")
    project = tmp_path / "project"
    project.mkdir()

    panel = ProjectPanel(get_app_context())
    qtbot.addWidget(panel)
    panel.set_project_path(project)
    QApplication.processEvents()

    index = panel.file_model.index(str(outside))
    tooltip = panel.file_model.data(index, Qt.ItemDataRole.ToolTipRole)
    # Absolute path is acceptable; key point is no exception and a string.
    assert tooltip == str(outside)


# ───────────────────────── Truncation filter unit tests ─────────────────────────


@pytest.fixture
def narrow_tree(qtbot):
    """QTreeWidget intentionally narrow so long items get elided."""
    tree = QTreeWidget()
    tree.setHeaderHidden(True)
    tree.resize(100, 200)  # narrow
    qtbot.addWidget(tree)
    tree.show()
    qtbot.waitExposed(tree)
    QApplication.processEvents()
    return tree


@pytest.mark.timeout(15, method="thread")
def test_is_truncated_true_for_long_text(narrow_tree):
    """A clearly-too-wide item is truncated and the helper says so."""
    item = QTreeWidgetItem(["this is a very long heading name that won't fit in 100px"])
    narrow_tree.addTopLevelItem(item)
    QApplication.processEvents()
    index = narrow_tree.indexFromItem(item)
    assert _is_index_truncated(narrow_tree, index) is True


@pytest.mark.timeout(15, method="thread")
def test_is_truncated_false_for_short_text(narrow_tree):
    """Short text that fits is not flagged as truncated."""
    item = QTreeWidgetItem(["x"])
    narrow_tree.addTopLevelItem(item)
    QApplication.processEvents()
    index = narrow_tree.indexFromItem(item)
    assert _is_index_truncated(narrow_tree, index) is False


@pytest.mark.timeout(15, method="thread")
def test_is_truncated_false_for_invalid_index(narrow_tree):
    """An invalid QModelIndex never claims truncation - the filter has
    to handle hovers over empty space without raising."""
    from PySide6.QtCore import QModelIndex
    assert _is_index_truncated(narrow_tree, QModelIndex()) is False


# ───────────────────────── Filter event handler tests ─────────────────────────


@pytest.fixture
def filter_with_tree(qtbot, monkeypatch):
    """Tree with the filter installed and ``QToolTip.showText`` /
    ``hideText`` stubbed so tests can assert what the filter did."""
    from markdown_editor.markdown6.components import tooltip_helpers as th

    tree = QTreeWidget()
    tree.setHeaderHidden(True)
    tree.resize(100, 200)
    qtbot.addWidget(tree)
    tree.show()
    qtbot.waitExposed(tree)
    QApplication.processEvents()

    shown: list[str] = []
    hidden: list[bool] = []

    monkeypatch.setattr(
        th.QToolTip,
        "showText",
        lambda pos, text, *args, **kwargs: shown.append(text),
    )
    monkeypatch.setattr(
        th.QToolTip,
        "hideText",
        lambda: hidden.append(True),
    )

    filter_ = TruncationToolTipFilter(tree)
    tree.viewport().installEventFilter(filter_)
    return tree, filter_, shown, hidden


def _send_tooltip(view, item):
    """Synthesize a ToolTip QHelpEvent over `item`'s viewport rect."""
    rect = view.visualRect(view.indexFromItem(item))
    pos = rect.center()
    global_pos = view.viewport().mapToGlobal(pos)
    event = QHelpEvent(QEvent.Type.ToolTip, pos, global_pos)
    QApplication.sendEvent(view.viewport(), event)


@pytest.mark.timeout(15, method="thread")
def test_filter_shows_tooltip_when_item_truncated(filter_with_tree):
    tree, _flt, shown, _hidden = filter_with_tree
    long_text = "this is a very long heading name that won't fit in 100px"
    item = QTreeWidgetItem([long_text])
    tree.addTopLevelItem(item)
    QApplication.processEvents()

    _send_tooltip(tree, item)
    assert shown == [long_text], (
        f"truncated item should show full-text tooltip; got showText={shown}"
    )


@pytest.mark.timeout(15, method="thread")
def test_filter_hides_tooltip_when_item_fits(filter_with_tree):
    tree, _flt, shown, hidden = filter_with_tree
    item = QTreeWidgetItem(["x"])
    tree.addTopLevelItem(item)
    QApplication.processEvents()

    _send_tooltip(tree, item)
    assert shown == [], (
        f"non-truncated item must NOT show tooltip; got showText={shown}"
    )
    assert hidden, "filter should call hideText to dismiss stale tooltips"


@pytest.mark.timeout(15, method="thread")
def test_filter_ignores_empty_viewport_hover(filter_with_tree):
    """Hover below all items - invalid index, no tooltip shown."""
    tree, _flt, shown, _hidden = filter_with_tree
    # No items added; viewport is empty.
    pos = QPoint(50, 150)
    event = QHelpEvent(QEvent.Type.ToolTip, pos, tree.viewport().mapToGlobal(pos))
    QApplication.sendEvent(tree.viewport(), event)
    assert shown == []


# ───────────────────────── Wiring on real panels ─────────────────────────


@pytest.mark.timeout(15, method="thread")
def test_outline_panel_installs_truncation_filter(qtbot):
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.components.outline_panel import OutlinePanel

    panel = OutlinePanel(get_app_context())
    qtbot.addWidget(panel)
    # The viewport must have our filter attached. Probe via attribute -
    # the panel stashes it for lifetime management.
    assert hasattr(panel, "_tooltip_filter")
    assert isinstance(panel._tooltip_filter, TruncationToolTipFilter)


@pytest.mark.timeout(15, method="thread")
def test_references_panel_installs_truncation_filter(qtbot):
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.components.references_panel import (
        ReferencesPanel,
    )

    panel = ReferencesPanel(get_app_context())
    qtbot.addWidget(panel)
    assert hasattr(panel, "_tooltip_filter")
    assert isinstance(panel._tooltip_filter, TruncationToolTipFilter)


@pytest.mark.timeout(15, method="thread")
def test_search_panel_installs_truncation_filter(qtbot):
    from markdown_editor.markdown6.app_context import get_app_context
    from markdown_editor.markdown6.components.search_panel import SearchPanel

    panel = SearchPanel(get_app_context())
    qtbot.addWidget(panel)
    assert hasattr(panel, "_tooltip_filter")
    assert isinstance(panel._tooltip_filter, TruncationToolTipFilter)

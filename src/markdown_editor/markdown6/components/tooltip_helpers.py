"""Hover-tooltip helpers for sidebar item views.

The sidebar trees (Outline, References, Search) display text that *is*
the information - heading text, line preview, etc. A tooltip duplicating
that text on every hover would be noise. We only want it when the text
is visually truncated, to reveal the part the user can't see.

``TruncationToolTipFilter`` is an event filter installed on a view's
``viewport()``. On a ``QEvent.ToolTip`` it computes whether the item
under the cursor is elided; if so, it shows the full ``DisplayRole``
text in a tooltip; otherwise it hides any active tooltip and returns
True so Qt doesn't fall back to its own (default-empty) tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QToolTip

# How much horizontal space an item icon typically consumes, in pixels.
# Used as a flat deduction when the index has a DecorationRole. Slightly
# generous so we err on showing tooltips when the text is *almost*
# clipped - a redundant tooltip is less bad than missing one.
_ICON_ALLOWANCE_PX = 20


def _is_index_truncated(view: QAbstractItemView, index: QModelIndex) -> bool:
    """True iff the displayed ``DisplayRole`` text for ``index`` would be
    elided when rendered in ``view``.

    Approximates by comparing the natural text width (font metrics) to
    the available horizontal space inside the visual rect, deducting a
    flat allowance for the icon when an icon is present. Not exact (no
    style/padding awareness) but reliable enough that obvious overflow
    is caught and clearly-fitting text is not flagged.
    """
    if not index.isValid():
        return False
    text = index.data(Qt.ItemDataRole.DisplayRole)
    if not text:
        return False
    rect = view.visualRect(index)
    if rect.width() <= 0:
        return False
    fm = view.fontMetrics()
    available = rect.width()
    if index.data(Qt.ItemDataRole.DecorationRole) is not None:
        available -= _ICON_ALLOWANCE_PX
    return fm.horizontalAdvance(str(text)) > available


class TruncationToolTipFilter(QObject):
    """Show a hover tooltip on a view's item only when the text is
    truncated. Install via ``view.viewport().installEventFilter(...)``.

    The filter is parented to ``view`` so Qt cleans it up when the view
    is destroyed.
    """

    def __init__(self, view: QAbstractItemView):
        super().__init__(view)
        self._view = view

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.ToolTip:
            return False
        index = self._view.indexAt(event.pos())
        if _is_index_truncated(self._view, index):
            text = str(index.data(Qt.ItemDataRole.DisplayRole))
            QToolTip.showText(event.globalPos(), text, self._view.viewport())
        else:
            QToolTip.hideText()
        # Consume the event so Qt's default tooltip handling (which
        # would show the model's empty ToolTipRole) doesn't run on top.
        return True

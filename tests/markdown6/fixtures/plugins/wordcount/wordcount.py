"""Word count sidebar panel — second bundled reference plugin.

Demonstrates three Phase 2 extension points working together:

* :func:`register_panel` — the sidebar panel widget.
* ``@on_content_changed`` / ``@on_file_opened`` — keep the panel in
  sync as the user edits or switches between documents.
* ``ctx.plugin_settings("wordcount")`` — persist the user's target
  word count across editor sessions.

The plugin is intentionally simple but real-world useful: writers
often want to track progress against a daily/article word target.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.plugins import (
    get_active_document,
    on_content_changed,
    on_file_opened,
    plugin_settings,
    register_panel,
)

_DEFAULT_TARGET = 500
_PANEL: "WordCountPanel | None" = None


def _word_count(text: str) -> int:
    """Trivial whitespace-split word count. Good enough for the demo."""
    return len(text.split())


class WordCountPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        settings = plugin_settings("wordcount")
        self._target: int = int(settings.get("target", _DEFAULT_TARGET))
        self._last_count: int = 0
        self._build_ui()

    # --- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.count_label = QLabel(self._format_count_text(0))
        layout.addWidget(self.count_label)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target:"))
        self._target_spin = QSpinBox()
        self._target_spin.setRange(1, 999_999)
        self._target_spin.setValue(self._target)
        self._target_spin.valueChanged.connect(self._on_target_changed)
        target_row.addWidget(self._target_spin)
        layout.addLayout(target_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        layout.addStretch()

    # --- Updates ------------------------------------------------------------

    def update_count(self, count: int) -> None:
        self._last_count = count
        self.count_label.setText(self._format_count_text(count))
        if self._target > 0:
            pct = min(100, int(round(count * 100 / self._target)))
        else:
            pct = 0
        self._progress.setValue(pct)

    def _format_count_text(self, count: int) -> str:
        return f"Words: {count} / {self._target}"

    # --- Settings persistence ----------------------------------------------

    def _on_target_changed(self, new_target: int) -> None:
        self._target = new_target
        plugin_settings("wordcount")["target"] = new_target
        self.update_count(self._last_count)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@register_panel(id="wordcount", label="Word Count", icon="📊")
def make_panel() -> WordCountPanel:
    global _PANEL
    _PANEL = WordCountPanel()
    return _PANEL


def _refresh_panel_from_active_document() -> None:
    """Pull the current document's text and update the panel.

    Called from both signal handlers below. Tolerates missing panel
    (signal fired before panel was constructed) and missing document
    (no active tab) — both are no-ops.
    """
    if _PANEL is None:
        return
    doc = get_active_document()
    if doc is None:
        return
    _PANEL.update_count(_word_count(doc.text))


@on_content_changed
def _on_change(_doc) -> None:
    _refresh_panel_from_active_document()


@on_file_opened
def _on_open(_doc) -> None:
    _refresh_panel_from_active_document()

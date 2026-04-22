"""Document tab component — container for a single open document.

Holds an EnhancedEditor, a preview pane (QWebEngineView with QTextBrowser
fallback), find/replace bar, and external change bar. Tracks file_path
and unsaved_changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from markdown_editor.markdown6.components.external_change_bar import (
    ExternalChangeBar,
)
from markdown_editor.markdown6.components.find_replace_bar import (
    FindReplaceBar,
)
from markdown_editor.markdown6.diagram_helpers import _render_diagram
from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
from markdown_editor.markdown6.logger import getLogger
from markdown_editor.markdown6.theme import StyleSheets, get_theme

if TYPE_CHECKING:
    from markdown_editor.markdown6.markdown_editor import MarkdownEditor

logger = getLogger(__name__)

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEnginePage = None  # type: ignore


def _export_diagram_to_file(kind: str, source: str, dark_mode: bool) -> str | None:
    """Render diagram source to an SVG temp file. Returns the file path or None."""
    import json
    import subprocess

    from markdown_editor.markdown6.temp_files import (
        create_temp_dir,
        create_temp_file,
    )

    if kind == 'mermaid':
        from markdown_editor.markdown6.tool_paths import get_mmdc_path
        mmdc = get_mmdc_path()
        if not mmdc:
            return None
        work_dir = create_temp_dir(prefix='mmdc_')
        input_path = work_dir / 'input.mmd'
        output_path = work_dir / 'output.svg'
        config_path = work_dir / 'config.json'
        input_path.write_text(source, encoding='utf-8')
        config_path.write_text(json.dumps({
            'htmlLabels': False,
            'flowchart': {'htmlLabels': False},
        }))
        theme = 'dark' if dark_mode else 'default'
        subprocess.run(
            [mmdc, '-i', str(input_path), '-o', str(output_path),
             '-t', theme, '-b', 'transparent', '--quiet',
             '-c', str(config_path)],
            capture_output=True, timeout=15,
        )
        if output_path.exists():
            svg_path = create_temp_file(suffix='.svg', prefix='diagram_',
                                        content=output_path.read_bytes())
            return str(svg_path)
        return None
    else:
        from markdown_editor.markdown6 import graphviz_service
        svg, error = graphviz_service.render_dot(source, dark_mode)
        if error:
            return None
        svg_path = create_temp_file(suffix='.svg', prefix='diagram_', content=svg)
        return str(svg_path)


def convert_lists_for_qtextbrowser(html: str) -> str:
    """Convert HTML lists to div/p elements that QTextBrowser renders correctly.

    QTextBrowser has poor support for <ul>/<ol>/<li> elements. This function
    converts them to <div> blocks with bullet/number characters.
    """
    def replace_ul(match):
        content = match.group(1)
        items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
        result = '<div style="margin: 8px 0;">'
        for item in items:
            result += f'<p style="margin: 2px 0; margin-left: 20px;">• {item.strip()}</p>'
        result += '</div>'
        return result

    def replace_ol(match):
        content = match.group(1)
        items = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL | re.IGNORECASE)
        result = '<div style="margin: 8px 0;">'
        for i, item in enumerate(items, 1):
            result += f'<p style="margin: 2px 0; margin-left: 20px;">{i}. {item.strip()}</p>'
        result += '</div>'
        return result

    html = re.sub(r'<ul[^>]*>(.*?)</ul>', replace_ul, html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ol[^>]*>(.*?)</ol>', replace_ol, html, flags=re.DOTALL | re.IGNORECASE)

    return html


# Custom WebEnginePage to intercept link clicks
if HAS_WEBENGINE:
    class LinkInterceptPage(QWebEnginePage):
        """Custom QWebEnginePage that intercepts link clicks."""

        link_clicked = Signal(QUrl)
        open_image_requested = Signal(QUrl)

        def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
            """Intercept navigation requests to handle link clicks."""
            if url.scheme() == 'open-image':
                self.open_image_requested.emit(url)
                return False

            if is_main_frame and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                self.link_clicked.emit(url)
                return False

            return True


class _PreviewWheelFilter(QObject):
    """Event filter that forwards wheel events from WebEngine's internal
    rendering widget to the editor, so scrolling the preview scrolls the
    editor (which then syncs the preview via scrollToSourceLine).
    """

    def __init__(self, tab: DocumentTab):
        super().__init__(tab)
        self._tab = tab

    def eventFilter(self, obj, event):
        if (
            event.type() == event.Type.Wheel
            and self._tab._sync_scrolling
            and self._tab.editor.isVisible()
        ):
            QApplication.sendEvent(self._tab.editor.viewport(), event)
            return True
        return False


class _PreviewKeyFilter(QObject):
    """Event filter that translates vertical-scroll keypresses on the
    preview into scrollbar moves on the **editor**, so keyboard scrolling
    in the preview keeps both panes aligned via the existing editor →
    preview sync pipeline.

    Keys handled (event consumed):

    - ``Down`` / ``Up``           — single-step scroll
    - ``PageDown`` / ``PageUp``   — page-step scroll
    - ``Space`` / ``Shift+Space`` — page-step scroll (WebEngine's native
      alias for PageDown/PageUp)
    - ``Home`` / ``End``          — jump to top / bottom

    All other keys pass through so the preview retains normal keyboard
    behavior (Left/Right, Tab, character input, shortcuts).

    Gate: the filter is a no-op when ``_sync_scrolling`` is off (user
    disabled editor↔preview sync in settings) or the editor isn't
    visible (preview-only layout — then native preview scrolling is the
    right thing). Same gating as ``_PreviewWheelFilter``.
    """

    def __init__(self, tab: DocumentTab):
        super().__init__(tab)
        self._tab = tab

    def eventFilter(self, obj, event):
        if event.type() != event.Type.KeyPress:
            return False
        if not self._tab._sync_scrolling:
            return False
        if not self._tab.editor.isVisible():
            return False

        vbar = self._tab.editor.verticalScrollBar()
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Down:
            vbar.setValue(vbar.value() + vbar.singleStep())
        elif key == Qt.Key.Key_Up:
            vbar.setValue(vbar.value() - vbar.singleStep())
        elif key == Qt.Key.Key_PageDown:
            vbar.setValue(vbar.value() + vbar.pageStep())
        elif key == Qt.Key.Key_PageUp:
            vbar.setValue(vbar.value() - vbar.pageStep())
        elif key == Qt.Key.Key_Space:
            delta = -vbar.pageStep() if mods & Qt.KeyboardModifier.ShiftModifier else vbar.pageStep()
            vbar.setValue(vbar.value() + delta)
        elif key == Qt.Key.Key_Home:
            vbar.setValue(0)
        elif key == Qt.Key.Key_End:
            vbar.setValue(vbar.maximum())
        else:
            return False

        return True


class DocumentTab(QWidget):
    """A single document tab with editor and preview panes."""

    link_clicked = Signal(QUrl)  # Emitted when a link is clicked in the preview

    def __init__(self, parent: MarkdownEditor):
        super().__init__()
        self.main_window = parent
        self.ctx = parent.ctx
        self.file_path: Path | None = None
        self._sync_scrolling = True
        self._pending_scroll_line: int | None = None
        self._preview_needs_full_reload = True
        self._preview_zoom_factor = 1.0
        self._pending_render_generation = 0  # bumped on each render to discard stale results

        self._init_ui()
        self._init_timer()
        # Baseline the document as unmodified before wiring the
        # modificationChanged signal so the initial (empty / just-loaded)
        # state is the "clean" reference point.
        self.editor.document().setModified(False)
        self._connect_signals()

    def _init_ui(self):
        """Set up the tab's user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter with editor and preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Editor container
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self.editor = EnhancedEditor(ctx=self.ctx)
        self.editor.setAcceptDrops(True)
        self.editor.setAccessibleName("Markdown Editor")

        editor_layout.addWidget(self.editor)

        # Preview pane - use QWebEngineView if available for better CSS support
        if HAS_WEBENGINE:
            from PySide6.QtWebEngineCore import QWebEngineSettings
            self.preview = QWebEngineView()
            # Custom page to intercept link clicks. Parented to self (not
            # the view) so Qt destroys the page before the view — avoiding
            # "Release of profile requested but WebEnginePage still not
            # deleted" warnings.
            self._custom_page = LinkInterceptPage(self)
            self._custom_page.link_clicked.connect(self._on_link_clicked)
            self._custom_page.open_image_requested.connect(self._on_open_image)
            self._custom_page.linkHovered.connect(self._on_link_hovered)
            self.preview.setPage(self._custom_page)
            # Allow loading CDN resources (KaTeX, Mermaid) from file:// pages
            self._custom_page.settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            # Allow the code-block copy buttons to use navigator.clipboard
            self._custom_page.settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
            )
            self._use_webengine = True
        else:
            self.preview = QTextBrowser()
            # Don't auto-open external links, handle them manually
            self.preview.setOpenExternalLinks(False)
            self.preview.anchorClicked.connect(self._on_link_clicked)
            # Enable mouse tracking for link tooltips
            self.preview.setMouseTracking(True)
            self.preview.mouseMoveEvent = self._preview_mouse_move
            self._use_webengine = False
        self._apply_preview_style()

        self.splitter.addWidget(editor_container)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([600, 600])

        # External change notification bar spans both panes (above splitter)
        self.external_change_bar = ExternalChangeBar(self.ctx, self)
        self.external_change_bar.reload_requested.connect(self.reload_file)

        # Find/Replace bar spans both panes (below splitter)
        self.find_replace_bar = FindReplaceBar(
            self.editor, self.preview, self._use_webengine, self
        )

        layout.addWidget(self.external_change_bar)
        layout.addWidget(self.splitter)
        layout.addWidget(self.find_replace_bar)

        # Apply settings
        self._apply_settings()

    def _apply_preview_style(self):
        """Apply styling to the preview pane."""
        theme = self.ctx.get("view.theme", "light")

        colors = get_theme(theme == "dark")

        # QWebEngineView - set page background color
        if self._use_webengine:
            from PySide6.QtGui import QColor
            self.preview.page().setBackgroundColor(QColor(colors.editor_bg))
            return

        # QTextBrowser widget styling
        self.preview.setStyleSheet(StyleSheets.text_browser(colors))

    def _apply_settings(self):
        """Apply current settings."""
        self.preview.setVisible(self.ctx.get("view.show_preview", True))
        self._sync_scrolling = self.ctx.get("view.sync_scrolling", True)

    def _init_timer(self):
        """Initialize the render debounce timer."""
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render_markdown)
        # A destroyed tab must not leave a live render_timer behind: if it
        # does, the timer fires during a later test's pytest-qt
        # processEvents window — after pytest's LogCaptureHandler has been
        # closed for the previous test — and render_markdown's logger
        # call writes to a closed StringIO.
        self.destroyed.connect(self.render_timer.stop)

    def _connect_signals(self):
        """Connect signals."""
        # ``textChanged`` is one-way (fires on every buffer mutation,
        # including undo/redo) — we keep it only for side effects that
        # should run on any content change: preview re-render and
        # outline update scheduling.
        self.editor.textChanged.connect(self._on_text_changed)
        # Dirty tracking uses ``modificationChanged`` instead because
        # it is bidirectional: emits ``True`` when the document leaves
        # its last ``setModified(False)`` baseline, and ``False`` when
        # it returns to that baseline (e.g. user undoes every edit).
        # Without this, the dirty flag would ratchet to ``True`` on
        # the first keystroke and never turn off until an explicit
        # save or reload — even if the buffer is byte-identical to
        # the saved state.
        self.editor.document().modificationChanged.connect(
            self._on_modification_changed
        )
        self.editor.file_externally_modified.connect(self._on_file_externally_modified)
        self.ctx.settings_changed.connect(self._on_setting_changed)

        # Sync scrolling — editor is the source of truth.
        # For WebEngine, wheel and vertical-scroll key events on the
        # preview's internal rendering widget are forwarded to the editor
        # so scrolling either pane (via mouse or keyboard) keeps them in
        # sync.
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scroll)
        if self._use_webengine:
            self._wheel_filter = _PreviewWheelFilter(self)
            self._key_filter = _PreviewKeyFilter(self)
            self._preview_filters_installed = False
            self._custom_page.loadFinished.connect(self._install_preview_event_filters)
            self._custom_page.loadFinished.connect(
                lambda ok: logger.info(f"[DIAG] loadFinished ok={ok}")
            )
        else:
            self.preview.viewport().installEventFilter(_PreviewWheelFilter(self))
            self.preview.viewport().installEventFilter(_PreviewKeyFilter(self))

    def _on_link_clicked(self, url: QUrl):
        """Handle link clicks in the preview, forwarding to the main window."""
        self.link_clicked.emit(url)

    def _on_open_image(self, url: QUrl):
        """Handle Ctrl+click on images/diagrams in the preview."""
        from urllib.parse import parse_qs, unquote

        host = url.host()
        if host == 'diagram':
            # Rendered diagram — get source from JS, re-render with native text
            kind = parse_qs(url.query()).get('kind', ['mermaid'])[0]
            self.preview.page().runJavaScript(
                'window._pendingDiagramSource || ""',
                lambda source, _kind=kind: self._export_diagram(source, _kind),
            )
        elif host == 'img':
            # Linked image — src is in query param
            src = unquote(url.query().replace('src=', '', 1)) if url.query().startswith('src=') else ''
            if not src:
                return
            img_url = QUrl(src)
            if img_url.isLocalFile():
                QDesktopServices.openUrl(img_url)
            elif img_url.scheme() in ('http', 'https'):
                QDesktopServices.openUrl(img_url)
            else:
                # Relative path — resolve against document dir
                if self.file_path:
                    resolved = self.file_path.parent / src
                    if resolved.exists():
                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))

    def _export_diagram(self, source: str, kind: str):
        """Re-render diagram source to SVG with native text and open it."""
        if not source:
            return
        import html as html_mod
        source = html_mod.unescape(source)
        dark_mode = self.ctx.get("view.theme") == "dark"

        # Override cursor app-wide — survives Ctrl keyup and CSS changes
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        future = self.main_window._diagram_executor.submit(
            _export_diagram_to_file, kind, source, dark_mode,
        )

        def poll():
            if future.done():
                try:
                    svg_path = future.result()
                except Exception:
                    logger.exception("Diagram export failed")
                    QApplication.restoreOverrideCursor()
                    return
                if svg_path:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(svg_path))
                QApplication.restoreOverrideCursor()
            else:
                QTimer.singleShot(100, poll)

        QTimer.singleShot(100, poll)

    def _on_link_hovered(self, url: str):
        """Handle link hover in the preview, showing URL as tooltip."""
        if url:
            self.preview.setToolTip(url)
        else:
            self.preview.setToolTip("")

    def _preview_mouse_move(self, event):
        """Handle mouse move in QTextBrowser to show link tooltips."""
        anchor = self.preview.anchorAt(event.pos())
        if anchor:
            self.preview.setToolTip(anchor)
        else:
            self.preview.setToolTip("")
        # Call the parent class method
        QTextBrowser.mouseMoveEvent(self.preview, event)

    def _on_setting_changed(self, key: str, value):
        """Handle setting changes."""
        if key == "view.show_preview":
            self.preview.setVisible(value)
        elif key == "view.sync_scrolling":
            self._sync_scrolling = value
        elif key == "view.theme":
            self._apply_preview_style()
            # Re-render preview with new theme (full reload needed)
            self._preview_needs_full_reload = True
            self.render_markdown()
        elif key == "view.preview_font_size":
            # Re-render preview with new font size (full reload needed)
            self._preview_needs_full_reload = True
            self.render_markdown()
        elif key == "editor.scroll_past_end":
            self._preview_needs_full_reload = True
            self.render_markdown()
        elif key.startswith("preview."):
            self._preview_needs_full_reload = True
            self.render_markdown()

    def preview_has_focus(self) -> bool:
        """Return True if the preview pane (or a child of it) has keyboard focus."""
        app = QApplication.instance()
        focus = app.focusWidget() if app else None
        if focus is None:
            return False
        return focus is self.preview or self.preview.isAncestorOf(focus)

    def preview_copy(self):
        """Copy selected text from the preview pane."""
        if self._use_webengine:
            self.preview.page().triggerAction(
                QWebEnginePage.WebAction.Copy
            )
        else:
            self.preview.copy()

    def preview_select_all(self):
        """Select all text in the preview pane."""
        if self._use_webengine:
            self.preview.page().triggerAction(
                QWebEnginePage.WebAction.SelectAll
            )
        else:
            self.preview.selectAll()

    def preview_zoom_in(self):
        """Zoom in the preview pane (text + images + diagrams)."""
        if self._preview_zoom_factor < 5.0:
            self._preview_zoom_factor += 0.1
            self._apply_preview_zoom()

    def preview_zoom_out(self):
        """Zoom out the preview pane (text + images + diagrams)."""
        if self._preview_zoom_factor > 0.3:
            self._preview_zoom_factor -= 0.1
            self._apply_preview_zoom()

    def preview_zoom_reset(self):
        """Reset preview zoom to 1.0."""
        self._preview_zoom_factor = 1.0
        self._apply_preview_zoom()

    def _apply_preview_zoom(self):
        """Apply the current zoom factor to the preview.

        At 1x zoom, diagram SVGs use max-width:100% to fit the container.
        When zoomed (body.zoomed), CSS removes that constraint so
        setZoomFactor can scale them.
        """
        if self._use_webengine:
            self.preview.setZoomFactor(self._preview_zoom_factor)
            zoomed = "true" if abs(self._preview_zoom_factor - 1.0) > 0.01 else "false"
            self.preview.page().runJavaScript(
                f"document.body.classList.toggle('zoomed', {zoomed});"
            )

    def _install_preview_event_filters(self):
        """Install wheel + key event filters on WebEngine's internal widgets.

        WebEngine keeps its actual rendering surface as a native child
        widget that only exists after ``loadFinished`` fires, so the
        filters have to be installed at that point rather than at
        construction time.
        """
        if self._preview_filters_installed:
            return
        children = self.preview.findChildren(QWidget)
        for child in children:
            child.installEventFilter(self._wheel_filter)
            child.installEventFilter(self._key_filter)
        self._preview_filters_installed = bool(children)

    def _on_text_changed(self):
        """Handle text changes in the editor."""
        self.render_timer.start(300)
        # Schedule debounced outline panel update
        if hasattr(self.main_window, '_schedule_outline_update'):
            self.main_window._schedule_outline_update()

    @property
    def unsaved_changes(self) -> bool:
        """Whether the document has unsaved changes.

        Derived read-only view of ``self.editor.document().isModified()``
        — the single source of truth. Direct assignment is deliberately
        not supported; callers that want to reset the modification
        baseline (file load, save, etc.) call
        ``self.editor.document().setModified(False)`` instead, which
        propagates here automatically via the ``modificationChanged``
        signal.
        """
        return self.editor.document().isModified()

    def _on_modification_changed(self, modified: bool):
        """Refresh the tab title and window title when the document's
        modification state flips.

        ``unsaved_changes`` itself is a derived property reading
        ``document().isModified()`` — no local mirror to update here,
        only the UI side effects that used to live in this handler.
        """
        self.main_window.update_tab_title(self)
        self.main_window.update_window_title()

    def _on_file_externally_modified(self):
        """Handle external file modification with non-modal notification."""
        name = self.file_path.name if self.file_path else "File"
        self.external_change_bar.show_change(name)

    def _on_editor_scroll(self):
        """Handle editor scroll for sync scrolling."""
        if not self._sync_scrolling:
            return
        if self._use_webengine:
            line = self.editor.get_first_visible_line()
            if self.preview.isVisible():
                self._pending_scroll_line = None
                js = f"if (typeof scrollToSourceLine === 'function') scrollToSourceLine({line});"
                self.preview.page().runJavaScript(js)
            else:
                self._pending_scroll_line = line
        else:
            if self.preview.isVisible():
                ratio = self.editor.get_scroll_ratio()
                preview_scrollbar = self.preview.verticalScrollBar()
                preview_scrollbar.setValue(int(ratio * preview_scrollbar.maximum()))

    def render_markdown(self):
        """Convert markdown to HTML and display in preview pane.

        Diagrams whose SVGs are already cached are inlined immediately.
        Uncached diagrams get a placeholder that is filled asynchronously
        by _render_pending_diagrams(), keeping the preview responsive.
        """
        import json

        # Cancel any pending debounced render — we're rendering now.
        self.render_timer.stop()

        text = self.editor.toPlainText()
        total_lines = text.count('\n') + 1
        self.main_window.md.reset()
        self.main_window.md._pending_diagrams = []

        # Set diagram config before conversion
        dark_mode = self.ctx.get("view.theme") == "dark"
        self.main_window.md.graphviz_dark_mode = dark_mode
        self.main_window.md.graphviz_base_path = str(self.file_path.parent) if self.file_path else None
        self.main_window.md.mermaid_dark_mode = dark_mode
        self.main_window.md.logseq_mode = self.ctx.get("view.logseq_mode", False)

        html_content = self.main_window.md.convert(text)
        pending = self.main_window.md._pending_diagrams

        # For QWebEngineView: use incremental JS update to preserve scroll position
        if self._use_webengine and not self._preview_needs_full_reload:
            logger.info(f"[DIAG] incremental pending={len(pending)}")
            escaped = json.dumps(html_content)
            js = f"document.getElementById('md-content').innerHTML = {escaped};"
            js += f"document.body.dataset.totalLines = '{total_lines}';"
            js += """
            if (typeof renderMathInElement !== 'undefined') {
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '$', right: '$', display: false}
                    ]
                });
            }
            if (typeof mermaid !== 'undefined') {
                mermaid.init(undefined, document.querySelectorAll('.mermaid:not([data-processed])'));
            }
            """
            self.preview.page().runJavaScript(js)
            # Re-apply zoom max-width toggle for new SVGs
            self._apply_preview_zoom()
            self._render_pending_diagrams(pending)
            return

        # Convert lists for QTextBrowser since it doesn't render <ul>/<li> properly
        if not self._use_webengine:
            html_content = convert_lists_for_qtextbrowser(html_content)
        full_html = self.main_window.get_html_template(
            html_content, for_qtextbrowser=not self._use_webengine,
            total_lines=total_lines,
        )
        # Set base URL for relative link resolution
        if self.file_path:
            base_url = QUrl.fromLocalFile(str(self.file_path.parent) + "/")
        else:
            base_url = QUrl()

        if not self._use_webengine:
            # QTextBrowser: save/restore scroll position around setHtml
            scrollbar = self.preview.verticalScrollBar()
            scroll_pos = scrollbar.value()
            self.preview.setHtml(full_html, base_url)
            scrollbar.setValue(scroll_pos)
        else:
            # Full reload for QWebEngineView (initial load or theme/font change)
            logger.info(f"[DIAG] full-reload pending={len(pending)}")
            self.preview.setHtml(full_html, base_url)
            self._preview_needs_full_reload = False
            # Re-apply zoom factor after setHtml
            self._apply_preview_zoom()
            self._render_pending_diagrams(pending)

    def _render_pending_diagrams(self, pending: list):
        """Dispatch background workers for uncached diagram placeholders.

        Uses a ThreadPoolExecutor to render diagrams off the main thread.
        A QTimer polls for completed futures and injects results via JS.
        A generation counter discards results from stale renders.
        """
        if not pending or not self._use_webengine:
            return
        self._pending_render_generation += 1
        gen = self._pending_render_generation
        futures = []
        for idx, (kind, source, dark_mode) in enumerate(pending):
            future = self.main_window._diagram_executor.submit(_render_diagram, kind, source, dark_mode)
            futures.append((idx, future))
        self._poll_diagram_futures(futures, gen)

    def _poll_diagram_futures(self, futures: list, generation: int):
        """Poll pending futures and inject completed diagrams into preview."""
        import json
        if generation != self._pending_render_generation:
            return
        remaining = []
        for idx, future in futures:
            if future.done():
                try:
                    svg_html, css_class = future.result()
                except Exception as e:
                    logger.exception("Diagram render failed")
                    import html
                    svg_html = f'<div class="diagram-loading">Error: {html.escape(str(e))}</div>'
                    css_class = 'mermaid-diagram'
                escaped_svg = json.dumps(svg_html)
                js = f"""
                (function() {{
                    var el = document.getElementById('diagram-pending-{idx}');
                    if (!el) return 'missing';
                    el.innerHTML = {escaped_svg};
                    el.classList.remove('diagram-loading');
                    el.classList.add('{css_class}');
                    return 'ok';
                }})();
                """
                def _cb(result, _idx=idx, _len=len(svg_html)):
                    logger.info(f"[DIAG] inject idx={_idx} result={result!r} svg_len={_len}")
                self.preview.page().runJavaScript(js, _cb)
                self._apply_preview_zoom()
            else:
                remaining.append((idx, future))
        if remaining:
            QTimer.singleShot(
                100, lambda: self._poll_diagram_futures(remaining, generation)
            )

    def reload_file(self):
        """Reload the file from disk."""
        if self.file_path and self.file_path.exists():
            content = self.file_path.read_text(encoding="utf-8")
            self.editor.setPlainText(content)
            # Reset the modification baseline to the just-loaded state;
            # modificationChanged(False) will propagate to unsaved_changes.
            self.editor.document().setModified(False)
            self.main_window.update_tab_title(self)

    def get_tab_title(self) -> str:
        """Return the title for this tab."""
        if self.file_path:
            name = self.file_path.name
        else:
            name = "Untitled"
        if self.unsaved_changes:
            name = f"*{name}"
        return name

    def show_find(self):
        """Show the find bar."""
        self.find_replace_bar.show_find()

    def show_replace(self):
        """Show the find and replace bar."""
        self.find_replace_bar.show_replace()

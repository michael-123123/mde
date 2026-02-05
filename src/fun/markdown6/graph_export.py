"""Document graph export functionality.

Generates a Graphviz graph from document links in a project.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEnginePage = None  # type: ignore

from fun.markdown6.settings import get_settings
from fun.markdown6.theme import get_theme, StyleSheets
from fun.markdown6 import graphviz_service


# Link detection patterns
WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
MD_LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+\.md(?:own)?)\)', re.IGNORECASE)


class VerticalTab(QWidget):
    """A vertical tab widget with rotated text that can be clicked to expand/collapse panels."""

    clicked = Signal()

    def __init__(self, text: str, width: int = 28, arrow_direction: str = "left", parent=None):
        """
        Args:
            text: The label text to display vertically
            width: Width of the tab
            arrow_direction: "left" or "right" - which way arrow points when expanded
        """
        super().__init__(parent)
        self._text = text
        self._hovered = False
        self._collapsed = False
        self._arrow_direction = arrow_direction  # "left" for left panel, "right" for right panel
        self.setFixedWidth(width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def setText(self, text: str):
        self._text = text
        self.update()

    def setCollapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw background
        if self._hovered:
            p.fillRect(self.rect(), QColor(100, 100, 100, 50))
        else:
            p.fillRect(self.rect(), QColor(80, 80, 80, 30))

        # Draw border line on the content side
        p.setPen(QPen(QColor(120, 120, 120), 1))
        if self._arrow_direction == "left":
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        else:
            p.drawLine(0, 0, 0, self.height())

        # Colors
        text_color = QColor(180, 180, 180) if self._hovered else QColor(140, 140, 140)
        p.setPen(text_color)

        fm = QFontMetrics(p.font())
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()

        # Arrow character based on state and direction
        # Left panel: expanded = ◀, collapsed = ▶
        # Right panel: expanded = ▶, collapsed = ◀
        if self._arrow_direction == "left":
            arrow = "▶" if self._collapsed else "◀"
        else:
            arrow = "◀" if self._collapsed else "▶"

        arrow_w = fm.horizontalAdvance(arrow)

        # Total height needed: arrow + gap + text (when rotated, text_w becomes height)
        gap = 8
        total_h = arrow_w + gap + text_w

        # Center vertically in widget
        start_y = (self.height() - total_h) / 2

        # Draw arrow (not rotated, centered horizontally)
        arrow_x = (self.width() - arrow_w) / 2
        arrow_y = start_y + fm.ascent()
        p.drawText(int(arrow_x), int(arrow_y), arrow)

        # Draw rotated text below arrow
        p.save()
        text_center_y = start_y + arrow_w + gap + text_w / 2
        p.translate(self.width() / 2, text_center_y)
        p.rotate(-90)

        # Draw centered horizontally around x=0 in rotated coords
        x = -text_w / 2
        y = fm.ascent() / 2
        p.drawText(int(x), int(y), self._text)
        p.restore()


class GraphExportDialog(QDialog):
    """Dialog for exporting document graph."""

    file_clicked = Signal(Path)

    def __init__(self, project_path: Path, current_file: Path = None, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.settings = get_settings()
        self.setWindowTitle("Export Document Graph")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(900, 600)

        # Flags for initialization state
        self._initializing = True
        self._preview_shown = False

        # Debounce timer for preview updates
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._update_preview)

        self._init_ui()
        self._load_files()
        self._apply_theme()

        self._initializing = False

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Create splitter for 3-column layout: Files | Preview | Options
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # === Left column: File selection with collapsible tab ===
        self._left_collapsed = False
        self._left_content_width = 220

        left_panel = QWidget()
        left_h_layout = QHBoxLayout(left_panel)
        left_h_layout.setContentsMargins(0, 0, 0, 0)
        left_h_layout.setSpacing(0)

        # Vertical tab (always visible)
        self._left_tab = VerticalTab("FILES", width=28, arrow_direction="left")
        self._left_tab.clicked.connect(self._toggle_left_panel)

        # Content area (can collapse to 0)
        self._left_content = QWidget()
        self._left_content.setMinimumWidth(0)
        self._left_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        file_layout = QVBoxLayout(self._left_content)
        file_layout.setContentsMargins(4, 0, 0, 0)

        file_group = QGroupBox("Files to Include")
        file_group_layout = QVBoxLayout(file_group)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemChanged.connect(self._on_file_selection_changed)
        file_group_layout.addWidget(self.file_list)

        # Select all/none buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addStretch()
        file_group_layout.addLayout(btn_layout)

        file_layout.addWidget(file_group)

        left_h_layout.addWidget(self._left_tab)
        left_h_layout.addWidget(self._left_content)

        # Allow panel to shrink to tab width
        left_panel.setMinimumWidth(28)
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.splitter.addWidget(left_panel)

        # === Middle column: Live Preview ===
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("Preview")
        preview_group_layout = QVBoxLayout(preview_group)

        # Preview area - create QWebEngineView early but delay content loading
        if HAS_WEBENGINE:
            self.preview_view = QWebEngineView()
            # Set custom page to handle node clicks
            self._preview_page = GraphPreviewPage(self.preview_view)
            self._preview_page.file_clicked_callback = self._on_preview_node_clicked
            self.preview_view.setPage(self._preview_page)
            # Set empty content initially - will be populated after dialog is shown
            self.preview_view.setHtml("<html><body></body></html>")
        else:
            from PySide6.QtWidgets import QTextEdit
            self.preview_view = QTextEdit()
            self.preview_view.setReadOnly(True)
        # Add with stretch factor 1 so it expands to fill space
        preview_group_layout.addWidget(self.preview_view, 1)

        # Preview controls (no stretch - stays at bottom)
        preview_btn_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._update_preview)
        preview_btn_layout.addWidget(self.refresh_btn)

        self.preview_status = QLabel("")
        preview_btn_layout.addWidget(self.preview_status)
        preview_btn_layout.addStretch()

        preview_group_layout.addLayout(preview_btn_layout, 0)

        preview_layout.addWidget(preview_group)
        self.splitter.addWidget(preview_widget)

        # === Right column: Options with collapsible tab ===
        self._right_collapsed = False
        self._right_content_width = 220

        right_panel = QWidget()
        right_h_layout = QHBoxLayout(right_panel)
        right_h_layout.setContentsMargins(0, 0, 0, 0)
        right_h_layout.setSpacing(0)

        # Content area (can collapse to 0)
        self._right_content = QWidget()
        self._right_content.setMinimumWidth(0)
        self._right_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        options_layout = QVBoxLayout(self._right_content)
        options_layout.setContentsMargins(0, 0, 4, 0)

        # Vertical tab (always visible, on right side)
        self._right_tab = VerticalTab("OPTIONS", width=28, arrow_direction="right")
        self._right_tab.clicked.connect(self._toggle_right_panel)

        # Graph options
        graph_group = QGroupBox("Graph Options")
        graph_layout = QVBoxLayout(graph_group)

        # Direction
        direction_layout = QHBoxLayout()
        direction_layout.addWidget(QLabel("Direction:"))
        self.directed_radio = QRadioButton("Directed")
        self.directed_radio.setChecked(True)
        self.directed_radio.toggled.connect(self._schedule_preview_update)
        self.undirected_radio = QRadioButton("Undirected")
        direction_layout.addWidget(self.directed_radio)
        direction_layout.addWidget(self.undirected_radio)
        direction_layout.addStretch()
        graph_layout.addLayout(direction_layout)

        # Layout engine
        engine_layout = QHBoxLayout()
        engine_layout.addWidget(QLabel("Layout:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["dot", "neato", "fdp", "circo", "twopi", "sfdp"])
        self.engine_combo.setToolTip(
            "dot: hierarchical (best for documentation trees)\n"
            "neato/fdp/sfdp: force-directed (best for interconnected graphs)\n"
            "circo: circular layout\n"
            "twopi: radial layout"
        )
        self.engine_combo.currentIndexChanged.connect(self._schedule_preview_update)
        engine_layout.addWidget(self.engine_combo)
        engine_layout.addStretch()
        graph_layout.addLayout(engine_layout)

        # Node label template
        label_layout = QHBoxLayout()
        label_layout.addWidget(QLabel("Node labels:"))
        self.label_combo = QComboBox()
        self.label_combo.addItems([
            "{stem}",
            "{filename}",
            "{relative_path}",
            "{relative_path_no_ext}",
            "Custom..."
        ])
        self.label_combo.setToolTip(
            "{stem}: filename without extension\n"
            "{filename}: full filename\n"
            "{relative_path}: path relative to project\n"
            "{relative_path_no_ext}: relative path without extension"
        )
        self.label_combo.currentTextChanged.connect(self._on_label_changed)
        label_layout.addWidget(self.label_combo)
        label_layout.addStretch()
        graph_layout.addLayout(label_layout)

        # Custom label input (hidden by default)
        self.custom_label_input = QLineEdit()
        self.custom_label_input.setPlaceholderText("e.g., {stem} or {relative_path}")
        self.custom_label_input.textChanged.connect(self._schedule_preview_update)

        # Node style checkbox
        self.labels_below_check = QCheckBox("Labels below nodes (dot style)")
        self.labels_below_check.setToolTip("Display nodes as small dots with labels underneath")
        self.labels_below_check.toggled.connect(self._schedule_preview_update)
        self.custom_label_input.hide()
        graph_layout.addWidget(self.custom_label_input)
        graph_layout.addWidget(self.labels_below_check)

        options_layout.addWidget(graph_group)

        # Broken links handling
        broken_group = QGroupBox("Broken Links (non-existent files)")
        broken_layout = QVBoxLayout(broken_group)

        self.broken_red_radio = QRadioButton("Show in red with dashed border")
        self.broken_red_radio.setChecked(True)
        self.broken_red_radio.toggled.connect(self._schedule_preview_update)
        self.broken_exclude_radio = QRadioButton("Exclude from graph")
        self.broken_exclude_radio.toggled.connect(self._schedule_preview_update)
        self.broken_warning_radio = QRadioButton("Show as warning nodes")
        self.broken_warning_radio.toggled.connect(self._schedule_preview_update)
        self.broken_normal_radio = QRadioButton("Show as regular nodes (ignore)")
        self.broken_normal_radio.toggled.connect(self._schedule_preview_update)

        broken_layout.addWidget(self.broken_red_radio)
        broken_layout.addWidget(self.broken_exclude_radio)
        broken_layout.addWidget(self.broken_warning_radio)
        broken_layout.addWidget(self.broken_normal_radio)

        options_layout.addWidget(broken_group)

        # Output options
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Save as:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["SVG", "PNG", "DOT"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        output_layout.addLayout(format_layout)

        self.show_preview_check = QCheckBox("Display in popup window after generation")
        self.show_preview_check.setChecked(False)
        output_layout.addWidget(self.show_preview_check)

        options_layout.addWidget(output_group)
        options_layout.addStretch()

        right_h_layout.addWidget(self._right_content)
        right_h_layout.addWidget(self._right_tab)

        # Allow panel to shrink to tab width
        right_panel.setMinimumWidth(28)
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.splitter.addWidget(right_panel)

        # Disable native collapsing - we handle it with tabs
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([250, 400, 250])
        self.splitter.setStretchFactor(1, 1)  # Preview gets extra space

        layout.addWidget(self.splitter)

        # Buttons
        button_box = QDialogButtonBox()
        self.export_btn = button_box.addButton("Export...", QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.export_btn.clicked.connect(self._export)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _apply_theme(self):
        """Apply the current theme."""
        theme_name = self.settings.get("view.theme", "light")
        theme = get_theme(theme_name == "dark")
        self.setStyleSheet(
            StyleSheets.dialog(theme) +
            StyleSheets.list_widget(theme) +
            StyleSheets.button(theme) +
            StyleSheets.combo_box(theme) +
            StyleSheets.line_edit(theme)
        )

    def _load_files(self):
        """Load all markdown files from project."""
        self.file_list.clear()

        if not self.project_path:
            return

        # Find all markdown files recursively
        md_files = []
        for ext in ["*.md", "*.markdown"]:
            md_files.extend(self.project_path.rglob(ext))

        md_files = sorted(md_files)

        for file_path in md_files:
            rel_path = file_path.relative_to(self.project_path)
            item = QListWidgetItem(str(rel_path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, str(file_path))
            self.file_list.addItem(item)

    def _select_all(self):
        """Select all files."""
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Checked)
        self.file_list.blockSignals(False)
        self._schedule_preview_update()

    def _select_none(self):
        """Deselect all files."""
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.file_list.blockSignals(False)
        self._schedule_preview_update()

    def _toggle_left_panel(self):
        """Toggle the left (Files) panel."""
        sizes = self.splitter.sizes()
        tab_width = 28

        if not self._left_collapsed:
            # Collapse - store current size, shrink to tab width
            self._left_content_width = max(sizes[0], tab_width + 50)
            new_left = tab_width
            # Give the freed space to preview
            freed = sizes[0] - new_left
            sizes[0] = new_left
            sizes[1] += freed
            self._left_collapsed = True
        else:
            # Expand - restore previous size
            restore = max(self._left_content_width, 180)
            needed = restore - sizes[0]
            sizes[0] = restore
            sizes[1] = max(200, sizes[1] - needed)
            self._left_collapsed = False
        self._left_tab.setCollapsed(self._left_collapsed)
        self.splitter.setSizes(sizes)

    def _toggle_right_panel(self):
        """Toggle the right (Options) panel."""
        sizes = self.splitter.sizes()
        tab_width = 28

        if not self._right_collapsed:
            # Collapse - store current size, shrink to tab width
            self._right_content_width = max(sizes[2], tab_width + 50)
            new_right = tab_width
            # Give the freed space to preview
            freed = sizes[2] - new_right
            sizes[2] = new_right
            sizes[1] += freed
            self._right_collapsed = True
        else:
            # Expand - restore previous size
            restore = max(self._right_content_width, 180)
            needed = restore - sizes[2]
            sizes[2] = restore
            sizes[1] = max(200, sizes[1] - needed)
            self._right_collapsed = False
        self._right_tab.setCollapsed(self._right_collapsed)
        self.splitter.setSizes(sizes)

    def _on_label_changed(self, text):
        """Handle label template change."""
        if text == "Custom...":
            self.custom_label_input.show()
        else:
            self.custom_label_input.hide()
        self._schedule_preview_update()

    def _on_file_selection_changed(self, item):
        """Handle file checkbox state change."""
        self._schedule_preview_update()

    def _schedule_preview_update(self, *args):
        """Schedule a preview update with debouncing."""
        if self._initializing:
            return
        self._preview_timer.start()

    def showEvent(self, event):
        """Handle dialog show - trigger initial preview."""
        super().showEvent(event)
        if not self._preview_shown:
            self._preview_shown = True
            QTimer.singleShot(100, self._update_preview)

    def _update_preview(self):
        """Update the live preview."""
        try:
            files = self._get_selected_files()

            if not files:
                self._show_preview_message("No files selected")
                self.preview_status.setText("")
                return

            # Show status for large graphs
            if len(files) > 30:
                self.preview_status.setText(f"⏳ Rendering {len(files)} files...")
                QApplication.processEvents()

            dot_source = self._generate_graph(files)
            dark_mode = self.settings.get("view.theme") == "dark"
            engine = self.engine_combo.currentText()
            svg_content = self._render_to_svg(dot_source, engine, dark_mode)

            if HAS_WEBENGINE and isinstance(self.preview_view, QWebEngineView):
                html = self._create_preview_html(svg_content, dark_mode)
                self.preview_view.setHtml(html)
            else:
                self.preview_view.setPlainText(dot_source)

            self.preview_status.setText(f"✓ {len(files)} files")
        except Exception as e:
            self._show_preview_message(f"Error: {e}")
            self.preview_status.setText("✗ Error")

    def _show_preview_message(self, message: str):
        """Show a message in the preview area."""
        if HAS_WEBENGINE and isinstance(self.preview_view, QWebEngineView):
            dark_mode = self.settings.get("view.theme") == "dark"
            bg = "#1e1e1e" if dark_mode else "#ffffff"
            color = "#888"
            html = f'<html><body style="background:{bg};color:{color};display:flex;justify-content:center;align-items:center;height:100vh;margin:0">{message}</body></html>'
            self.preview_view.setHtml(html)
        else:
            self.preview_view.setPlainText(message)

    def _create_preview_html(self, svg_content: str, dark_mode: bool) -> str:
        """Create HTML for the preview with clickable nodes, zoom and pan."""
        bg_color = "#1e1e1e" if dark_mode else "#ffffff"

        return f"""<!DOCTYPE html>
<html><head><style>
html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: {bg_color};
}}
#container {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    cursor: grab;
}}
#container.grabbing {{
    cursor: grabbing;
}}
#graph {{
    transform-origin: 0 0;
    position: absolute;
}}
svg {{
    display: block;
}}
.node {{ cursor: pointer; }}
.node:hover polygon, .node:hover ellipse, .node:hover path {{ stroke-width: 2px; }}
</style></head>
<body>
<div id="container">
    <div id="graph">{svg_content}</div>
</div>
<script>
(function() {{
    var container = document.getElementById('container');
    var graph = document.getElementById('graph');
    var scale = 1;
    var panX = 0, panY = 0;
    var isPanning = false;
    var startX, startY;

    function updateTransform() {{
        graph.style.transform = 'translate(' + panX + 'px, ' + panY + 'px) scale(' + scale + ')';
    }}

    // Fit to view on load
    function fitToView() {{
        var svg = graph.querySelector('svg');
        if (!svg) return;
        var svgWidth = svg.getBBox().width || svg.clientWidth || 500;
        var svgHeight = svg.getBBox().height || svg.clientHeight || 500;
        var containerRect = container.getBoundingClientRect();
        var scaleX = containerRect.width / svgWidth;
        var scaleY = containerRect.height / svgHeight;
        scale = Math.min(scaleX, scaleY, 1) * 0.95;
        panX = (containerRect.width - svgWidth * scale) / 2;
        panY = (containerRect.height - svgHeight * scale) / 2;
        updateTransform();
    }}
    setTimeout(fitToView, 50);

    // Mouse wheel zoom
    container.addEventListener('wheel', function(e) {{
        e.preventDefault();
        var rect = container.getBoundingClientRect();
        var mouseX = e.clientX - rect.left;
        var mouseY = e.clientY - rect.top;
        var delta = e.deltaY > 0 ? 0.9 : 1.1;
        var newScale = Math.max(0.1, Math.min(5, scale * delta));
        panX = mouseX - (mouseX - panX) * (newScale / scale);
        panY = mouseY - (mouseY - panY) * (newScale / scale);
        scale = newScale;
        updateTransform();
    }});

    // Pan with mouse drag
    container.addEventListener('mousedown', function(e) {{
        if (e.target.closest('.node')) return;
        isPanning = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
        container.classList.add('grabbing');
    }});
    document.addEventListener('mousemove', function(e) {{
        if (!isPanning) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        updateTransform();
    }});
    document.addEventListener('mouseup', function() {{
        isPanning = false;
        container.classList.remove('grabbing');
    }});

    // Node click handlers
    document.querySelectorAll('.node').forEach(function(node) {{
        node.addEventListener('click', function(e) {{
            e.preventDefault();
            e.stopPropagation();
            var anchor = node.querySelector('a');
            if (anchor) {{
                var href = anchor.getAttribute('xlink:href') || anchor.getAttribute('href');
                if (href) {{
                    window.location.href = 'file://' + href;
                }}
            }}
        }});
    }});
}})();
</script>
</body></html>"""

    def _get_label_template(self) -> str:
        """Get the current label template."""
        text = self.label_combo.currentText()
        if text == "Custom...":
            return self.custom_label_input.text() or "{stem}"
        return text

    def _get_selected_files(self) -> list[Path]:
        """Get list of selected files."""
        files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                files.append(Path(item.data(Qt.ItemDataRole.UserRole)))
        return files

    def _export(self):
        """Export the document graph."""
        files = self._get_selected_files()
        if not files:
            QMessageBox.warning(self, "No Files", "Please select at least one file.")
            return

        # Get output path
        format_type = self.format_combo.currentText().lower()
        ext = {"svg": ".svg", "png": ".png", "dot": ".dot"}[format_type]

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Graph",
            str(self.project_path / f"document-graph{ext}"),
            f"{format_type.upper()} Files (*{ext})",
        )

        if not output_path:
            return

        # Generate graph
        try:
            dot_source = self._generate_graph(files)

            if format_type == "dot":
                Path(output_path).write_text(dot_source, encoding="utf-8")
            else:
                # Render to SVG or PNG
                dark_mode = self.settings.get("view.theme") == "dark"
                engine = self.engine_combo.currentText()

                if format_type == "svg":
                    svg_content = self._render_to_svg(dot_source, engine, dark_mode)
                    Path(output_path).write_text(svg_content, encoding="utf-8")
                else:  # png
                    self._render_to_png(dot_source, output_path, engine)

            # Show preview if requested
            if self.show_preview_check.isChecked():
                self._show_preview(dot_source)

            QMessageBox.information(self, "Export Complete", f"Graph saved to:\n{output_path}")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to generate graph:\n{e}")

    def _generate_graph(self, files: list[Path]) -> str:
        """Generate DOT source from document links."""
        # Build file index
        file_index = {}  # stem -> full path
        for f in files:
            file_index[f.stem.lower()] = f
            # Also index by relative path without extension
            rel_path = f.relative_to(self.project_path)
            rel_no_ext = str(rel_path.with_suffix("")).lower()
            file_index[rel_no_ext] = f

        # Parse links from each file
        links = []  # (source_path, target_path, exists)
        all_targets = set()

        for source_file in files:
            try:
                content = source_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Find wiki links
            for match in WIKI_LINK_PATTERN.finditer(content):
                target = match.group(1).strip().lower()
                target_path = self._resolve_link(target, source_file, file_index)
                exists = target_path is not None and target_path.exists()
                links.append((source_file, target_path or target, exists))
                all_targets.add(target_path or target)

            # Find markdown links
            for match in MD_LINK_PATTERN.finditer(content):
                target = match.group(2).strip()
                # Resolve relative to source file
                target_path = (source_file.parent / target).resolve()
                exists = target_path.exists()
                links.append((source_file, target_path, exists))
                all_targets.add(target_path)

        # Generate DOT
        is_directed = self.directed_radio.isChecked()
        graph_type = "digraph" if is_directed else "graph"
        edge_op = "->" if is_directed else "--"

        label_template = self._get_label_template()
        broken_handling = (
            "red" if self.broken_red_radio.isChecked()
            else "exclude" if self.broken_exclude_radio.isChecked()
            else "warning" if self.broken_warning_radio.isChecked()
            else "normal"
        )

        # Check if labels should be below nodes
        labels_below = self.labels_below_check.isChecked()
        engine = self.engine_combo.currentText()

        lines = [f'{graph_type} DocumentGraph {{']
        lines.append('    rankdir=LR;')

        if labels_below:
            # Use smaller font and increase spacing to prevent label overlap
            lines.append('    forcelabels=true;')
            lines.append('    node [shape=point, width=0.15, height=0.15];')
            lines.append('    graph [fontsize=10];')
            lines.append('    node [fontsize=10];')

            # Spacing depends on layout engine
            if engine == "dot":
                # Hierarchical layout - increase rank and node separation
                lines.append('    nodesep=0.8;')
                lines.append('    ranksep=1.0;')
            else:
                # Force-directed layouts (neato, fdp, circo, twopi, sfdp)
                # Use overlap removal and increase separation
                lines.append('    overlap=prism;')
                lines.append('    overlap_scaling=2;')
                lines.append('    sep="+20,20";')
        else:
            lines.append('    node [shape=box, style=rounded];')
        lines.append('')

        # Add nodes
        node_ids = {}  # path -> node_id
        node_counter = 0

        def get_node_id(path):
            nonlocal node_counter
            if path not in node_ids:
                node_ids[path] = f"n{node_counter}"
                node_counter += 1
            return node_ids[path]

        def get_label(path):
            if isinstance(path, Path):
                try:
                    rel = path.relative_to(self.project_path)
                except ValueError:
                    rel = path
                return label_template.format(
                    stem=path.stem,
                    filename=path.name,
                    relative_path=str(rel),
                    relative_path_no_ext=str(rel.with_suffix(""))
                )
            return str(path)

        def get_tooltip(path):
            """Get relative path for tooltip."""
            if isinstance(path, Path):
                try:
                    return str(path.relative_to(self.project_path))
                except ValueError:
                    return str(path)
            return str(path)

        # Add file nodes (include URL for click handling)
        for f in files:
            node_id = get_node_id(f)
            label = get_label(f)
            tooltip = get_tooltip(f)
            url = str(f).replace('"', '\\"')
            if labels_below:
                lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}", URL="{url}"];')
            else:
                lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}", URL="{url}"];')

        # Add broken link nodes
        broken_nodes = set()
        for source, target, exists in links:
            if not exists:
                if broken_handling == "exclude":
                    continue
                if target not in broken_nodes:
                    broken_nodes.add(target)
                    node_id = get_node_id(target)
                    label = get_label(target) if isinstance(target, Path) else target
                    tooltip = get_tooltip(target)
                    if broken_handling == "red":
                        if labels_below:
                            lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}", color=red];')
                        else:
                            lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}", color=red, style="dashed,rounded"];')
                    elif broken_handling == "warning":
                        if labels_below:
                            lines.append(f'    {node_id} [shape=point, xlabel="{label}\\n(missing)", tooltip="{tooltip}", color=orange];')
                        else:
                            lines.append(f'    {node_id} [label="{label}\\n(missing)", tooltip="{tooltip}", color=orange, style="filled,rounded", fillcolor=lightyellow];')
                    else:  # normal - show as regular node
                        if labels_below:
                            lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}"];')
                        else:
                            lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}"];')

        lines.append('')

        # Add edges
        seen_edges = set()
        for source, target, exists in links:
            if not exists and broken_handling == "exclude":
                continue

            source_id = get_node_id(source)
            target_id = get_node_id(target)

            edge_key = (source_id, target_id) if is_directed else tuple(sorted([source_id, target_id]))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            if exists or broken_handling == "normal":
                lines.append(f'    {source_id} {edge_op} {target_id};')
            else:
                lines.append(f'    {source_id} {edge_op} {target_id} [style=dashed, color=red];')

        lines.append('}')

        return '\n'.join(lines)

    def _resolve_link(self, target: str, source_file: Path, file_index: dict) -> Path | None:
        """Resolve a wiki link target to a file path."""
        # Try direct match
        if target in file_index:
            return file_index[target]

        # Try with .md extension
        target_md = target + ".md"
        if target_md.lower() in file_index:
            return file_index[target_md.lower()]

        # Try relative to source
        rel_path = source_file.parent / (target + ".md")
        if rel_path.exists():
            return rel_path.resolve()

        return None

    def _render_to_svg(self, dot_source: str, engine: str, dark_mode: bool) -> str:
        """Render DOT to SVG string."""
        import graphviz
        graph = graphviz.Source(dot_source, engine=engine)
        svg = graph.pipe(format='svg').decode('utf-8')

        if dark_mode:
            svg = graphviz_service._apply_dark_mode(svg)

        return svg

    def _render_to_png(self, dot_source: str, output_path: str, engine: str):
        """Render DOT to PNG file."""
        import graphviz
        graph = graphviz.Source(dot_source, engine=engine)
        # graphviz.Source.render() adds extension, so we remove it first
        output_base = str(Path(output_path).with_suffix(""))
        graph.render(output_base, format='png', cleanup=True)

    def _show_preview(self, dot_source: str):
        """Show the graph in a preview window."""
        dark_mode = self.settings.get("view.theme") == "dark"
        engine = self.engine_combo.currentText()

        try:
            svg_content = self._render_to_svg(dot_source, engine, dark_mode)
            dialog = GraphPreviewDialog(svg_content, self.project_path, dark_mode, self)
            dialog.file_clicked.connect(self._on_preview_file_clicked)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", f"Could not render preview:\n{e}")

    def _on_preview_node_clicked(self, file_path: str):
        """Handle node click in the live preview."""
        path = Path(file_path)
        if path.exists():
            self.file_clicked.emit(path)

    def _on_preview_file_clicked(self, file_path: str):
        """Handle file click in popup preview."""
        path = Path(file_path)
        if path.exists():
            self.file_clicked.emit(path)


class GraphPreviewPage(QWebEnginePage if HAS_WEBENGINE else object):
    """Custom page to intercept node click navigation."""

    def __init__(self, parent=None):
        if HAS_WEBENGINE:
            super().__init__(parent)
        self.file_clicked_callback = None

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        """Intercept navigation to handle node clicks."""
        url_str = url.toString()
        # Check if this is a file:// URL from a node click
        if url_str.startswith("file://") and self.file_clicked_callback:
            # Extract path from URL (remove file:// prefix)
            file_path = url_str[7:]  # Remove 'file://'
            self.file_clicked_callback(file_path)
            return False  # Don't actually navigate
        return True


class GraphPreviewDialog(QDialog):
    """Dialog for previewing the document graph."""

    file_clicked = Signal(str)

    def __init__(self, svg_content: str, project_path: Path, dark_mode: bool, parent=None):
        super().__init__(parent)
        self.svg_content = svg_content
        self.project_path = project_path
        self.dark_mode = dark_mode
        self.setWindowTitle("Document Graph Preview")
        self.setMinimumSize(800, 600)
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Use WebEngine if available for better SVG rendering and interactivity
        if HAS_WEBENGINE:
            self.view = QWebEngineView()

            # Create custom page to intercept navigation
            self.page = GraphPreviewPage(self.view)
            self.page.file_clicked_callback = self._handle_node_click
            self.view.setPage(self.page)

            # Create HTML with clickable SVG
            html = self._create_interactive_html()
            self.view.setHtml(html)

            # Handle link hover for tooltips
            self.view.page().linkHovered.connect(self._on_link_hovered)

            layout.addWidget(self.view)
        else:
            # Fallback to QLabel with SVG
            from PySide6.QtSvgWidgets import QSvgWidget
            self.view = QSvgWidget()
            self.view.load(self.svg_content.encode())
            layout.addWidget(self.view)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def _handle_node_click(self, file_path: str):
        """Handle node click from custom page."""
        self.file_clicked.emit(file_path)

    def _create_interactive_html(self) -> str:
        """Create HTML with interactive SVG."""
        bg_color = "#1e1e1e" if self.dark_mode else "#ffffff"
        text_color = "#d4d4d4" if self.dark_mode else "#333333"

        return f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background-color: {bg_color};
            color: {text_color};
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
        }}
        svg {{
            max-width: 100%;
            height: auto;
        }}
        /* Make nodes look clickable */
        .node {{
            cursor: pointer;
        }}
        .node:hover polygon,
        .node:hover ellipse,
        .node:hover path {{
            stroke-width: 2px;
        }}
    </style>
</head>
<body>
    {self.svg_content}
    <script>
        // Add click handlers to nodes
        document.querySelectorAll('.node').forEach(function(node) {{
            node.addEventListener('click', function(e) {{
                e.preventDefault();
                // Look for xlink:href in anchor element (set by URL attribute in DOT)
                var anchor = node.querySelector('a');
                if (anchor) {{
                    var href = anchor.getAttribute('xlink:href') || anchor.getAttribute('href');
                    if (href) {{
                        // Signal to Qt - navigate to file:// URL
                        window.location.href = 'file://' + href;
                        return;
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>"""

    def _on_link_hovered(self, url: str):
        """Handle link hover."""
        self.view.setToolTip(url if url else "")

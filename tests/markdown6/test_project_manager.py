"""Tests for the project manager module."""

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.project_manager import (
    ProjectConfig,
    ProjectExportDialog,
    ProjectPanel,
)


@pytest.fixture
def panel(qtbot):
    """Create a ProjectPanel instance."""
    p = ProjectPanel(get_app_context())
    qtbot.addWidget(p)
    return p


@pytest.fixture
def project_dir(tmp_path):
    """Create a temporary project directory with files."""
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "readme.md").write_text("# README")
    (project / "doc.md").write_text("# Doc")
    (project / "subdir").mkdir()
    (project / "subdir" / "nested.md").write_text("# Nested")
    return project


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_config_creation(self):
        """Test creating a ProjectConfig."""
        config = ProjectConfig(
            name="Test Project",
            root_path="/path/to/project",
        )
        assert config.name == "Test Project"
        assert config.root_path == "/path/to/project"

    def test_config_defaults(self):
        """Test default values."""
        config = ProjectConfig(name="Test", root_path="/path")
        assert config.export_order == []
        assert config.export_format == "html"
        assert config.created == ""
        assert config.modified == ""


class TestProjectPanelCreation:
    """Tests for ProjectPanel initialization."""

    def test_panel_creation(self, panel):
        """Test creating a project panel."""
        assert panel is not None
        assert panel.project_path is None

    def test_tree_view_exists(self, panel):
        """Test that tree view exists."""
        assert panel.tree_view is not None

    def test_filter_input_exists(self, panel):
        """Test that filter input exists."""
        assert panel.filter_input is not None

    def test_signals_exist(self, panel):
        """Test that signals are defined."""
        assert hasattr(panel, "file_selected")
        assert hasattr(panel, "file_double_clicked")
        assert hasattr(panel, "graph_export_requested")

    def test_default_file_filters(self, panel):
        """Test default file filters."""
        filters = panel.file_model.nameFilters()
        assert "*.md" in filters
        assert "*.markdown" in filters
        assert "*.txt" in filters


class TestProjectPath:
    """Tests for setting project path."""

    def test_set_project_path(self, panel, project_dir):
        """Test setting the project path."""
        panel.set_project_path(project_dir)
        assert panel.project_path == project_dir

    def test_set_project_path_updates_model(self, panel, project_dir):
        """Test that model root is updated."""
        panel.set_project_path(project_dir)
        assert panel.file_model.rootPath() == str(project_dir)

    def test_set_project_path_clears_filter(self, panel, project_dir):
        """Test that filter is cleared when project changes."""
        panel.filter_input.setText("test")
        panel.set_project_path(project_dir)
        assert panel.filter_input.text() == ""


class TestFileFiltering:
    """Tests for file filtering."""

    def test_filter_text_change(self, panel, project_dir):
        """Test filter text changes."""
        panel.set_project_path(project_dir)
        panel._on_filter_changed("readme")
        # Filter should be set
        assert panel._filter_text == "readme"

    def test_filter_creates_patterns(self, panel, project_dir):
        """Test that filter creates appropriate patterns."""
        panel.set_project_path(project_dir)
        panel._on_filter_changed("test")
        filters = panel.file_model.nameFilters()
        # Should have patterns containing "test"
        assert any("test" in f for f in filters)

    def test_empty_filter_resets(self, panel, project_dir):
        """Test that empty filter resets to defaults."""
        panel.set_project_path(project_dir)
        panel._on_filter_changed("something")
        panel._on_filter_changed("")
        filters = panel.file_model.nameFilters()
        assert "*.md" in filters


class TestFileSelection:
    """Tests for file selection."""

    def test_file_selected_signal(self, panel, project_dir, qtbot):
        """Test that file_selected signal is emitted."""
        panel.set_project_path(project_dir)

        # Get index of a file
        index = panel.file_model.index(str(project_dir / "readme.md"))

        with qtbot.waitSignal(panel.file_selected):
            panel._on_item_clicked(index)

    def test_file_double_clicked_signal(self, panel, project_dir, qtbot):
        """Test that file_double_clicked signal is emitted."""
        panel.set_project_path(project_dir)

        index = panel.file_model.index(str(project_dir / "readme.md"))

        with qtbot.waitSignal(panel.file_double_clicked):
            panel._on_item_double_clicked(index)


class TestProjectFiles:
    """Tests for get_project_files method."""

    def test_get_project_files_no_project(self, panel):
        """Test get_project_files with no project set."""
        files = panel.get_project_files()
        assert files == []

    def test_get_project_files(self, panel, project_dir):
        """Test getting all markdown files."""
        panel.set_project_path(project_dir)
        files = panel.get_project_files()

        # Should find all .md files
        assert len(files) == 3
        names = [f.name for f in files]
        assert "readme.md" in names
        assert "doc.md" in names
        assert "nested.md" in names

    def test_get_project_files_sorted(self, panel, project_dir):
        """Test that files are sorted."""
        panel.set_project_path(project_dir)
        files = panel.get_project_files()

        # Should be sorted
        assert files == sorted(files)


class TestContextMenu:
    """Tests for context menu functionality."""

    def test_new_file(self, panel, project_dir, qtbot):
        """Test creating a new file."""
        panel.set_project_path(project_dir)

        with patch.object(panel, "file_double_clicked"):
            with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("new.md", True)):
                panel._new_file(project_dir)

        assert (project_dir / "new.md").exists()

    def test_new_file_adds_extension(self, panel, project_dir):
        """Test that .md is added if missing."""
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("test", True)):
            panel._new_file(project_dir)

        assert (project_dir / "test.md").exists()

    def test_new_file_cancelled(self, panel, project_dir):
        """Test cancelling new file dialog."""
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("", False)):
            panel._new_file(project_dir)

        # No new file should be created
        assert len([f for f in project_dir.glob("*.md") if f.name not in ["readme.md", "doc.md"]]) == 0

    def test_new_folder(self, panel, project_dir):
        """Test creating a new folder."""
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("newfolder", True)):
            panel._new_folder(project_dir)

        assert (project_dir / "newfolder").is_dir()

    def test_rename_file(self, panel, project_dir):
        """Test renaming a file."""
        test_file = project_dir / "to_rename.md"
        test_file.write_text("content")

        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("renamed.md", True)):
            panel._rename_file(test_file)

        assert (project_dir / "renamed.md").exists()
        assert not test_file.exists()

    def test_delete_file(self, panel, project_dir):
        """Test deleting a file."""
        test_file = project_dir / "to_delete.md"
        test_file.write_text("content")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            panel._delete_file(test_file)

        assert not test_file.exists()

    def test_delete_file_cancelled(self, panel, project_dir):
        """Test cancelling file deletion."""
        test_file = project_dir / "keep_me.md"
        test_file.write_text("content")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            panel._delete_file(test_file)

        assert test_file.exists()


class TestGraphExport:
    """Tests for graph export button."""

    def test_graph_export_no_project(self, panel, qtbot):
        """Test graph export with no project shows warning."""
        with patch.object(QMessageBox, "warning") as mock_warning:
            panel._on_graph_export_clicked()
            mock_warning.assert_called_once()

    def test_graph_export_emits_signal(self, panel, project_dir, qtbot):
        """Test graph export emits signal when project is set."""
        panel.set_project_path(project_dir)

        with qtbot.waitSignal(panel.graph_export_requested):
            panel._on_graph_export_clicked()


class TestProjectExportDialog:
    """Tests for ProjectExportDialog."""

    @pytest.fixture
    def export_dialog(self, qtbot, project_dir):
        """Create a ProjectExportDialog instance."""
        dialog = ProjectExportDialog(project_dir, get_app_context())
        qtbot.addWidget(dialog)
        return dialog

    def test_dialog_creation(self, export_dialog):
        """Test creating export dialog."""
        assert export_dialog is not None
        assert export_dialog.windowTitle() == "Export Project"

    def test_files_loaded(self, export_dialog, project_dir):
        """Test that project files are loaded."""
        # Should have loaded the markdown files
        assert len(export_dialog.file_tree.get_selected_files()) == 3

    def test_files_checked_by_default(self, export_dialog):
        """Test that files are checked by default."""
        selected = export_dialog.file_tree.get_selected_files()
        assert len(selected) == 3

    def test_select_all(self, export_dialog):
        """Test select all button."""
        # First uncheck all
        export_dialog._select_none()
        assert len(export_dialog.file_tree.get_selected_files()) == 0
        # Then select all
        export_dialog._select_all()
        assert len(export_dialog.file_tree.get_selected_files()) == 3

    def test_select_none(self, export_dialog):
        """Test select none button."""
        export_dialog._select_none()
        assert len(export_dialog.file_tree.get_selected_files()) == 0

    def test_format_options(self, export_dialog):
        """Test format combo box options."""
        formats = []
        for i in range(export_dialog.format_combo.count()):
            formats.append(export_dialog.format_combo.itemText(i))

        assert "HTML" in formats
        assert "PDF" in formats
        assert "DOCX" in formats
        assert "Markdown" in formats

    def test_include_toc_default(self, export_dialog):
        """Test include TOC is checked by default."""
        assert export_dialog.include_toc.isChecked()

    def test_page_breaks_default(self, export_dialog):
        """Test page breaks is checked by default."""
        assert export_dialog.page_breaks.isChecked()

    def test_export_no_files_warning(self, export_dialog, qtbot):
        """Test export with no files selected shows warning."""
        export_dialog._select_none()

        with patch.object(QMessageBox, "warning") as mock_warning:
            export_dialog._export()
            mock_warning.assert_called_once()

    def test_export_cancelled_on_no_path(self, export_dialog):
        """Test export is cancelled if no output path selected."""
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
            # Should not crash
            export_dialog._export()


class TestProjectExportFormats:
    """Tests for different export formats."""

    @pytest.fixture
    def export_dialog(self, qtbot, project_dir):
        """Create a ProjectExportDialog instance."""
        dialog = ProjectExportDialog(project_dir, get_app_context())
        qtbot.addWidget(dialog)
        return dialog

    def test_html_export(self, export_dialog, tmp_path):
        """Test HTML export."""
        output_path = tmp_path / "output.html"
        export_dialog.format_combo.setCurrentText("HTML")

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch.object(QMessageBox, "information"):
                export_dialog._export()

        assert output_path.exists()

    def test_markdown_export(self, export_dialog, tmp_path):
        """Test Markdown export (combined)."""
        output_path = tmp_path / "output.md"
        export_dialog.format_combo.setCurrentText("Markdown")

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch.object(QMessageBox, "information"):
                export_dialog._export()

        assert output_path.exists()
        content = output_path.read_text()
        # Should contain content from the files
        assert "README" in content or "Doc" in content

    def test_toc_included_when_checked(self, export_dialog, tmp_path):
        """Test that TOC is included when option is checked."""
        output_path = tmp_path / "output.md"
        export_dialog.format_combo.setCurrentText("Markdown")
        export_dialog.include_toc.setChecked(True)

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch.object(QMessageBox, "information"):
                export_dialog._export()

        content = output_path.read_text()
        assert "Table of Contents" in content

    def test_page_breaks_html(self, export_dialog, tmp_path):
        """Test page breaks in HTML export."""
        output_path = tmp_path / "output.html"
        export_dialog.format_combo.setCurrentText("HTML")
        export_dialog.page_breaks.setChecked(True)

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch.object(QMessageBox, "information"):
                export_dialog._export()

        content = output_path.read_text()
        assert "page-break" in content


class TestExportErrors:
    """Tests for export error handling."""

    @pytest.fixture
    def export_dialog(self, qtbot, project_dir):
        """Create a ProjectExportDialog instance."""
        dialog = ProjectExportDialog(project_dir, get_app_context())
        qtbot.addWidget(dialog)
        return dialog

    def test_export_error_handled(self, export_dialog, tmp_path):
        """Test that export errors are handled gracefully."""
        from markdown_editor.markdown6.export_service import ExportError

        export_dialog.format_combo.setCurrentText("PDF")
        output_path = tmp_path / "output.pdf"

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch("markdown_editor.markdown6.export_service.export_pdf", side_effect=ExportError("Test error")):
                with patch.object(QMessageBox, "warning") as mock_warning:
                    export_dialog._export()
                    mock_warning.assert_called_once()

    def test_general_error_handled(self, export_dialog, tmp_path):
        """Test that general errors are handled gracefully."""
        export_dialog.format_combo.setCurrentText("HTML")
        output_path = tmp_path / "output.html"

        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_path), "")):
            with patch("markdown_editor.markdown6.export_service.export_html", side_effect=Exception("General error")):
                with patch.object(QMessageBox, "critical") as mock_critical:
                    export_dialog._export()
                    mock_critical.assert_called_once()


class TestTreeStatePersistence:
    """Tests for saving and restoring expanded directory state."""

    @pytest.fixture
    def deep_project(self, tmp_path):
        """Create a project with nested directories."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "top.md").write_text("# Top")
        d1 = root / "dir_a"
        d1.mkdir()
        (d1 / "a.md").write_text("# A")
        d2 = d1 / "dir_b"
        d2.mkdir()
        (d2 / "b.md").write_text("# B")
        d3 = root / "dir_c"
        d3.mkdir()
        (d3 / "c.md").write_text("# C")
        return root

    def _expand_and_wait(self, qtbot, panel, dir_path):
        """Expand a directory in the tree and wait for it to load."""
        dir_str = str(dir_path)
        loaded = set()
        panel.file_model.directoryLoaded.connect(loaded.add)
        try:
            idx = panel.file_model.index(dir_str)
            panel.tree_view.expand(idx)
            qtbot.waitUntil(lambda: dir_str in loaded, timeout=5000)
        finally:
            panel.file_model.directoryLoaded.disconnect(loaded.add)

    def _wait_for_expanded(self, qtbot, panel, dir_path):
        """Wait until a directory is expanded in the tree view."""
        dir_str = str(dir_path)
        qtbot.waitUntil(
            lambda: panel.tree_view.isExpanded(panel.file_model.index(dir_str)),
            timeout=5000,
        )

    def test_save_tree_state_empty(self, panel):
        """save_tree_state with no project is a no-op."""
        panel.save_tree_state()
        from markdown_editor.markdown6.app_context import get_app_context
        assert get_app_context().get("project.expanded_dirs", []) == []

    def test_save_and_restore_expanded_dirs(self, qtbot, deep_project):
        """Expand dirs, save, create new panel, verify dirs restored."""
        from markdown_editor.markdown6.app_context import get_app_context
        ctx = get_app_context()

        dir_a = deep_project / "dir_a"
        dir_b = dir_a / "dir_b"
        dir_c = deep_project / "dir_c"

        # --- Phase 1: expand dirs and save ---
        panel1 = ProjectPanel(get_app_context())
        qtbot.addWidget(panel1)
        panel1.show()

        # Connect before set_project_path so we catch root directoryLoaded
        root_loaded = set()
        panel1.file_model.directoryLoaded.connect(root_loaded.add)
        panel1.set_project_path(deep_project)
        qtbot.waitUntil(lambda: str(deep_project) in root_loaded, timeout=5000)
        panel1.file_model.directoryLoaded.disconnect(root_loaded.add)

        # Expand directories and wait for each to load
        self._expand_and_wait(qtbot, panel1, dir_a)
        self._expand_and_wait(qtbot, panel1, dir_c)
        self._expand_and_wait(qtbot, panel1, dir_b)

        # Verify they are expanded
        assert panel1.tree_view.isExpanded(panel1.file_model.index(str(dir_a)))
        assert panel1.tree_view.isExpanded(panel1.file_model.index(str(dir_c)))
        assert panel1.tree_view.isExpanded(panel1.file_model.index(str(dir_b)))

        # Save state
        panel1.save_tree_state()
        saved = ctx.get("project.expanded_dirs", [])
        assert str(dir_a) in saved
        assert str(dir_c) in saved
        assert str(dir_b) in saved

        # --- Phase 2: new panel, same project - dirs should restore ---
        panel2 = ProjectPanel(get_app_context())
        qtbot.addWidget(panel2)
        panel2.show()
        panel2.set_project_path(deep_project)

        # Wait for the async restore to expand all saved dirs
        self._wait_for_expanded(qtbot, panel2, dir_a)
        self._wait_for_expanded(qtbot, panel2, dir_c)
        self._wait_for_expanded(qtbot, panel2, dir_b)

    def test_restore_disabled_by_setting(self, qtbot, deep_project):
        """When restore_tree_state is False, dirs are not expanded."""
        from PySide6.QtWidgets import QApplication

        from markdown_editor.markdown6.app_context import get_app_context
        ctx = get_app_context()

        dir_a = deep_project / "dir_a"
        ctx.set("project.expanded_dirs", [str(dir_a)])
        ctx.set("project.restore_tree_state", False)

        panel = ProjectPanel(get_app_context())
        qtbot.addWidget(panel)
        panel.show()

        root_loaded = set()
        panel.file_model.directoryLoaded.connect(root_loaded.add)
        panel.set_project_path(deep_project)
        qtbot.waitUntil(lambda: str(deep_project) in root_loaded, timeout=5000)
        panel.file_model.directoryLoaded.disconnect(root_loaded.add)

        # Process any remaining events
        QApplication.processEvents()

        # Should NOT be expanded
        assert not panel.tree_view.isExpanded(panel.file_model.index(str(dir_a)))

    def test_restore_ignores_dirs_from_different_project(self, qtbot, tmp_path):
        """Saved dirs from a different project root are ignored."""
        from markdown_editor.markdown6.app_context import get_app_context
        ctx = get_app_context()

        # project A
        proj_a = tmp_path / "projA"
        proj_a.mkdir()
        d = proj_a / "sub"
        d.mkdir()
        (d / "x.md").write_text("x")

        # project B
        proj_b = tmp_path / "projB"
        proj_b.mkdir()
        (proj_b / "sub").mkdir()
        (proj_b / "sub" / "y.md").write_text("y")

        # Save dirs from project A
        ctx.set("project.expanded_dirs", [str(d)])

        # Open project B - should not try to expand proj_a/sub
        panel = ProjectPanel(get_app_context())
        qtbot.addWidget(panel)
        panel.set_project_path(proj_b)

        # The pending set should be empty (filtered out)
        assert not panel._pending_expand


class TestPandocOption:
    """Tests for pandoc checkbox."""

    @pytest.fixture
    def export_dialog(self, qtbot, project_dir):
        """Create a ProjectExportDialog instance."""
        dialog = ProjectExportDialog(project_dir, get_app_context())
        qtbot.addWidget(dialog)
        return dialog

    def test_pandoc_disabled_when_unavailable(self, qtbot, project_dir):
        """Test pandoc checkbox disabled when pandoc not installed."""
        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=False):
            dialog = ProjectExportDialog(project_dir, get_app_context())
            qtbot.addWidget(dialog)
            assert not dialog.use_pandoc.isEnabled()

    def test_pandoc_enabled_when_available(self, qtbot, project_dir):
        """Test pandoc checkbox enabled when pandoc is installed."""
        with patch("markdown_editor.markdown6.export_service.has_pandoc", return_value=True):
            dialog = ProjectExportDialog(project_dir, get_app_context())
            qtbot.addWidget(dialog)
            assert dialog.use_pandoc.isEnabled()

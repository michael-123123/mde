"""Tests for the hidden files setting and filtering."""


import pytest

from markdown_editor.markdown6.app_context import (
    get_app_context,
    get_project_markdown_files,
    is_hidden_path,
)

# --- is_hidden_path ---

class TestIsHiddenPath:
    def test_hidden_file(self, tmp_path):
        assert is_hidden_path(tmp_path / ".secret.md", tmp_path) is True

    def test_hidden_directory(self, tmp_path):
        assert is_hidden_path(tmp_path / ".hidden" / "note.md", tmp_path) is True

    def test_nested_hidden_directory(self, tmp_path):
        assert is_hidden_path(tmp_path / "a" / ".hidden" / "note.md", tmp_path) is True

    def test_visible_file(self, tmp_path):
        assert is_hidden_path(tmp_path / "visible.md", tmp_path) is False

    def test_visible_nested(self, tmp_path):
        assert is_hidden_path(tmp_path / "docs" / "readme.md", tmp_path) is False

    def test_root_with_dot_component(self, tmp_path):
        """Components in root itself should not count as hidden."""
        root = tmp_path / ".config" / "project"
        path = root / "notes.md"
        assert is_hidden_path(path, root) is False


# --- get_project_markdown_files ---

@pytest.fixture
def project_tree(tmp_path):
    """Create a project with visible and hidden files/dirs."""
    # Visible files
    (tmp_path / "readme.md").touch()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").touch()
    (tmp_path / "docs" / "deep").mkdir()
    (tmp_path / "docs" / "deep" / "nested.markdown").touch()

    # Hidden files and dirs
    (tmp_path / ".hidden_note.md").touch()
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "config.md").touch()
    (tmp_path / "docs" / ".secret.md").touch()

    return tmp_path


class TestGetProjectMarkdownFiles:
    def test_excludes_hidden_by_default(self, project_tree):
        files = get_project_markdown_files(project_tree, show_hidden=False)
        names = {f.name for f in files}
        assert "readme.md" in names
        assert "guide.md" in names
        assert "nested.markdown" in names
        assert ".hidden_note.md" not in names
        assert "config.md" not in names  # inside .obsidian
        assert ".secret.md" not in names

    def test_includes_hidden_when_enabled(self, project_tree):
        files = get_project_markdown_files(project_tree, show_hidden=True)
        names = {f.name for f in files}
        assert "readme.md" in names
        assert ".hidden_note.md" in names
        assert "config.md" in names
        assert ".secret.md" in names

    def test_reads_setting_when_show_hidden_is_none(self, project_tree):
        ctx = get_app_context()
        # Default is False
        files = get_project_markdown_files(project_tree)
        names = {f.name for f in files}
        assert ".hidden_note.md" not in names

        # Change setting
        ctx.set("files.show_hidden", True)
        files = get_project_markdown_files(project_tree)
        names = {f.name for f in files}
        assert ".hidden_note.md" in names

    def test_results_are_sorted(self, project_tree):
        files = get_project_markdown_files(project_tree, show_hidden=True)
        assert files == sorted(files)

    def test_max_depth_limits_scan(self, project_tree):
        files = get_project_markdown_files(
            project_tree, show_hidden=False, max_depth=2
        )
        names = {f.name for f in files}
        # Level 1: readme.md; Level 2: guide.md
        assert "readme.md" in names
        assert "guide.md" in names
        # Level 3: nested.markdown — should be excluded
        assert "nested.markdown" not in names

    def test_max_depth_excludes_hidden(self, project_tree):
        files = get_project_markdown_files(
            project_tree, show_hidden=False, max_depth=2
        )
        names = {f.name for f in files}
        assert ".hidden_note.md" not in names
        assert "config.md" not in names

    def test_max_depth_includes_hidden(self, project_tree):
        files = get_project_markdown_files(
            project_tree, show_hidden=True, max_depth=2
        )
        names = {f.name for f in files}
        assert ".hidden_note.md" in names
        assert "config.md" in names  # .obsidian/config.md is depth 2


# --- Default setting ---

class TestDefaultSetting:
    def test_default_is_false(self):
        ctx = get_app_context()
        assert ctx.get("files.show_hidden") is False

"""Tests for FileTreeWidget."""


import pytest
from PySide6.QtCore import Qt

from markdown_editor.markdown6.file_tree_widget import FileTreeWidget


@pytest.fixture
def tree(qtbot):
    w = FileTreeWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def project_files(tmp_path):
    """Create files and return (file_list, project_path)."""
    files = [
        tmp_path / "readme.md",
        tmp_path / "docs" / "guide.md",
        tmp_path / "docs" / "api.md",
        tmp_path / "docs" / "deep" / "nested.md",
        tmp_path / "notes" / "todo.md",
    ]
    for f in files:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
    return sorted(files), tmp_path


class TestLoadFiles:
    def test_creates_directory_nodes(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        # Top level: "docs" dir, "notes" dir, "readme.md" file
        top_names = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
        assert "docs" in top_names
        assert "notes" in top_names
        assert "readme.md" in top_names

    def test_nests_files_under_dirs(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        # Find "docs" node
        docs = None
        for i in range(tree.topLevelItemCount()):
            if tree.topLevelItem(i).text(0) == "docs":
                docs = tree.topLevelItem(i)
                break
        assert docs is not None

        child_names = [docs.child(i).text(0) for i in range(docs.childCount())]
        assert "api.md" in child_names
        assert "guide.md" in child_names
        assert "deep" in child_names  # subdirectory

    def test_all_checked_by_default(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        selected = tree.get_selected_files()
        assert len(selected) == len(files)

    def test_returns_absolute_paths(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        selected = tree.get_selected_files()
        for p in selected:
            assert p.is_absolute()


class TestSelectAllNone:
    def test_select_none(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        tree.select_none()
        assert tree.get_selected_files() == []

    def test_select_all_after_none(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        tree.select_none()
        tree.select_all()
        assert len(tree.get_selected_files()) == len(files)


class TestCheckboxPropagation:
    def test_uncheck_dir_unchecks_children(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        # Find "docs" dir node and uncheck it
        docs = None
        for i in range(tree.topLevelItemCount()):
            if tree.topLevelItem(i).text(0) == "docs":
                docs = tree.topLevelItem(i)
                break
        assert docs is not None

        docs.setCheckState(0, Qt.CheckState.Unchecked)

        selected = tree.get_selected_files()
        selected_names = {p.name for p in selected}
        # docs files should be gone
        assert "guide.md" not in selected_names
        assert "api.md" not in selected_names
        assert "nested.md" not in selected_names
        # Others remain
        assert "readme.md" in selected_names
        assert "todo.md" in selected_names

    def test_uncheck_single_file_makes_parent_partial(self, tree, project_files):
        files, root = project_files
        tree.load_files(files, root)

        # Find "docs" dir and uncheck one child
        docs = None
        for i in range(tree.topLevelItemCount()):
            if tree.topLevelItem(i).text(0) == "docs":
                docs = tree.topLevelItem(i)
                break

        # Find a file child (not the "deep" dir)
        for i in range(docs.childCount()):
            child = docs.child(i)
            if child.text(0) == "api.md":
                child.setCheckState(0, Qt.CheckState.Unchecked)
                break

        assert docs.checkState(0) == Qt.CheckState.PartiallyChecked


class TestSelectionChangedSignal:
    def test_emits_on_select_all(self, tree, qtbot, project_files):
        files, root = project_files
        tree.load_files(files, root)
        tree.select_none()

        with qtbot.waitSignal(tree.selection_changed, timeout=1000):
            tree.select_all()

    def test_emits_on_select_none(self, tree, qtbot, project_files):
        files, root = project_files
        tree.load_files(files, root)

        with qtbot.waitSignal(tree.selection_changed, timeout=1000):
            tree.select_none()

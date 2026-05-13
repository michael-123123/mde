"""Tests for ``_FileBrowserSortProxy`` - the sort proxy for the project panel.

The proxy enforces two invariants on top of ``QFileSystemModel``:

1. Directories always appear above files, regardless of sort order.
2. Within each group (dirs / files), entries sort by either filename or
   last-modified time, ascending or descending.

These tests verify the invariants in isolation, against a temp project
on disk. They don't go through ``ProjectPanel`` - that's the next
commit's job.
"""

import os
import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileSystemModel

from markdown_editor.markdown6.project_manager import _FileBrowserSortProxy


def _wait_for_loaded(qtbot, model, path: Path):
    """``QFileSystemModel`` loads directory contents asynchronously.
    Wait until the requested directory has finished loading."""
    loaded = set()
    model.directoryLoaded.connect(loaded.add)
    try:
        model.setRootPath(str(path))
        qtbot.waitUntil(lambda: str(path) in loaded, timeout=5000)
    finally:
        model.directoryLoaded.disconnect(loaded.add)


def _names_under_root(proxy, model, root_path: Path) -> list[str]:
    """Return ``fileName`` strings under ``root_path`` in proxy order."""
    src_root = model.index(str(root_path))
    proxy_root = proxy.mapFromSource(src_root)
    out = []
    for row in range(proxy.rowCount(proxy_root)):
        proxy_idx = proxy.index(row, 0, proxy_root)
        src_idx = proxy.mapToSource(proxy_idx)
        out.append(model.fileName(src_idx))
    return out


@pytest.fixture
def mixed_project(tmp_path):
    """A project with both directories and files, easy to sort by name."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "alpha.md").write_text("a")
    (root / "zeta.md").write_text("z")
    (root / "middle.md").write_text("m")
    (root / "bravo_dir").mkdir()
    (root / "alpha_dir").mkdir()
    (root / "zulu_dir").mkdir()
    return root


@pytest.fixture
def model_and_proxy(qtbot, mixed_project):
    """Wire a QFileSystemModel up to the sort proxy and wait for load."""
    model = QFileSystemModel()
    model.setNameFilters(["*.md"])
    model.setNameFilterDisables(False)
    proxy = _FileBrowserSortProxy()
    proxy.setSourceModel(model)
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    _wait_for_loaded(qtbot, model, mixed_project)
    return model, proxy, mixed_project


class TestDirsAlwaysFirst:
    """Invariant 1: directories above files, both sort orders."""

    def test_dirs_above_files_ascending(self, model_and_proxy):
        model, proxy, root = model_and_proxy
        proxy.set_sort_key("name")
        proxy.sort(0, Qt.SortOrder.AscendingOrder)
        names = _names_under_root(proxy, model, root)
        # Find the boundary - last dir index, first file index.
        kinds = [
            "d" if model.isDir(model.index(str(root / n))) else "f"
            for n in names
        ]
        # All "d" must come before any "f".
        assert "f" not in "".join(kinds).split("d")[0] or kinds[0] == "f"
        # More directly: no "d" appears after the first "f".
        first_file = kinds.index("f") if "f" in kinds else len(kinds)
        assert "d" not in kinds[first_file:], (
            f"directories appeared after files: {list(zip(names, kinds))}"
        )

    def test_dirs_above_files_descending(self, model_and_proxy):
        """Crucial: under DESC, Qt flips ``lessThan`` results - dirs
        must still stay on top. The proxy pre-inverts the dir-vs-file
        comparison so this invariant survives the flip."""
        model, proxy, root = model_and_proxy
        proxy.set_sort_key("name")
        proxy.sort(0, Qt.SortOrder.DescendingOrder)
        names = _names_under_root(proxy, model, root)
        kinds = [
            "d" if model.isDir(model.index(str(root / n))) else "f"
            for n in names
        ]
        first_file = kinds.index("f") if "f" in kinds else len(kinds)
        assert "d" not in kinds[first_file:], (
            f"directories appeared after files under DESC: "
            f"{list(zip(names, kinds))}"
        )


class TestSortByName:
    def test_files_sorted_ascending_by_name(self, model_and_proxy):
        model, proxy, root = model_and_proxy
        proxy.set_sort_key("name")
        proxy.sort(0, Qt.SortOrder.AscendingOrder)
        names = _names_under_root(proxy, model, root)
        files = [n for n in names if not model.isDir(model.index(str(root / n)))]
        assert files == ["alpha.md", "middle.md", "zeta.md"]

    def test_files_sorted_descending_by_name(self, model_and_proxy):
        model, proxy, root = model_and_proxy
        proxy.set_sort_key("name")
        proxy.sort(0, Qt.SortOrder.DescendingOrder)
        names = _names_under_root(proxy, model, root)
        files = [n for n in names if not model.isDir(model.index(str(root / n)))]
        assert files == ["zeta.md", "middle.md", "alpha.md"]

    def test_dirs_sorted_among_themselves(self, model_and_proxy):
        model, proxy, root = model_and_proxy
        proxy.set_sort_key("name")
        proxy.sort(0, Qt.SortOrder.AscendingOrder)
        names = _names_under_root(proxy, model, root)
        dirs = [n for n in names if model.isDir(model.index(str(root / n)))]
        assert dirs == ["alpha_dir", "bravo_dir", "zulu_dir"]


class TestSortByMtime:
    @pytest.fixture
    def mtime_project(self, qtbot, tmp_path):
        """Three files with controlled mtimes: A oldest, B middle, C newest."""
        root = tmp_path / "mtime_proj"
        root.mkdir()
        a = root / "a_oldest.md"
        b = root / "b_middle.md"
        c = root / "c_newest.md"
        a.write_text("a")
        b.write_text("b")
        c.write_text("c")
        now = time.time()
        # Use os.utime to set explicit, well-separated mtimes - cross-
        # platform (works on Linux/macOS/Windows).
        os.utime(a, (now - 3000, now - 3000))
        os.utime(b, (now - 2000, now - 2000))
        os.utime(c, (now - 1000, now - 1000))

        model = QFileSystemModel()
        model.setNameFilters(["*.md"])
        model.setNameFilterDisables(False)
        proxy = _FileBrowserSortProxy()
        proxy.setSourceModel(model)
        _wait_for_loaded(qtbot, model, root)
        return model, proxy, root

    def test_ascending_oldest_first(self, mtime_project):
        model, proxy, root = mtime_project
        proxy.set_sort_key("mtime")
        proxy.sort(0, Qt.SortOrder.AscendingOrder)
        names = _names_under_root(proxy, model, root)
        files = [n for n in names if not model.isDir(model.index(str(root / n)))]
        assert files == ["a_oldest.md", "b_middle.md", "c_newest.md"]

    def test_descending_newest_first(self, mtime_project):
        model, proxy, root = mtime_project
        proxy.set_sort_key("mtime")
        proxy.sort(0, Qt.SortOrder.DescendingOrder)
        names = _names_under_root(proxy, model, root)
        files = [n for n in names if not model.isDir(model.index(str(root / n)))]
        assert files == ["c_newest.md", "b_middle.md", "a_oldest.md"]


class TestKeyChangeReorders:
    """Switching the key without re-calling ``sort`` should still reorder
    - the proxy invalidates itself on key change."""

    def test_switch_name_to_mtime_reorders(self, qtbot, tmp_path):
        root = tmp_path / "p"
        root.mkdir()
        # Names sorted alphabetically differ from mtime order.
        alpha = root / "alpha.md"
        zeta = root / "zeta.md"
        alpha.write_text("a")
        zeta.write_text("z")
        now = time.time()
        # zeta OLDER, alpha NEWER so mtime-ascending is the OPPOSITE
        # of name-ascending - that's what makes the test discriminate
        # the two sort keys.
        os.utime(zeta, (now - 5000, now - 5000))
        os.utime(alpha, (now - 1000, now - 1000))

        model = QFileSystemModel()
        model.setNameFilters(["*.md"])
        model.setNameFilterDisables(False)
        proxy = _FileBrowserSortProxy()
        proxy.setSourceModel(model)
        proxy.sort(0, Qt.SortOrder.AscendingOrder)
        _wait_for_loaded(qtbot, model, root)

        proxy.set_sort_key("name")
        names_by_name = _names_under_root(proxy, model, root)
        assert names_by_name == ["alpha.md", "zeta.md"]

        proxy.set_sort_key("mtime")  # zeta is older -> should come first ASC
        names_by_mtime = _names_under_root(proxy, model, root)
        assert names_by_mtime == ["zeta.md", "alpha.md"]

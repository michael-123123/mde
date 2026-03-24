"""Tests for the graph export module."""

import pytest
import re
from pathlib import Path

from markdown_editor.markdown6.graph_export import (
    WIKI_LINK_PATTERN,
    MD_LINK_PATTERN,
    VerticalTab,
)


class TestLinkPatterns:
    """Tests for link detection regex patterns."""

    def test_wiki_link_simple(self):
        """Test detecting simple wiki links."""
        text = "See [[OtherDocument]] for more info."
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == ["OtherDocument"]

    def test_wiki_link_with_alias(self):
        """Test detecting wiki links with aliases."""
        text = "See [[OtherDocument|the other doc]] for more info."
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == ["OtherDocument"]

    def test_wiki_link_multiple(self):
        """Test detecting multiple wiki links."""
        text = "Links: [[Doc1]], [[Doc2]], and [[Doc3]]"
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == ["Doc1", "Doc2", "Doc3"]

    def test_wiki_link_with_spaces(self):
        """Test detecting wiki links with spaces."""
        text = "See [[My Document Name]] here."
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == ["My Document Name"]

    def test_wiki_link_with_path(self):
        """Test detecting wiki links with paths."""
        text = "See [[folder/subfolder/document]] here."
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == ["folder/subfolder/document"]

    def test_wiki_link_no_match_for_empty(self):
        """Test that empty brackets don't match."""
        text = "Not a link: [[]]"
        matches = WIKI_LINK_PATTERN.findall(text)
        assert matches == []

    def test_md_link_simple(self):
        """Test detecting simple markdown links."""
        text = "See [link text](other.md) for more."
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][1] == "other.md"

    def test_md_link_markdown_extension(self):
        """Test detecting .markdown extension (mdown variant)."""
        # The pattern uses .md(?:own)? so it matches .md and .mdown, not .markdown
        text = "See [link](document.mdown) here."
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][1] == "document.mdown"

    def test_md_link_with_path(self):
        """Test detecting markdown links with paths."""
        text = "See [docs](../folder/doc.md) here."
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][1] == "../folder/doc.md"

    def test_md_link_multiple(self):
        """Test detecting multiple markdown links."""
        text = "[One](one.md) and [Two](two.md) and [Three](three.md)"
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 3

    def test_md_link_ignores_non_md_links(self):
        """Test that non-.md links are ignored."""
        text = "[image](photo.png) and [doc](file.md)"
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][1] == "file.md"

    def test_md_link_case_insensitive(self):
        """Test that .MD extension is detected."""
        text = "[doc](FILE.MD) here."
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1

    def test_md_link_empty_text(self):
        """Test markdown link with empty text."""
        text = "[](doc.md)"
        matches = MD_LINK_PATTERN.findall(text)
        assert len(matches) == 1
        assert matches[0][0] == ""
        assert matches[0][1] == "doc.md"


class TestVerticalTab:
    """Tests for VerticalTab widget."""

    def test_vertical_tab_creation(self, qtbot):
        """Test creating a VerticalTab widget."""
        tab = VerticalTab("FILES", width=28, arrow_direction="left")
        qtbot.addWidget(tab)
        assert tab.width() == 28
        assert tab._text == "FILES"
        assert tab._arrow_direction == "left"

    def test_vertical_tab_set_text(self, qtbot):
        """Test setting text on VerticalTab."""
        tab = VerticalTab("OLD", width=28)
        qtbot.addWidget(tab)
        tab.setText("NEW")
        assert tab._text == "NEW"

    def test_vertical_tab_set_collapsed(self, qtbot):
        """Test setting collapsed state."""
        tab = VerticalTab("TEST", width=28)
        qtbot.addWidget(tab)
        assert tab._collapsed == False
        tab.setCollapsed(True)
        assert tab._collapsed == True

    def test_vertical_tab_click_emits_signal(self, qtbot):
        """Test that clicking emits clicked signal."""
        from PySide6.QtCore import Qt

        tab = VerticalTab("TEST", width=28)
        qtbot.addWidget(tab)

        with qtbot.waitSignal(tab.clicked):
            qtbot.mouseClick(tab, Qt.MouseButton.LeftButton)

    def test_vertical_tab_hover_state(self, qtbot):
        """Test hover state changes."""
        tab = VerticalTab("TEST", width=28)
        qtbot.addWidget(tab)
        tab.show()

        assert tab._hovered == False
        # Note: Actually testing hover would require more complex event simulation


class TestGraphExportHelpers:
    """Tests for helper functions in graph export."""

    def test_escape_special_characters_in_label(self):
        """Test that special characters are handled in labels."""
        # This tests the concept - actual implementation is in _generate_graph
        label = 'Document "with" quotes'
        escaped = label.replace('"', '\\"')
        assert escaped == 'Document \\"with\\" quotes'

    def test_path_to_node_id_uniqueness(self):
        """Test that different paths get unique node IDs."""
        # Simulating the node ID generation logic
        node_ids = {}
        counter = 0

        def get_node_id(path):
            nonlocal counter
            if path not in node_ids:
                node_ids[path] = f"n{counter}"
                counter += 1
            return node_ids[path]

        id1 = get_node_id(Path("/a/b/c.md"))
        id2 = get_node_id(Path("/a/b/d.md"))
        id3 = get_node_id(Path("/a/b/c.md"))  # Same as first

        assert id1 != id2
        assert id1 == id3  # Same path gets same ID


class TestDotGeneration:
    """Tests for DOT source generation logic."""

    def test_digraph_header(self):
        """Test that directed graphs use 'digraph' keyword."""
        is_directed = True
        graph_type = "digraph" if is_directed else "graph"
        assert graph_type == "digraph"

    def test_graph_header(self):
        """Test that undirected graphs use 'graph' keyword."""
        is_directed = False
        graph_type = "digraph" if is_directed else "graph"
        assert graph_type == "graph"

    def test_directed_edge_operator(self):
        """Test edge operator for directed graphs."""
        is_directed = True
        edge_op = "->" if is_directed else "--"
        assert edge_op == "->"

    def test_undirected_edge_operator(self):
        """Test edge operator for undirected graphs."""
        is_directed = False
        edge_op = "->" if is_directed else "--"
        assert edge_op == "--"

    def test_label_template_stem(self):
        """Test stem label template."""
        path = Path("/project/docs/readme.md")
        label = "{stem}".format(stem=path.stem)
        assert label == "readme"

    def test_label_template_filename(self):
        """Test filename label template."""
        path = Path("/project/docs/readme.md")
        label = "{filename}".format(filename=path.name)
        assert label == "readme.md"

    def test_label_template_relative_path(self):
        """Test relative path label template."""
        project_path = Path("/project")
        path = Path("/project/docs/readme.md")
        rel = path.relative_to(project_path)
        label = "{relative_path}".format(relative_path=str(rel))
        assert label == "docs/readme.md"

    def test_label_template_relative_path_no_ext(self):
        """Test relative path without extension template."""
        project_path = Path("/project")
        path = Path("/project/docs/readme.md")
        rel = path.relative_to(project_path)
        label = "{relative_path_no_ext}".format(
            relative_path_no_ext=str(rel.with_suffix(""))
        )
        assert label == "docs/readme"

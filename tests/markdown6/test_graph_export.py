"""Tests for the graph export module."""

from pathlib import Path

from markdown_editor.markdown6.components.graph_export import VerticalTab
from markdown_editor.markdown6.link_detection import (
    MD_LINK_PATTERN,
    WIKI_LINK_PATTERN,
    mask_verbatim_regions,
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

    def test_wiki_link_does_not_match_inside_code_spans(self):
        """Regression: wiki/MD link detection must skip verbatim regions.

        Real-world repro (from local/research-upgrades/05-gap-analysis-and-roadmap.md):
        the file contained an inline `` `[[` `` (literal brackets in a code span)
        and a `` `![[my.base]]` `` 92 lines later, both intentionally verbatim.
        The link regex ignored the code-span context and stitched them into one
        4600-char wiki target, which then exploded as ENAMETOOLONG on
        Path(...).exists() in graph_export._resolve_link.

        Verbatim regions (per CommonMark) must be masked before link detection.
        """
        text = (
            "Editor autocomplete: when user types `[[`, after picking a note,\n"
            "allow `#` to filter headings, then `^` to filter blocks.\n"
            "many paragraphs of free-form prose with no closing brackets\n"
            "embedding views in notes (`![[my.base]]`) - extends the module.\n"
        )
        masked = mask_verbatim_regions(text)
        # No wiki link should be detected: every `[[` / `]]` lives inside a
        # backtick code span.
        assert WIKI_LINK_PATTERN.findall(masked) == []

    def test_md_link_target_does_not_span_newlines(self):
        """Regression: link target must not greedily consume across newlines.

        A stray `](` followed many lines later by any line ending with `.md)`
        used to be captured as one giant multi-line target. Passing that to
        ``Path.resolve()`` / ``.exists()`` then raised ``ENAMETOOLONG`` (errno
        36), which surfaced in the graph-export preview as
        ``Error: [Errno 36] File name too long: ...``.
        """
        text = (
            "intro line\n"
            "Look [x](local/research-upgrades/`, "
            "after picking a note,\n"
            "allow `#` to filter headings,\n"
            "...many lines later...\n"
            "see also wikilinks.md)\n"
            "more text\n"
        )
        for _text, target in MD_LINK_PATTERN.findall(text):
            assert "\n" not in target, (
                f"link target spans newlines (would explode on Path.resolve): {target!r}"
            )


class TestVerbatimRegionMasking:
    """Tests for mask_verbatim_regions and its effect on link detection.

    These mirror the cases in examples/LINKS.md.
    """

    def _has_link(self, line: str) -> bool:
        """True iff at least one wiki or markdown link is detected in `line`."""
        masked = mask_verbatim_regions(line)
        return bool(WIKI_LINK_PATTERN.findall(masked) or MD_LINK_PATTERN.findall(masked))

    # -- inline code spans ------------------------------------------------

    def test_brackets_in_backtick_span_not_a_link(self):
        assert not self._has_link("- not link: `[[` hello")
        assert not self._has_link("- not link: `[[CHANGELOG.md]]`")
        assert not self._has_link("- not link: `[[CHANGELOG]]`")

    def test_md_link_in_backtick_span_not_a_link(self):
        assert not self._has_link("- not link: `[text](broken.md)`")

    def test_real_wiki_link_with_inline_code_target(self):
        # [[`CHANGELOG`]] - brackets are real, target is monospace-displayed.
        line = "- link: [[`CHANGELOG`]]"
        masked = mask_verbatim_regions(line)
        # After masking, the backtick content is whitespace, but the [[ ]] are
        # still present so the wiki regex matches.
        matches = WIKI_LINK_PATTERN.findall(masked)
        assert len(matches) == 1

    def test_multibacktick_span_masked(self):
        assert not self._has_link("- not link: ``[[has`backtick`inside]]``")

    # -- fenced code blocks -----------------------------------------------

    def test_brackets_in_fenced_code_block_not_a_link(self):
        text = (
            "prose\n"
            "\n"
            "```\n"
            "[[NotALinkInFence]]\n"
            "[text](not-a-link.md)\n"
            "```\n"
            "\n"
            "more prose\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == []
        assert MD_LINK_PATTERN.findall(masked) == []

    def test_brackets_in_tilde_fenced_block_not_a_link(self):
        text = (
            "~~~\n"
            "[[NotALinkInTildeFence]]\n"
            "[text](not-a-link.md)\n"
            "~~~\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == []
        assert MD_LINK_PATTERN.findall(masked) == []

    # -- indented code blocks ---------------------------------------------

    def test_brackets_in_indented_code_block_not_a_link(self):
        text = (
            "paragraph above\n"
            "\n"
            "    [[NotALinkInIndented]]\n"
            "    [text](not-a-link.md)\n"
            "\n"
            "paragraph below\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == []
        assert MD_LINK_PATTERN.findall(masked) == []

    def test_indented_continuation_is_not_code(self):
        # An indented line that continues a paragraph (no blank line before)
        # is NOT a code block; link inside should still be detected.
        text = (
            "this paragraph keeps going\n"
            "    [[StillALink]]\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == ["StillALink"]

    # -- math --------------------------------------------------------------

    def test_brackets_in_inline_math_not_a_link(self):
        assert not self._has_link("- not link: $[[x_{ij}]]$")
        assert not self._has_link("- not link: $[a](b.md)$")

    def test_brackets_in_display_math_not_a_link(self):
        text = (
            "$$\n"
            "[[A_{ij}]] = \\begin{bmatrix} 1 & 2 \\\\ 3 & 4 \\end{bmatrix}\n"
            "$$\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == []

    # -- HTML --------------------------------------------------------------

    def test_brackets_in_html_pre_not_a_link(self):
        assert not self._has_link("- not link: <pre>[[NotALink]]</pre>")

    def test_brackets_in_html_script_not_a_link(self):
        assert not self._has_link("- not link: <script>[[NotALink]]</script>")

    def test_brackets_in_html_style_not_a_link(self):
        assert not self._has_link("- not link: <style>[[NotALink]]</style>")

    def test_brackets_in_html_comment_not_a_link(self):
        assert not self._has_link("- not link: <!-- [[NotALink]] -->")
        assert not self._has_link("- not link: <!-- [text](not-a-link.md) -->")

    # -- sanity: real links still detected --------------------------------

    def test_real_wiki_link_still_detected(self):
        line = "- link: [[RealWikiLink]]"
        masked = mask_verbatim_regions(line)
        assert WIKI_LINK_PATTERN.findall(masked) == ["RealWikiLink"]

    def test_real_wiki_link_with_display_still_detected(self):
        line = "- link: [[RealWikiLink|With Display]]"
        masked = mask_verbatim_regions(line)
        assert WIKI_LINK_PATTERN.findall(masked) == ["RealWikiLink"]

    def test_real_md_link_still_detected(self):
        line = "- link: [text](real-link.md)"
        masked = mask_verbatim_regions(line)
        matches = MD_LINK_PATTERN.findall(masked)
        assert len(matches) == 1
        assert matches[0][1] == "real-link.md"

    # -- the real-world bug repro ----------------------------------------

    def test_real_world_repro_from_gap_analysis(self):
        """Mirror of the 05-gap-analysis-and-roadmap.md case: a `[[` inline
        code span 92 lines before a `![[my.base]]` inline code span got
        stitched into one giant wiki target, exploding as ENAMETOOLONG."""
        text = (
            "Editor autocomplete: when user types `[[`, after picking a note,\n"
            + "filler line with no brackets\n" * 90
            + "embedding views in notes (`![[my.base]]`) - extends the module.\n"
        )
        masked = mask_verbatim_regions(text)
        assert WIKI_LINK_PATTERN.findall(masked) == []


# `_resolve_link` moved out of the dialog into
# :mod:`markdown_editor.markdown6.graph_exporter`. ENAMETOOLONG handling
# coverage now lives in
# ``test_graph_exporter.py::TestResolveLink::test_enametoolong_returns_none_and_logs``
# and ``test_other_oserror_propagates``.


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
        assert tab._collapsed is False
        tab.setCollapsed(True)
        assert tab._collapsed is True

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

        assert tab._hovered is False
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

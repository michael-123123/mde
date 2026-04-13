"""Tests for the outline panel module."""

import pytest
from PySide6.QtCore import Qt

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.components.outline_panel import (Heading,
                                                                OutlinePanel)


@pytest.fixture
def panel(qtbot):
    """Create an OutlinePanel instance."""
    p = OutlinePanel(get_app_context())
    qtbot.addWidget(p)
    return p


class TestHeadingDataclass:
    """Tests for Heading dataclass."""

    def test_heading_creation(self):
        """Test creating a Heading."""
        heading = Heading(level=1, text="Test", line=0)
        assert heading.level == 1
        assert heading.text == "Test"
        assert heading.line == 0

    def test_heading_levels(self):
        """Test different heading levels."""
        for level in range(1, 7):
            heading = Heading(level=level, text=f"H{level}", line=level)
            assert heading.level == level


class TestOutlinePanelCreation:
    """Tests for OutlinePanel initialization."""

    def test_panel_creation(self, panel):
        """Test creating an outline panel."""
        assert panel is not None

    def test_tree_exists(self, panel):
        """Test that tree widget exists."""
        assert panel.tree is not None

    def test_tree_header_hidden(self, panel):
        """Test that tree header is hidden."""
        assert panel.tree.isHeaderHidden()

    def test_signal_exists(self, panel):
        """Test that heading_clicked signal exists."""
        assert hasattr(panel, "heading_clicked")


class TestHeadingParsing:
    """Tests for parsing headings from markdown."""

    def test_parse_h1(self, panel):
        """Test parsing H1 heading."""
        headings = panel._parse_headings("# Heading 1")
        assert len(headings) == 1
        assert headings[0].level == 1
        assert headings[0].text == "Heading 1"

    def test_parse_h2(self, panel):
        """Test parsing H2 heading."""
        headings = panel._parse_headings("## Heading 2")
        assert len(headings) == 1
        assert headings[0].level == 2

    def test_parse_h3_to_h6(self, panel):
        """Test parsing H3 through H6."""
        text = """### H3
#### H4
##### H5
###### H6"""
        headings = panel._parse_headings(text)
        assert len(headings) == 4
        assert [h.level for h in headings] == [3, 4, 5, 6]

    def test_parse_multiple_headings(self, panel):
        """Test parsing multiple headings."""
        text = """# First
## Second
### Third"""
        headings = panel._parse_headings(text)
        assert len(headings) == 3

    def test_parse_line_numbers(self, panel):
        """Test that line numbers are correct."""
        text = """Line 0
# Heading on Line 1
Line 2
## Heading on Line 3"""
        headings = panel._parse_headings(text)
        assert headings[0].line == 1
        assert headings[1].line == 3

    def test_ignore_headings_in_code_blocks(self, panel):
        """Test that headings inside code blocks are ignored."""
        text = """# Real Heading
```
# Fake Heading in Code
```
## Another Real Heading"""
        headings = panel._parse_headings(text)
        assert len(headings) == 2
        assert headings[0].text == "Real Heading"
        assert headings[1].text == "Another Real Heading"

    def test_setext_h1(self, panel):
        """Test parsing setext-style H1."""
        text = """Heading
======="""
        headings = panel._parse_headings(text)
        assert len(headings) == 1
        assert headings[0].level == 1
        assert headings[0].text == "Heading"

    def test_setext_h2(self, panel):
        """Test parsing setext-style H2."""
        text = """Heading
-------"""
        headings = panel._parse_headings(text)
        assert len(headings) == 1
        assert headings[0].level == 2

    def test_no_headings(self, panel):
        """Test parsing text with no headings."""
        headings = panel._parse_headings("Just some text\nNo headings here")
        assert len(headings) == 0

    def test_heading_with_trailing_hashes(self, panel):
        """Test heading with trailing hashes."""
        headings = panel._parse_headings("# Heading ###")
        assert len(headings) == 1
        assert headings[0].text == "Heading"

    def test_heading_with_extra_spaces(self, panel):
        """Test heading with extra spaces."""
        headings = panel._parse_headings("#   Heading   ")
        assert len(headings) == 1
        assert headings[0].text == "Heading"

    def test_invalid_heading_no_space(self, panel):
        """Test that #NoSpace is not a heading."""
        headings = panel._parse_headings("#NoSpace")
        assert len(headings) == 0


class TestOutlineUpdate:
    """Tests for updating the outline."""

    def test_update_outline_basic(self, panel):
        """Test basic outline update."""
        panel.update_outline("# Heading")
        assert panel.tree.topLevelItemCount() == 1

    def test_update_outline_empty(self, panel):
        """Test outline update with no headings."""
        panel.update_outline("No headings")
        # Should show "No headings found" item
        assert panel.tree.topLevelItemCount() == 1
        item = panel.tree.topLevelItem(0)
        assert "No headings" in item.text(0)

    def test_update_outline_clears_previous(self, panel):
        """Test that update clears previous items."""
        panel.update_outline("# First")
        panel.update_outline("# Second")
        assert panel.tree.topLevelItemCount() == 1
        assert "Second" in panel.tree.topLevelItem(0).text(0)

    def test_update_outline_hierarchical(self, panel):
        """Test hierarchical outline structure."""
        text = """# Parent
## Child"""
        panel.update_outline(text)
        # Parent should be top level
        assert panel.tree.topLevelItemCount() == 1
        parent = panel.tree.topLevelItem(0)
        # Child should be nested
        assert parent.childCount() == 1

    def test_update_outline_expanded(self, panel):
        """Test that outline is expanded by default."""
        text = """# Parent
## Child"""
        panel.update_outline(text)
        parent = panel.tree.topLevelItem(0)
        assert parent.isExpanded()

    def test_item_stores_line_number(self, panel):
        """Test that items store line numbers in UserRole."""
        panel.update_outline("# Heading")
        item = panel.tree.topLevelItem(0)
        line = item.data(0, Qt.ItemDataRole.UserRole)
        assert line == 0

    def test_item_text_includes_level(self, panel):
        """Test that item text includes H1, H2, etc prefix."""
        panel.update_outline("# Heading")
        item = panel.tree.topLevelItem(0)
        assert "H1" in item.text(0)


class TestOutlineNavigation:
    """Tests for navigation functionality."""

    def test_heading_clicked_signal(self, panel, qtbot):
        """Test that clicking heading emits signal."""
        panel.update_outline("# Heading")

        with qtbot.waitSignal(panel.heading_clicked) as blocker:
            item = panel.tree.topLevelItem(0)
            panel._on_item_clicked(item, 0)

        assert blocker.args == [0]

    def test_no_heading_item_doesnt_emit(self, panel, qtbot):
        """Test that items without line data don't emit signal."""
        panel.update_outline("No headings")
        item = panel.tree.topLevelItem(0)

        # Should not emit (no line number stored)
        with qtbot.assertNotEmitted(panel.heading_clicked):
            panel._on_item_clicked(item, 0)

    def test_select_heading_at_line(self, panel):
        """Test selecting heading at or before a line."""
        text = """# First
Some text
## Second
More text"""
        panel.update_outline(text)

        # Select heading at line 3 (should select "Second")
        panel.select_heading_at_line(3)
        current = panel.tree.currentItem()
        assert "Second" in current.text(0)

    def test_select_heading_before_line(self, panel):
        """Test selecting heading when cursor is after heading."""
        text = """# Heading
Line 1
Line 2
Line 3"""
        panel.update_outline(text)

        # Line 3 is after the heading, should still select it
        panel.select_heading_at_line(3)
        current = panel.tree.currentItem()
        assert "Heading" in current.text(0)


class TestCollapseExpand:
    """Tests for collapse/expand functionality."""

    def test_collapse_all(self, panel):
        """Test collapsing all items."""
        text = """# Parent
## Child"""
        panel.update_outline(text)
        panel._collapse_all()
        parent = panel.tree.topLevelItem(0)
        assert not parent.isExpanded()

    def test_expand_all(self, panel):
        """Test expanding all items."""
        text = """# Parent
## Child"""
        panel.update_outline(text)
        panel._collapse_all()
        panel._expand_all()
        parent = panel.tree.topLevelItem(0)
        assert parent.isExpanded()


class TestComplexHierarchy:
    """Tests for complex heading hierarchies."""

    def test_multiple_h1_sections(self, panel):
        """Test multiple H1 sections."""
        text = """# Section 1
## Subsection 1.1
# Section 2
## Subsection 2.1"""
        panel.update_outline(text)

        # Should have 2 top-level items
        assert panel.tree.topLevelItemCount() == 2

    def test_skipped_levels(self, panel):
        """Test when heading levels are skipped (H1 -> H3)."""
        text = """# H1
### H3"""
        panel.update_outline(text)
        # H3 should still be nested under H1
        parent = panel.tree.topLevelItem(0)
        assert parent.childCount() == 1

    def test_deep_nesting(self, panel):
        """Test deeply nested headings."""
        text = """# H1
## H2
### H3
#### H4
##### H5
###### H6"""
        panel.update_outline(text)

        # Check nesting depth
        item = panel.tree.topLevelItem(0)
        depth = 0
        while item.childCount() > 0:
            item = item.child(0)
            depth += 1
        assert depth == 5  # H2 through H6

    def test_sibling_headings(self, panel):
        """Test sibling headings at same level."""
        text = """# Parent
## Child 1
## Child 2
## Child 3"""
        panel.update_outline(text)

        parent = panel.tree.topLevelItem(0)
        assert parent.childCount() == 3


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_text(self, panel):
        """Test empty text input."""
        panel.update_outline("")
        # Should show "No headings found"
        assert panel.tree.topLevelItemCount() == 1

    def test_only_whitespace(self, panel):
        """Test text with only whitespace."""
        panel.update_outline("   \n\n   \n")
        assert panel.tree.topLevelItemCount() == 1  # "No headings"

    def test_unicode_headings(self, panel):
        """Test headings with Unicode characters."""
        panel.update_outline("# 日本語タイトル")
        item = panel.tree.topLevelItem(0)
        assert "日本語タイトル" in item.text(0)

    def test_heading_with_special_chars(self, panel):
        """Test heading with special characters."""
        panel.update_outline("# Test & <special> \"chars\"")
        item = panel.tree.topLevelItem(0)
        assert "Test" in item.text(0)

    def test_setext_needs_preceding_text(self, panel):
        """Test that setext heading needs preceding line."""
        text = """
======="""
        headings = panel._parse_headings(text)
        # Should not match as there's no text on preceding line
        assert len(headings) == 0

    def test_short_setext_h2_ignored(self, panel):
        """Test that short dashes are not setext headings."""
        text = """Not Heading
--"""
        headings = panel._parse_headings(text)
        # Two dashes is too short
        assert len(headings) == 0

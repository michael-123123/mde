"""Tests for the snippets module."""

import pytest
from datetime import datetime

from markdown_editor.markdown6.snippets import (
    Snippet,
    SnippetManager,
    DEFAULT_SNIPPETS,
    get_snippet_manager,
)


@pytest.fixture
def snippet_manager():
    """Create a fresh SnippetManager instance."""
    return SnippetManager()


class TestSnippet:
    """Tests for Snippet dataclass."""

    def test_snippet_creation(self):
        """Test creating a snippet."""
        snippet = Snippet(
            trigger="/test",
            name="Test Snippet",
            content="Test content",
            description="A test snippet",
        )
        assert snippet.trigger == "/test"
        assert snippet.name == "Test Snippet"
        assert snippet.content == "Test content"
        assert snippet.description == "A test snippet"

    def test_snippet_default_values(self):
        """Test snippet default values."""
        snippet = Snippet(trigger="/test", name="Test", content="content")
        assert snippet.description == ""
        assert snippet.cursor_offset == 0


class TestDefaultSnippets:
    """Tests for default snippets."""

    def test_default_snippets_not_empty(self):
        """Test that default snippets list is not empty."""
        assert len(DEFAULT_SNIPPETS) > 0

    def test_default_snippets_have_triggers(self):
        """Test that all default snippets have triggers starting with /."""
        for snippet in DEFAULT_SNIPPETS:
            assert snippet.trigger.startswith("/")

    def test_default_snippets_have_names(self):
        """Test that all default snippets have names."""
        for snippet in DEFAULT_SNIPPETS:
            assert snippet.name

    def test_default_snippets_have_content(self):
        """Test that all default snippets have content."""
        for snippet in DEFAULT_SNIPPETS:
            assert snippet.content

    def test_common_snippets_exist(self):
        """Test that common snippets are present."""
        triggers = [s.trigger for s in DEFAULT_SNIPPETS]
        assert "/h1" in triggers
        assert "/bold" in triggers
        assert "/code" in triggers
        assert "/link" in triggers
        assert "/table" in triggers


class TestSnippetManager:
    """Tests for SnippetManager."""

    def test_loads_default_snippets(self, snippet_manager):
        """Test that manager loads default snippets."""
        assert len(snippet_manager.snippets) == len(DEFAULT_SNIPPETS)

    def test_get_snippet_by_trigger(self, snippet_manager):
        """Test getting a snippet by trigger."""
        snippet = snippet_manager.get_snippet("/h1")
        assert snippet is not None
        assert snippet.name == "Heading 1"

    def test_get_nonexistent_snippet(self, snippet_manager):
        """Test getting a nonexistent snippet returns None."""
        snippet = snippet_manager.get_snippet("/nonexistent")
        assert snippet is None

    def test_get_all_snippets(self, snippet_manager):
        """Test getting all snippets."""
        all_snippets = snippet_manager.get_all_snippets()
        assert len(all_snippets) == len(DEFAULT_SNIPPETS)

    def test_get_matching_snippets_by_trigger(self, snippet_manager):
        """Test getting matching snippets by trigger prefix."""
        matches = snippet_manager.get_matching_snippets("/h")
        assert len(matches) >= 3  # /h1, /h2, /h3

    def test_get_matching_snippets_by_name(self, snippet_manager):
        """Test getting matching snippets by name."""
        matches = snippet_manager.get_matching_snippets("heading")
        assert len(matches) >= 3

    def test_get_matching_snippets_empty_prefix(self, snippet_manager):
        """Test that empty prefix returns empty list."""
        matches = snippet_manager.get_matching_snippets("")
        assert matches == []

    def test_add_snippet(self, snippet_manager):
        """Test adding a custom snippet."""
        custom = Snippet(trigger="/custom", name="Custom", content="custom content")
        snippet_manager.add_snippet(custom)
        assert snippet_manager.get_snippet("/custom") == custom

    def test_remove_snippet(self, snippet_manager):
        """Test removing a snippet."""
        snippet_manager.remove_snippet("/h1")
        assert snippet_manager.get_snippet("/h1") is None

    def test_remove_nonexistent_snippet(self, snippet_manager):
        """Test removing a nonexistent snippet doesn't raise."""
        snippet_manager.remove_snippet("/nonexistent")  # Should not raise


class TestSnippetExpansion:
    """Tests for snippet expansion."""

    def test_expand_simple_snippet(self, snippet_manager):
        """Test expanding a simple snippet without placeholders."""
        snippet = Snippet(trigger="/hr", name="HR", content="---\n")
        content, start, end = snippet_manager.expand_snippet(snippet)
        assert content == "---\n"
        assert start == -1
        assert end == -1

    def test_expand_snippet_with_placeholder(self, snippet_manager):
        """Test expanding a snippet with a placeholder."""
        snippet = Snippet(trigger="/bold", name="Bold", content="**${1:text}**")
        content, start, end = snippet_manager.expand_snippet(snippet)
        assert content == "**text**"
        assert start == 2  # Position of "text"
        assert end == 6  # End of "text"

    def test_expand_snippet_with_multiple_placeholders(self, snippet_manager):
        """Test expanding a snippet with multiple placeholders."""
        snippet = Snippet(
            trigger="/link",
            name="Link",
            content="[${1:text}](${2:url})"
        )
        content, start, end = snippet_manager.expand_snippet(snippet)
        assert content == "[text](url)"
        assert start == 1  # First placeholder position
        assert end == 5  # End of first placeholder

    def test_expand_snippet_with_date_variable(self, snippet_manager):
        """Test expanding a snippet with DATE variable."""
        snippet = Snippet(
            trigger="/date",
            name="Date",
            content="Date: ${DATE}"
        )
        content, start, end = snippet_manager.expand_snippet(snippet)
        today = datetime.now().strftime("%Y-%m-%d")
        assert content == f"Date: {today}"

    def test_expand_snippet_with_custom_variables(self, snippet_manager):
        """Test expanding a snippet with custom variables."""
        snippet = Snippet(
            trigger="/custom",
            name="Custom",
            content="Hello ${NAME}!"
        )
        content, start, end = snippet_manager.expand_snippet(
            snippet,
            variables={"NAME": "World"}
        )
        assert content == "Hello World!"

    def test_expand_snippet_preserves_order(self, snippet_manager):
        """Test that placeholder numbering determines selection order."""
        snippet = Snippet(
            trigger="/test",
            name="Test",
            content="${2:second} ${1:first} ${3:third}"
        )
        content, start, end = snippet_manager.expand_snippet(snippet)
        assert content == "second first third"
        # First placeholder (${1:first}) should be selected
        assert start == 7  # Position of "first"
        assert end == 12  # End of "first"


class TestGetSnippetManager:
    """Tests for global snippet manager."""

    def test_get_snippet_manager_returns_instance(self):
        """Test that get_snippet_manager returns a SnippetManager."""
        manager = get_snippet_manager()
        assert isinstance(manager, SnippetManager)

    def test_get_snippet_manager_returns_same_instance(self):
        """Test that get_snippet_manager returns the same instance."""
        manager1 = get_snippet_manager()
        manager2 = get_snippet_manager()
        assert manager1 is manager2

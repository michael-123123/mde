"""Snippet system for quick insertion of common markdown patterns."""

import re
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QWidget

from fun.markdown6.searchable_popup import SearchablePopup


@dataclass
class Snippet:
    """Represents a text snippet."""
    trigger: str
    name: str
    content: str
    description: str = ""
    cursor_offset: int = 0  # Offset from end of content for cursor placement


# Default snippets
DEFAULT_SNIPPETS = [
    Snippet(
        trigger="/h1",
        name="Heading 1",
        content="# ${1:Heading}\n",
        description="Insert H1 heading",
    ),
    Snippet(
        trigger="/h2",
        name="Heading 2",
        content="## ${1:Heading}\n",
        description="Insert H2 heading",
    ),
    Snippet(
        trigger="/h3",
        name="Heading 3",
        content="### ${1:Heading}\n",
        description="Insert H3 heading",
    ),
    Snippet(
        trigger="/bold",
        name="Bold Text",
        content="**${1:text}**",
        description="Bold text",
    ),
    Snippet(
        trigger="/italic",
        name="Italic Text",
        content="*${1:text}*",
        description="Italic text",
    ),
    Snippet(
        trigger="/code",
        name="Inline Code",
        content="`${1:code}`",
        description="Inline code",
    ),
    Snippet(
        trigger="/codeblock",
        name="Code Block",
        content="```${1:language}\n${2:code}\n```\n",
        description="Fenced code block",
    ),
    Snippet(
        trigger="/python",
        name="Python Code Block",
        content="```python\n${1:code}\n```\n",
        description="Python code block",
    ),
    Snippet(
        trigger="/js",
        name="JavaScript Code Block",
        content="```javascript\n${1:code}\n```\n",
        description="JavaScript code block",
    ),
    Snippet(
        trigger="/link",
        name="Link",
        content="[${1:text}](${2:url})",
        description="Markdown link",
    ),
    Snippet(
        trigger="/img",
        name="Image",
        content="![${1:alt text}](${2:url})",
        description="Markdown image",
    ),
    Snippet(
        trigger="/table",
        name="Table (3x3)",
        content="""| Header 1 | Header 2 | Header 3 |
| -------- | -------- | -------- |
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |
| Cell 7   | Cell 8   | Cell 9   |
""",
        description="3x3 markdown table",
    ),
    Snippet(
        trigger="/table2",
        name="Table (2x2)",
        content="""| Header 1 | Header 2 |
| -------- | -------- |
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
""",
        description="2x2 markdown table",
    ),
    Snippet(
        trigger="/ul",
        name="Unordered List",
        content="- ${1:Item 1}\n- ${2:Item 2}\n- ${3:Item 3}\n",
        description="Unordered list",
    ),
    Snippet(
        trigger="/ol",
        name="Ordered List",
        content="1. ${1:Item 1}\n2. ${2:Item 2}\n3. ${3:Item 3}\n",
        description="Ordered list",
    ),
    Snippet(
        trigger="/task",
        name="Task List",
        content="- [ ] ${1:Task 1}\n- [ ] ${2:Task 2}\n- [ ] ${3:Task 3}\n",
        description="Task/checkbox list",
    ),
    Snippet(
        trigger="/quote",
        name="Blockquote",
        content="> ${1:Quote text}\n",
        description="Blockquote",
    ),
    Snippet(
        trigger="/hr",
        name="Horizontal Rule",
        content="\n---\n\n",
        description="Horizontal rule",
    ),
    Snippet(
        trigger="/note",
        name="Note Callout",
        content="> [!NOTE]\n> ${1:Note content}\n",
        description="Note callout/admonition",
    ),
    Snippet(
        trigger="/warning",
        name="Warning Callout",
        content="> [!WARNING]\n> ${1:Warning content}\n",
        description="Warning callout/admonition",
    ),
    Snippet(
        trigger="/tip",
        name="Tip Callout",
        content="> [!TIP]\n> ${1:Tip content}\n",
        description="Tip callout/admonition",
    ),
    Snippet(
        trigger="/important",
        name="Important Callout",
        content="> [!IMPORTANT]\n> ${1:Important content}\n",
        description="Important callout/admonition",
    ),
    Snippet(
        trigger="/caution",
        name="Caution Callout",
        content="> [!CAUTION]\n> ${1:Caution content}\n",
        description="Caution callout/admonition",
    ),
    Snippet(
        trigger="/math",
        name="Math Block",
        content="$$\n${1:equation}\n$$\n",
        description="LaTeX math block",
    ),
    Snippet(
        trigger="/mermaid",
        name="Mermaid Diagram",
        content="""```mermaid
graph TD
    A[${1:Start}] --> B[${2:Process}]
    B --> C[${3:End}]
```
""",
        description="Mermaid flowchart diagram",
    ),
    Snippet(
        trigger="/sequence",
        name="Mermaid Sequence Diagram",
        content="""```mermaid
sequenceDiagram
    participant A as ${1:Actor A}
    participant B as ${2:Actor B}
    A->>B: ${3:Message}
    B-->>A: ${4:Response}
```
""",
        description="Mermaid sequence diagram",
    ),
    Snippet(
        trigger="/frontmatter",
        name="YAML Front Matter",
        content="""---
title: ${1:Title}
date: ${2:DATE}
tags: [${3:tag1, tag2}]
---

""",
        description="YAML front matter",
    ),
    Snippet(
        trigger="/toc",
        name="Table of Contents",
        content="[TOC]\n\n",
        description="Table of contents marker",
    ),
    Snippet(
        trigger="/details",
        name="Collapsible Details",
        content="""<details>
<summary>${1:Summary}</summary>

${2:Content}

</details>
""",
        description="Collapsible details section",
    ),
    Snippet(
        trigger="/footnote",
        name="Footnote",
        content="[^${1:note}]: ${2:Footnote content}",
        description="Footnote reference",
    ),
    Snippet(
        trigger="/abbr",
        name="Abbreviation",
        content="*[${1:ABBR}]: ${2:Full text}",
        description="Abbreviation definition",
    ),
]


class SnippetManager:
    """Manages snippets and their triggers."""

    def __init__(self):
        self.snippets: dict[str, Snippet] = {}
        self._load_default_snippets()

    def _load_default_snippets(self):
        """Load the default snippets."""
        for snippet in DEFAULT_SNIPPETS:
            self.snippets[snippet.trigger] = snippet

    def get_snippet(self, trigger: str) -> Snippet | None:
        """Get a snippet by its trigger."""
        return self.snippets.get(trigger)

    def get_all_snippets(self) -> list[Snippet]:
        """Get all available snippets."""
        return list(self.snippets.values())

    def get_matching_snippets(self, prefix: str) -> list[Snippet]:
        """Get snippets matching the given prefix."""
        if not prefix:
            return []
        return [
            s for s in self.snippets.values()
            if s.trigger.startswith(prefix) or prefix in s.name.lower()
        ]

    def expand_snippet(self, snippet: Snippet, variables: dict[str, str] | None = None) -> tuple[str, int, int]:
        """Expand a snippet's content with variables.

        Returns:
            Tuple of (content, first_placeholder_start, first_placeholder_end)
            where the indices indicate the position of the first placeholder
            for cursor selection. Returns (-1, -1) if no placeholder found.
        """
        content = snippet.content

        # Replace special variables
        if variables is None:
            variables = {}

        # Add default variables
        variables.setdefault("DATE", datetime.now().strftime("%Y-%m-%d"))
        variables.setdefault("DATETIME", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        variables.setdefault("TIME", datetime.now().strftime("%H:%M:%S"))
        variables.setdefault("YEAR", datetime.now().strftime("%Y"))

        # Replace ${VAR} patterns (uppercase variables)
        for key, value in variables.items():
            content = content.replace(f"${{{key}}}", value)

        # Process numbered placeholders ${1:default}, ${2:default}, etc.
        # Find the first placeholder to select after insertion
        first_placeholder_start = -1
        first_placeholder_end = -1

        # Find all ${N:text} patterns
        placeholder_pattern = re.compile(r'\$\{(\d+):([^}]*)\}')

        def replace_placeholder(match):
            nonlocal first_placeholder_start, first_placeholder_end
            num = int(match.group(1))
            default_text = match.group(2)

            # Track position of first placeholder (${1:...})
            if num == 1 and first_placeholder_start < 0:
                # Will be calculated after all replacements
                pass

            return default_text

        # First pass: find position of first ${1:...} in original string
        first_match = placeholder_pattern.search(content)
        while first_match:
            if first_match.group(1) == '1':
                # Found ${1:...}, calculate position after replacement of earlier placeholders
                break
            first_match = placeholder_pattern.search(content, first_match.end())

        # Replace all placeholders with their default text
        result = placeholder_pattern.sub(replace_placeholder, content)

        # Calculate position of first placeholder in the result
        if first_match and first_match.group(1) == '1':
            # Count how much text before this placeholder changes
            prefix = content[:first_match.start()]
            prefix_result = placeholder_pattern.sub(lambda m: m.group(2), prefix)
            first_placeholder_start = len(prefix_result)
            first_placeholder_end = first_placeholder_start + len(first_match.group(2))

        return result, first_placeholder_start, first_placeholder_end

    def add_snippet(self, snippet: Snippet):
        """Add a custom snippet."""
        self.snippets[snippet.trigger] = snippet

    def remove_snippet(self, trigger: str):
        """Remove a snippet."""
        if trigger in self.snippets:
            del self.snippets[trigger]


class SnippetPopup(SearchablePopup):
    """A popup for selecting snippets."""

    def __init__(self, snippets: list[Snippet], parent: QWidget | None = None):
        super().__init__(parent)
        self.snippets = snippets
        self.selected_snippet: Snippet | None = None
        self._init_snippet_ui()
        self._populate_list(self.snippets)

    def _init_snippet_ui(self):
        """Initialize the snippet popup UI."""
        self.setMinimumWidth(400)
        self.setMaximumHeight(300)
        self.search_input.setPlaceholderText("Search snippets...")

    def _populate_list(self, snippets: list[Snippet]):
        """Populate the list with snippets."""
        self.list_widget.clear()
        for snippet in snippets:
            item = QListWidgetItem(f"{snippet.trigger}  -  {snippet.name}")
            item.setData(Qt.ItemDataRole.UserRole, snippet)
            item.setToolTip(snippet.description)
            self.list_widget.addItem(item)

        if snippets:
            self.list_widget.setCurrentRow(0)

    def _on_search_changed(self, text: str):
        """Filter snippets based on search text."""
        text = text.lower()
        if text:
            filtered = [
                s for s in self.snippets
                if text in s.trigger.lower() or text in s.name.lower()
            ]
        else:
            filtered = self.snippets
        self._populate_list(filtered)

    def _on_item_activated(self, item: QListWidgetItem):
        """Handle item activation."""
        self.selected_snippet = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


# Global snippet manager instance
_snippet_manager: SnippetManager | None = None


def get_snippet_manager() -> SnippetManager:
    """Get the global snippet manager instance."""
    global _snippet_manager
    if _snippet_manager is None:
        _snippet_manager = SnippetManager()
    return _snippet_manager

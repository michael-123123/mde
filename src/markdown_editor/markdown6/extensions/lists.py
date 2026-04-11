"""List-related extensions: breakless lists and task list checkboxes."""

import re
from markdown import Extension
from markdown.preprocessors import Preprocessor
from markdown.postprocessors import Postprocessor


class BreaklessListPreprocessor(Preprocessor):
    """Preprocessor to add blank lines before lists that follow non-blank lines.

    Python-Markdown requires a blank line before lists. This preprocessor
    automatically inserts blank lines to make lists work without requiring
    the user to add them manually.
    """

    # Pattern to detect list items (unordered: -, *, + or ordered: 1., 2., etc.)
    LIST_ITEM_PATTERN = re.compile(r'^(\s*)([-*+]|\d+\.)\s+\S')

    def run(self, lines):
        new_lines = []
        prev_line_blank = True
        prev_line_was_list = False

        for line in lines:
            is_list_item = bool(self.LIST_ITEM_PATTERN.match(line))
            is_blank = not line.strip()

            # If this is a list item and the previous line was not blank
            # and was not itself a list item, insert a blank line
            if is_list_item and not prev_line_blank and not prev_line_was_list:
                new_lines.append('')

            new_lines.append(line)
            prev_line_blank = is_blank
            prev_line_was_list = is_list_item

        return new_lines


class BreaklessListExtension(Extension):
    """Extension to allow lists without blank lines before them."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            BreaklessListPreprocessor(md),
            'breakless_lists',
            100  # High priority to run before other preprocessors
        )


class TaskListPostprocessor(Postprocessor):
    """Postprocessor to render task list checkboxes.

    Converts <li>[ ] and <li>[x]/[X] into styled checkbox spans.
    Safe to run after all other processing since [ ] inside <a> tags
    won't appear immediately after <li>.
    """

    UNCHECKED_PATTERN = re.compile(r'<li>\s*\[ \]')
    CHECKED_PATTERN = re.compile(r'<li>\s*\[[xX]\]')

    def run(self, text):
        text = self.UNCHECKED_PATTERN.sub(
            '<li class="task-list-item"><span class="checkbox unchecked"></span>',
            text
        )
        text = self.CHECKED_PATTERN.sub(
            '<li class="task-list-item"><span class="checkbox checked">\u2713</span>',
            text
        )
        return text


class TaskListExtension(Extension):
    """Extension for task list checkbox rendering."""

    def extendMarkdown(self, md):
        md.postprocessors.register(
            TaskListPostprocessor(md),
            'tasklist',
            23  # After graphviz_image (24)
        )


def get_tasklist_css(dark_mode: bool = False) -> str:
    """Get CSS for task list checkbox styling."""
    if dark_mode:
        border_color = "#6e7681"
        checked_bg = "#58a6ff"
        checked_color = "#0d1117"
    else:
        border_color = "#d0d7de"
        checked_bg = "#0969da"
        checked_color = "#ffffff"

    return f"""
        .task-list-item {{
            list-style-type: none;
            position: relative;
            margin-left: -1.5em;
        }}
        .checkbox {{
            display: inline-block;
            width: 1em;
            height: 1em;
            border: 1.5px solid {border_color};
            border-radius: 3px;
            margin-right: 0.4em;
            text-align: center;
            line-height: 1em;
            font-size: 0.85em;
            vertical-align: middle;
            position: relative;
            top: -0.1em;
        }}
        .checkbox.checked {{
            background-color: {checked_bg};
            border-color: {checked_bg};
            color: {checked_color};
        }}
    """

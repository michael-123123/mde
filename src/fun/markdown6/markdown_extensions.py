"""Custom Markdown extensions for callouts, wiki links, and other features."""

import re
import xml.etree.ElementTree as etree
from markdown import Extension
from markdown.preprocessors import Preprocessor
from markdown.inlinepatterns import InlineProcessor
from markdown.postprocessors import Postprocessor


class CalloutPreprocessor(Preprocessor):
    """Preprocessor for GitHub-style callouts/admonitions.

    Converts:
        > [!NOTE]
        > This is a note

    To styled HTML callout boxes.
    """

    CALLOUT_PATTERN = re.compile(
        r'^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$',
        re.IGNORECASE
    )

    CALLOUT_STYLES = {
        'note': {
            'icon': 'info-circle',
            'color': '#0969da',
            'bg': '#ddf4ff',
            'dark_bg': '#193c47',
            'title': 'Note',
        },
        'tip': {
            'icon': 'lightbulb',
            'color': '#1a7f37',
            'bg': '#dafbe1',
            'dark_bg': '#1b4721',
            'title': 'Tip',
        },
        'important': {
            'icon': 'report',
            'color': '#8250df',
            'bg': '#fbefff',
            'dark_bg': '#341c4f',
            'title': 'Important',
        },
        'warning': {
            'icon': 'alert',
            'color': '#9a6700',
            'bg': '#fff8c5',
            'dark_bg': '#4d3800',
            'title': 'Warning',
        },
        'caution': {
            'icon': 'stop',
            'color': '#cf222e',
            'bg': '#ffebe9',
            'dark_bg': '#5a1d23',
            'title': 'Caution',
        },
    }

    def run(self, lines):
        new_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]
            match = self.CALLOUT_PATTERN.match(line)

            if match:
                callout_type = match.group(1).lower()
                style = self.CALLOUT_STYLES.get(callout_type, self.CALLOUT_STYLES['note'])

                # Collect callout content
                content_lines = []
                i += 1
                while i < len(lines) and lines[i].startswith('>'):
                    # Remove the leading '> ' or '>'
                    content = lines[i][1:].lstrip() if len(lines[i]) > 1 else ''
                    content_lines.append(content)
                    i += 1

                content = '\n'.join(content_lines)

                # Generate HTML
                new_lines.append(f'<div class="callout callout-{callout_type}">')
                new_lines.append(f'<div class="callout-title">')
                new_lines.append(f'<span class="callout-icon"></span>')
                new_lines.append(f'<span>{style["title"]}</span>')
                new_lines.append('</div>')
                new_lines.append(f'<div class="callout-content">')
                new_lines.append(content)
                new_lines.append('</div>')
                new_lines.append('</div>')
                new_lines.append('')
            else:
                new_lines.append(line)
                i += 1

        return new_lines


class WikiLinkPattern(InlineProcessor):
    """Inline processor for wiki-style [[links]]."""

    def __init__(self, pattern, md, base_path=None):
        super().__init__(pattern, md)
        self.base_path = base_path

    def handleMatch(self, m, data):
        link_text = m.group(1)

        # Check for display text: [[link|display]]
        if '|' in link_text:
            link_target, display_text = link_text.split('|', 1)
        else:
            link_target = link_text
            display_text = link_text

        # Create anchor element
        el = etree.Element('a')
        el.set('class', 'wiki-link')
        el.set('href', f'{link_target}.md')
        el.set('data-wiki-link', link_target)
        el.text = display_text

        return el, m.start(0), m.end(0)


class WikiLinkExtension(Extension):
    """Extension for wiki-style [[links]]."""

    def __init__(self, **kwargs):
        self.config = {
            'base_path': ['', 'Base path for resolving wiki links'],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        # Pattern: [[link text]] or [[link|display text]]
        pattern = r'\[\[([^\]]+)\]\]'
        wiki_link = WikiLinkPattern(pattern, md, self.getConfig('base_path'))
        md.inlinePatterns.register(wiki_link, 'wikilink', 175)


class CalloutExtension(Extension):
    """Extension for GitHub-style callouts."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            CalloutPreprocessor(md),
            'callout',
            25
        )


class MathPreprocessor(Preprocessor):
    """Preprocessor to protect math blocks from other processing."""

    MATH_BLOCK_PATTERN = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    MATH_INLINE_PATTERN = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')

    def __init__(self, md):
        super().__init__(md)
        self.math_blocks = []

    def run(self, lines):
        text = '\n'.join(lines)

        # Protect block math
        def replace_block(m):
            idx = len(self.math_blocks)
            self.math_blocks.append(('block', m.group(1)))
            return f'MATHBLOCK{idx}ENDMATHBLOCK'

        text = self.MATH_BLOCK_PATTERN.sub(replace_block, text)

        # Protect inline math
        def replace_inline(m):
            idx = len(self.math_blocks)
            self.math_blocks.append(('inline', m.group(1)))
            return f'MATHINLINE{idx}ENDMATHINLINE'

        text = self.MATH_INLINE_PATTERN.sub(replace_inline, text)

        # Store for postprocessor
        self.md.math_blocks = self.math_blocks

        return text.split('\n')


class MathPostprocessor(Postprocessor):
    """Postprocessor to restore math blocks."""

    def run(self, text):
        if not hasattr(self.md, 'math_blocks'):
            return text

        for idx, (math_type, content) in enumerate(self.md.math_blocks):
            if math_type == 'block':
                placeholder = f'MATHBLOCK{idx}ENDMATHBLOCK'
                replacement = f'<div class="math-block">$${content}$$</div>'
            else:
                placeholder = f'MATHINLINE{idx}ENDMATHINLINE'
                replacement = f'<span class="math-inline">${content}$</span>'

            text = text.replace(placeholder, replacement)

        return text


class MathExtension(Extension):
    """Extension for LaTeX math support."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            MathPreprocessor(md),
            'math_pre',
            30
        )
        md.postprocessors.register(
            MathPostprocessor(md),
            'math_post',
            25
        )


class MermaidPreprocessor(Preprocessor):
    """Preprocessor to convert mermaid code blocks.

    Cached diagrams are inlined immediately.  Uncached diagrams get a
    placeholder that is filled asynchronously after the page loads (see
    DocumentTab._render_pending_diagrams).  This keeps the preview snappy
    even when mmdc takes 1-2 s per diagram.

    Falls back to <div class="mermaid"> for client-side JS when mmdc is
    unavailable.

    Reads dark_mode from md.mermaid_dark_mode attribute (set before convert).
    """

    MERMAID_PATTERN = re.compile(
        r'^```mermaid\s*\n(.*?)^```',
        re.MULTILINE | re.DOTALL
    )

    def run(self, lines):
        import html as html_mod
        from fun.markdown6 import mermaid_service

        dark_mode = getattr(self.md, 'mermaid_dark_mode', False)
        # Collect pending (uncached) diagram sources for async rendering
        pending = getattr(self.md, '_pending_diagrams', None)
        if pending is None:
            pending = []
            self.md._pending_diagrams = pending

        text = '\n'.join(lines)

        def replace_mermaid(m):
            content = m.group(1).strip()

            if not mermaid_service.has_mermaid():
                return f'<div class="mermaid">\n{content}\n</div>'

            # If cached, inline immediately (zero cost)
            if mermaid_service.is_cached(content, dark_mode):
                svg, error = mermaid_service.render_mermaid(content, dark_mode)
                if error:
                    return svg
                return f'<div class="mermaid-diagram">{svg}</div>'

            # Not cached — emit placeholder, schedule async render
            idx = len(pending)
            pending.append(('mermaid', content, dark_mode))
            escaped = html_mod.escape(content)
            return (
                f'<div class="mermaid-diagram" id="diagram-pending-{idx}">'
                f'<div class="diagram-loading">'
                f'<pre class="diagram-loading-source">{escaped}</pre>'
                f'<div class="diagram-loading-spinner">Rendering...</div>'
                f'</div></div>'
            )

        text = self.MERMAID_PATTERN.sub(replace_mermaid, text)
        return text.split('\n')


class MermaidExtension(Extension):
    """Extension for Mermaid diagram support."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            MermaidPreprocessor(md),
            'mermaid',
            26
        )


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


def get_callout_css(dark_mode: bool = False) -> str:
    """Get CSS for callout styling."""
    if dark_mode:
        return """
        .callout {
            padding: 16px;
            margin: 16px 0;
            border-radius: 6px;
            border-left: 4px solid;
        }
        .callout-title {
            font-weight: 600;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .callout-note { background: #193c47; border-color: #0969da; }
        .callout-note .callout-title { color: #58a6ff; }
        .callout-tip { background: #1b4721; border-color: #1a7f37; }
        .callout-tip .callout-title { color: #3fb950; }
        .callout-important { background: #341c4f; border-color: #8250df; }
        .callout-important .callout-title { color: #a371f7; }
        .callout-warning { background: #4d3800; border-color: #9a6700; }
        .callout-warning .callout-title { color: #d29922; }
        .callout-caution { background: #5a1d23; border-color: #cf222e; }
        .callout-caution .callout-title { color: #f85149; }
        """
    else:
        return """
        .callout {
            padding: 16px;
            margin: 16px 0;
            border-radius: 6px;
            border-left: 4px solid;
        }
        .callout-title {
            font-weight: 600;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .callout-note { background: #ddf4ff; border-color: #0969da; }
        .callout-note .callout-title { color: #0969da; }
        .callout-tip { background: #dafbe1; border-color: #1a7f37; }
        .callout-tip .callout-title { color: #1a7f37; }
        .callout-important { background: #fbefff; border-color: #8250df; }
        .callout-important .callout-title { color: #8250df; }
        .callout-warning { background: #fff8c5; border-color: #9a6700; }
        .callout-warning .callout-title { color: #9a6700; }
        .callout-caution { background: #ffebe9; border-color: #cf222e; }
        .callout-caution .callout-title { color: #cf222e; }
        """


def get_math_js() -> str:
    """Get JavaScript for math rendering with KaTeX."""
    return """
    <script>
        // Polyfill for structuredClone (not available in older Chromium)
        if (typeof structuredClone === 'undefined') {
            window.structuredClone = function(obj) {
                return JSON.parse(JSON.stringify(obj));
            };
        }
    </script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {
            delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false}
            ]
        });"></script>
    """


def get_mermaid_js() -> str:
    """Get JavaScript for Mermaid diagram rendering.

    Returns JS only when mmdc is unavailable (client-side fallback).
    When mmdc is installed, diagrams are pre-rendered to SVG and no JS is needed.
    """
    from fun.markdown6 import mermaid_service

    if mermaid_service.has_mermaid():
        return ""  # Server-side rendered, no JS needed
    return mermaid_service.get_mermaid_js()


def get_mermaid_css(dark_mode: bool = False) -> str:
    """Get CSS for mermaid diagrams and errors."""
    from fun.markdown6 import mermaid_service
    return mermaid_service.get_mermaid_css(dark_mode)


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


class GraphvizPreprocessor(Preprocessor):
    """Preprocessor to convert graphviz/dot code blocks to rendered SVG.

    Like MermaidPreprocessor, cached results are inlined immediately and
    uncached ones get a placeholder for async rendering.

    Reads dark_mode from md.graphviz_dark_mode attribute (set before convert).
    """

    GRAPHVIZ_PATTERN = re.compile(
        r'^```(?:dot|graphviz)\s*\n(.*?)^```',
        re.MULTILINE | re.DOTALL
    )

    def run(self, lines):
        import html as html_mod
        from fun.markdown6 import graphviz_service

        dark_mode = getattr(self.md, 'graphviz_dark_mode', False)
        pending = getattr(self.md, '_pending_diagrams', None)
        if pending is None:
            pending = []
            self.md._pending_diagrams = pending

        text = '\n'.join(lines)

        def replace_graphviz(m):
            source = m.group(1).strip()

            if not graphviz_service.has_graphviz():
                escaped = html_mod.escape(source)
                return f'<div class="graphviz-pending">{escaped}</div>'

            # If cached, inline immediately
            if graphviz_service.is_cached(source, dark_mode):
                svg, error = graphviz_service.render_dot(source, dark_mode)
                if error:
                    return svg
                return f'<div class="graphviz-diagram">{svg}</div>'

            # Not cached — emit placeholder, schedule async render
            idx = len(pending)
            pending.append(('graphviz', source, dark_mode))
            escaped = html_mod.escape(source)
            return (
                f'<div class="graphviz-diagram" id="diagram-pending-{idx}">'
                f'<div class="diagram-loading">'
                f'<pre class="diagram-loading-source">{escaped}</pre>'
                f'<div class="diagram-loading-spinner">Rendering...</div>'
                f'</div></div>'
            )

        text = self.GRAPHVIZ_PATTERN.sub(replace_graphviz, text)
        return text.split('\n')


class GraphvizImagePostprocessor(Postprocessor):
    """Postprocessor to handle .dot file references in images.

    Reads dark_mode and base_path from md attributes (set before convert).
    """

    DOT_IMAGE_PATTERN = re.compile(
        r'<img\s+[^>]*src=["\']([^"\']+\.dot)["\'][^>]*>',
        re.IGNORECASE
    )

    def run(self, text):
        from fun.markdown6 import graphviz_service
        from pathlib import Path

        # Get config from markdown instance (set by caller before convert)
        dark_mode = getattr(self.md, 'graphviz_dark_mode', False)
        base_path = getattr(self.md, 'graphviz_base_path', None)

        def replace_dot_image(m):
            dot_path = m.group(1)

            # Resolve path relative to base_path if provided
            if base_path:
                full_path = Path(base_path) / dot_path
            else:
                full_path = Path(dot_path)

            # Render the .dot file
            svg, error = graphviz_service.render_dot_file(full_path, dark_mode)
            if error:
                return svg  # Error HTML
            return f'<div class="graphviz-diagram">{svg}</div>'

        text = self.DOT_IMAGE_PATTERN.sub(replace_dot_image, text)
        return text


class GraphvizExtension(Extension):
    """Extension for Graphviz diagram support.

    Before calling md.convert(), set these attributes on the markdown instance:
        md.graphviz_dark_mode = True/False
        md.graphviz_base_path = "/path/to/file/directory"
    """

    def extendMarkdown(self, md):
        md.preprocessors.register(
            GraphvizPreprocessor(md),
            'graphviz',
            27  # After mermaid (26)
        )
        md.postprocessors.register(
            GraphvizImagePostprocessor(md),
            'graphviz_image',
            24  # After math_post (25)
        )

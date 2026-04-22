"""GitHub-style callout/admonition blocks."""

import re

from markdown import Extension
from markdown.preprocessors import Preprocessor


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
                new_lines.append('<div class="callout-title">')
                new_lines.append('<span class="callout-icon"></span>')
                new_lines.append(f'<span>{style["title"]}</span>')
                new_lines.append('</div>')
                new_lines.append('<div class="callout-content">')
                new_lines.append(content)
                new_lines.append('</div>')
                new_lines.append('</div>')
                new_lines.append('')
            else:
                new_lines.append(line)
                i += 1

        return new_lines


class CalloutExtension(Extension):
    """Extension for GitHub-style callouts."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            CalloutPreprocessor(md),
            'callout',
            25
        )


def _admonition_css(dark_mode: bool = False) -> str:
    """CSS for Python-Markdown !!! admonition syntax."""
    # Map admonition types to the same palette as GitHub-style callouts.
    # Types not in this map inherit the default (note) style.
    if dark_mode:
        return """
        .admonition {
            padding: 16px;
            margin: 16px 0;
            border-radius: 6px;
            border-left: 4px solid #0969da;
            background: #193c47;
        }
        .admonition-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: #58a6ff;
        }
        .admonition.note, .admonition.info { background: #193c47; border-color: #0969da; }
        .admonition.note .admonition-title, .admonition.info .admonition-title { color: #58a6ff; }
        .admonition.tip, .admonition.success, .admonition.example { background: #1b4721; border-color: #1a7f37; }
        .admonition.tip .admonition-title, .admonition.success .admonition-title, .admonition.example .admonition-title { color: #3fb950; }
        .admonition.important, .admonition.abstract, .admonition.question { background: #341c4f; border-color: #8250df; }
        .admonition.important .admonition-title, .admonition.abstract .admonition-title, .admonition.question .admonition-title { color: #a371f7; }
        .admonition.warning, .admonition.quote { background: #4d3800; border-color: #9a6700; }
        .admonition.warning .admonition-title, .admonition.quote .admonition-title { color: #d29922; }
        .admonition.caution, .admonition.danger, .admonition.failure, .admonition.bug { background: #5a1d23; border-color: #cf222e; }
        .admonition.caution .admonition-title, .admonition.danger .admonition-title, .admonition.failure .admonition-title, .admonition.bug .admonition-title { color: #f85149; }
        """
    else:
        return """
        .admonition {
            padding: 16px;
            margin: 16px 0;
            border-radius: 6px;
            border-left: 4px solid #0969da;
            background: #ddf4ff;
        }
        .admonition-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: #0969da;
        }
        .admonition.note, .admonition.info { background: #ddf4ff; border-color: #0969da; }
        .admonition.note .admonition-title, .admonition.info .admonition-title { color: #0969da; }
        .admonition.tip, .admonition.success, .admonition.example { background: #dafbe1; border-color: #1a7f37; }
        .admonition.tip .admonition-title, .admonition.success .admonition-title, .admonition.example .admonition-title { color: #1a7f37; }
        .admonition.important, .admonition.abstract, .admonition.question { background: #fbefff; border-color: #8250df; }
        .admonition.important .admonition-title, .admonition.abstract .admonition-title, .admonition.question .admonition-title { color: #8250df; }
        .admonition.warning, .admonition.quote { background: #fff8c5; border-color: #9a6700; }
        .admonition.warning .admonition-title, .admonition.quote .admonition-title { color: #9a6700; }
        .admonition.caution, .admonition.danger, .admonition.failure, .admonition.bug { background: #ffebe9; border-color: #cf222e; }
        .admonition.caution .admonition-title, .admonition.danger .admonition-title, .admonition.failure .admonition-title, .admonition.bug .admonition-title { color: #cf222e; }
        """


def get_callout_css(dark_mode: bool = False) -> str:
    """Get CSS for callout styling (GitHub-style and admonition-style)."""
    if dark_mode:
        callout = """
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
        callout = """
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
    return callout + _admonition_css(dark_mode)

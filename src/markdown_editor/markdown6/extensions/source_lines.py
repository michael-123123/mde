"""Source line markers for editor-preview scroll synchronization."""

import re

from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor


class SourceLinePreprocessor(Preprocessor):
    """Inject <!-- SL:N --> markers before block-starting lines.

    Runs at priority 200 (before all other preprocessors) so that
    the line numbers reflect the original source.  Markers are HTML
    comments that survive markdown processing and are later converted
    to data-source-line attributes by SourceLinePostprocessor.
    """

    FENCE_PATTERN = re.compile(r'^(`{3,}|~{3,})')

    def run(self, lines):
        result = []
        prev_blank = True
        in_fence = False
        fence_char = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Track fenced code blocks - don't inject markers inside them
            if not in_fence:
                fm = self.FENCE_PATTERN.match(stripped)
                if fm:
                    in_fence = True
                    fence_char = fm.group(1)[0]
                    # Mark the fence opening itself
                    result.append(f'<!-- SL:{i} -->')
                    result.append(line)
                    prev_blank = False
                    continue
            else:
                if stripped.startswith(fence_char * 3) and stripped.rstrip('`~ ') == '':
                    in_fence = False
                    fence_char = None
                result.append(line)
                prev_blank = not stripped
                continue

            if not stripped:
                prev_blank = True
                result.append(line)
                continue

            # Insert marker before block-starting lines:
            # after a blank line, or heading lines
            if prev_blank or stripped.startswith('#'):
                result.append(f'<!-- SL:{i} -->')

            prev_blank = False
            result.append(line)

        return result


class SourceLinePostprocessor(Postprocessor):
    """Convert <!-- SL:N --> markers to data-source-line attributes.

    Matches markers immediately before block-level HTML elements and
    injects data-source-line="N" on the opening tag.  Unmatched
    markers are removed.
    """

    SL_PATTERN = re.compile(
        r'<!-- SL:(\d+) -->\s*<(h[1-6]|p|div|ul|ol|li|table|blockquote|pre|hr)(\s|>|/)',
    )

    def run(self, text):
        def inject(m):
            line_num = m.group(1)
            tag = m.group(2)
            after = m.group(3)
            return f'<{tag} data-source-line="{line_num}"{after}'

        text = self.SL_PATTERN.sub(inject, text)
        # Remove any remaining markers that didn't match a block element
        text = re.sub(r'<!-- SL:\d+ -->\s*', '', text)
        return text


class SourceLineExtension(Extension):
    """Inject data-source-line attributes for scroll synchronization."""

    def extendMarkdown(self, md):
        md.preprocessors.register(
            SourceLinePreprocessor(md),
            'source_line_pre',
            200  # Before everything else
        )
        md.postprocessors.register(
            SourceLinePostprocessor(md),
            'source_line_post',
            10  # After all other postprocessors
        )

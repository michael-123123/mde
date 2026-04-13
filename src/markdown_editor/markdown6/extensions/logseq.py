"""Logseq syntax preprocessing for clean preview rendering."""

import re

from markdown import Extension
from markdown.preprocessors import Preprocessor


class LogseqPreprocessor(Preprocessor):
    """Strip Logseq-specific syntax for clean preview rendering.

    Only active when md.logseq_mode is True (set before convert()).
    Strips property lines, block references, macros/embeds/queries,
    and converts task markers (TODO/DONE/etc.) to standard checkboxes.
    """

    PROPERTY_PATTERN = re.compile(r'^\s*\w[\w-]*::\s+.*$')
    BLOCK_REF_PATTERN = re.compile(r'\(\([0-9a-f-]{36}\)\)')
    MACRO_PATTERN = re.compile(r'\{\{[^}]*\}\}')
    # Top-level outliner bullet: "- " with no leading whitespace
    TOPLEVEL_BULLET_PATTERN = re.compile(r'^- (.+)$')
    # Leading whitespace before content on indented lines
    LEADING_WS_PATTERN = re.compile(r'^(\s+)')
    TASK_MARKER_PATTERN = re.compile(
        r'^(\s*[-*] )?(TODO|DOING|NOW|LATER|WAITING|CANCELLED)\s+'
    )
    DONE_MARKER_PATTERN = re.compile(r'^(\s*[-*] )?DONE\s+')
    FENCE_PATTERN = re.compile(r'^(`{3,}|~{3,})')

    @staticmethod
    def _dedent(line, indent_unit):
        """Remove one level of indent_unit from the start of line."""
        if indent_unit and line.startswith(indent_unit):
            return line[len(indent_unit):]
        return line

    def run(self, lines):
        if not getattr(self.md, 'logseq_mode', False):
            return lines

        # First pass: strip properties, refs, macros (these can appear at any
        # indent level and their removal shouldn't affect indent detection).
        cleaned = []
        in_code_block = False
        fence_marker = None

        for line in lines:
            # Track fenced code blocks to avoid stripping inside them
            fence_match = self.FENCE_PATTERN.match(line.strip())
            if fence_match:
                if not in_code_block:
                    in_code_block = True
                    fence_marker = fence_match.group(1)[0]
                elif line.strip().startswith(fence_marker) and len(
                    line.strip().rstrip()
                ) <= len(fence_match.group(1)):
                    in_code_block = False
                    fence_marker = None

            if in_code_block:
                cleaned.append(line)
                continue

            # Strip property lines entirely
            if self.PROPERTY_PATTERN.match(line):
                continue

            # Strip block references inline
            line = self.BLOCK_REF_PATTERN.sub('', line)

            # Strip macros (embeds, queries, renderers, etc.)
            line = self.MACRO_PATTERN.sub('', line)

            cleaned.append(line)

        # Second pass: strip top-level bullets, auto-detect indent unit per
        # section, and dedent children accordingly.
        result = []
        indent_unit = None  # detected from first child after a top-level bullet

        for line in cleaned:
            # Strip top-level outliner bullets (Logseq makes every line a block)
            bullet_match = self.TOPLEVEL_BULLET_PATTERN.match(line)
            if bullet_match:
                line = bullet_match.group(1)
                indent_unit = None  # reset — detect from next child
            elif line.strip():
                # Non-blank, non-top-level line: detect or apply indent
                ws_match = self.LEADING_WS_PATTERN.match(line)
                if ws_match:
                    if indent_unit is None:
                        # First indented child after a top-level bullet:
                        # use its leading whitespace as the indent unit
                        indent_unit = ws_match.group(1)
                    line = self._dedent(line, indent_unit)

            # Convert DONE to checked checkbox
            done_match = self.DONE_MARKER_PATTERN.match(line)
            if done_match:
                prefix = done_match.group(1) or '- '
                line = prefix + '[x] ' + line[done_match.end():]
                result.append(line)
                continue

            # Convert TODO/DOING/NOW/LATER/WAITING/CANCELLED to unchecked checkbox
            task_match = self.TASK_MARKER_PATTERN.match(line)
            if task_match:
                prefix = task_match.group(1) or '- '
                line = prefix + '[ ] ' + line[task_match.end():]
                result.append(line)
                continue

            # Collapse consecutive blank lines left by stripping
            if not line.strip():
                if result and not result[-1].strip():
                    continue

            result.append(line)

        return result


class LogseqExtension(Extension):
    """Extension for Logseq preview mode."""

    def extendMarkdown(self, md):
        md.preprocessors.register(LogseqPreprocessor(md), 'logseq', 101)

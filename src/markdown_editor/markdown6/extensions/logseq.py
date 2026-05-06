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
                indent_unit = None  # reset - detect from next child
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

        # Third pass: unwrap bullet-prefixed code fences.
        # Logseq writes fenced blocks as `<indent>- \`\`\`` (the fence is
        # the bullet's content). Markdown's CommonMark rule requires a
        # fence to start within ≤3 leading spaces — `- \`\`\`` is a list
        # item containing literal backticks, NOT a fence opener. We
        # rewrite the bullet `- ` to two spaces so the fence opens at
        # the same column it visually occupies. The `id::` property line
        # Logseq sometimes inserts immediately after the opener is also
        # stripped (the first pass missed it because the fence wasn't
        # detected then either, but a property line inside a code block
        # IS data we want to drop in Logseq mode — it's not source code).
        return self._unwrap_bullet_fences(result)

    # Recogniser for the SL line markers SourceLinePreprocessor injects.
    # We need to detect them inside fence bodies we're about to unwrap so
    # we can a) remove them (otherwise they break the fence parse) and
    # b) recover the source-line number they encode (so we can synthesise
    # a correctly-placed marker for the fence opener — see comments inside
    # `_unwrap_bullet_fences`).
    SL_MARKER_PATTERN = re.compile(r'^\s*<!--\s*SL:(\d+)\s*-->\s*$')

    def _unwrap_bullet_fences(self, lines):
        bullet_fence_re = re.compile(
            r'^(?P<indent>\s*)- (?P<fence>`{3,}|~{3,})(?P<info>.*)$'
        )
        out: list = []
        i = 0
        while i < len(lines):
            m = bullet_fence_re.match(lines[i])
            if not m:
                out.append(lines[i])
                i += 1
                continue
            # Ensure a blank line precedes the fence — without it,
            # markdown treats the fence opener as paragraph continuation
            # of any preceding non-blank line.
            if out and out[-1].strip():
                out.append("")
            fence = m.group("fence")
            info = m.group("info")
            i += 1
            # Strip a single Logseq `id::` property line right after the
            # opener — Logseq's convention for code-block bullets.
            if i < len(lines) and self.PROPERTY_PATTERN.match(lines[i]):
                i += 1
            # Walk fence body until close. Two things happen during the
            # walk that don't happen in a plain pass-through:
            #
            # 1. Drop any `<!-- SL:N -->` markers we find. They're there
            #    because SourceLinePreprocessor (priority 200) ran first
            #    and didn't recognise our `<indent>- \`\`\`` line as a
            #    fence opener — its detector looks at the stripped line
            #    and sees `- \`\`\``, not `\`\`\``. But it DOES recognise
            #    the close line `<indent>  \`\`\`` as a fence opener, so
            #    it injects a marker right before it.
            # 2. Capture that marker's source-line number. The captured
            #    N is the close's original line; the opener's line is
            #    `N - body_content_lines - 1`.
            body_lines: list[str] = []
            close_line: str | None = None
            captured_close_n: int | None = None
            fence_char = fence[0]
            close_re = re.compile(
                r'^\s*' + re.escape(fence_char) + '{' + str(len(fence))
                + r',}\s*$'
            )
            while i < len(lines):
                line = lines[i]
                i += 1
                sl_m = self.SL_MARKER_PATTERN.match(line)
                if sl_m:
                    captured_close_n = int(sl_m.group(1))
                    continue
                if close_re.match(line):
                    close_line = line
                    break
                body_lines.append(line)
            # Flatten the fence to column 0. Python-Markdown's
            # `fenced_code` extension only opens fences at the start of
            # a line (regex anchored at `^`). Anything indented — even
            # by a single space — is silently rejected and falls through
            # to other processing (typically inline backticks). In a
            # Logseq file the body lines and close line have a leading
            # whitespace prefix matching the bullet's content indent,
            # which by this stage may be tabs or spaces or a mix.
            # Strip the longest common leading whitespace from the body
            # lines (preserving relative indentation INSIDE the code,
            # which matters for languages like Python) and from the
            # close. The opener was already at the bullet's indent; we
            # emit it at column 0 unconditionally.
            non_blank_body = [b for b in body_lines if b.strip()]
            if non_blank_body:
                leading_ws = [
                    b[:len(b) - len(b.lstrip())] for b in non_blank_body
                ]
                common_prefix = leading_ws[0]
                for ws in leading_ws[1:]:
                    while not ws.startswith(common_prefix):
                        common_prefix = common_prefix[:-1]
                        if not common_prefix:
                            break
                    if not common_prefix:
                        break
            else:
                common_prefix = ""
            # Synthesise the opener's SL marker BEFORE we emit the
            # opener, so the rendered <pre> picks it up via the
            # `<!-- SL:N -->` immediately-before-block-element rule.
            if captured_close_n is not None:
                open_source_line = captured_close_n - len(body_lines) - 1
                if open_source_line >= 0:
                    out.append(f"<!-- SL:{open_source_line} -->")
            out.append(f"{fence}{info}")
            for b in body_lines:
                if b.startswith(common_prefix):
                    out.append(b[len(common_prefix):])
                else:
                    # Blank line, or a line shallower than common_prefix.
                    out.append(b.lstrip() if not b.strip() else b)
            if close_line is not None:
                out.append(close_line.lstrip())
                # Ensure a blank line follows the close, so the next
                # markdown element doesn't get glued to the fence.
                if i < len(lines) and lines[i].strip():
                    out.append("")
        return out


class LogseqExtension(Extension):
    """Extension for Logseq preview mode."""

    def extendMarkdown(self, md):
        md.preprocessors.register(LogseqPreprocessor(md), 'logseq', 101)

r"""Markdown link detection - shared between the graph-export GUI and the
`mde` CLI subcommands (`graph`, `stats`, `validate`).

Two link patterns plus a helper to mask verbatim regions (code spans, fenced
blocks, indented blocks, math, HTML) before applying them.

Callers MUST run :func:`mask_verbatim_regions` on the file content before
running these regexes. The patterns walk a flat string and have no idea
whether a given ``[[`` lives inside ``..code..``, a ``\`\`\`fence\`\`\``, math,
or HTML. mde's renderer (python-markdown) handles this correctly because it
tokenises code spans before wiki/inline-link processing; callers of this
module don't go through that pipeline, so they have to mask first.

MD_LINK_PATTERN additionally disallows whitespace in the destination per
CommonMark - a literal newline or space inside ``[text](dest)`` is not a valid
inline-link destination, so excluding ``\s`` keeps a stray ``](`` from being
stitched to a ``.md)`` many paragraphs later.
"""

import re

WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
MD_LINK_PATTERN = re.compile(r'\[([^\]\n]*)\]\(([^)\s]+\.md(?:own)?)\)', re.IGNORECASE)


# Patterns used by mask_verbatim_regions. Compiled once at import.
_FENCED_CODE_RE = re.compile(
    r'(?ms)^([ \t]{0,3})(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\2[ \t]*$'
)
_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_HTML_VERBATIM_TAG_RE = re.compile(
    r'<(pre|script|style)\b[^>]*>.*?</\1>',
    re.IGNORECASE | re.DOTALL,
)
_DISPLAY_MATH_RE = re.compile(r'\$\$.*?\$\$', re.DOTALL)
_INLINE_CODE_RE = re.compile(r'(`+)(?:(?!\1).)+?\1')
_INLINE_MATH_RE = re.compile(r'\$[^$\n]+?\$')


def _spaces_preserving_newlines(s: str) -> str:
    """Return a same-length string with every non-newline character replaced by space."""
    return ''.join('\n' if c == '\n' else ' ' for c in s)


def _mask_indented_code_blocks(content: str) -> str:
    """Mask indented (4-space) code blocks.

    Per CommonMark: an indented code block starts with a 4-space (or tab)
    indented line that does not continue a paragraph; subsequent indented or
    blank lines belong to the block until a non-indented non-blank line ends it.
    """
    lines = content.split('\n')
    out = []
    prev_is_paragraph = False
    for line in lines:
        is_blank = line.strip() == ''
        is_indented = line.startswith('    ') or line.startswith('\t')
        if is_indented and not prev_is_paragraph:
            out.append(' ' * len(line))
            # Stay in code-block context: prev_is_paragraph remains False.
        else:
            out.append(line)
            prev_is_paragraph = not is_blank
    return '\n'.join(out)


def mask_verbatim_regions(content: str) -> str:
    """Replace verbatim regions in markdown with whitespace (length-preserving).

    Used by link detection so that ``[[``, ``]]``, ``](``, ``.md)`` inside code
    spans, fenced blocks, indented blocks, math, or HTML are invisible to the
    link regexes - matching what the markdown renderer would actually display
    verbatim.

    Length is preserved (newlines kept, everything else turned into spaces) so
    callers that care about line numbers / match offsets aren't disturbed.

    Pass order matters: handle multi-line containers (fences, math display,
    HTML blocks) before inline ones, so we don't half-mask their interiors.
    """
    content = _FENCED_CODE_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    content = _HTML_COMMENT_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    content = _HTML_VERBATIM_TAG_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    content = _DISPLAY_MATH_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    content = _mask_indented_code_blocks(content)
    content = _INLINE_CODE_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    content = _INLINE_MATH_RE.sub(
        lambda m: _spaces_preserving_newlines(m.group(0)), content
    )
    return content

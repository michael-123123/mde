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
    masked, _spans = _mask_and_collect_spans(content)
    return masked


def find_verbatim_spans(content: str) -> list[tuple[int, int]]:
    """Return source-position spans (start, end) of every verbatim region.

    Spans are returned sorted by start and merged so overlapping/adjacent
    ranges collapse into one (later masker passes can match against the
    whitespace left by earlier passes - e.g. the indented-code pass picks
    up 4-space-indented lines that the fence pass already blanked out; the
    merge keeps only the outermost range).

    Use this when you need to know whether a specific cursor position is
    inside a verbatim region. ``mask_verbatim_regions`` alone isn't enough
    for that check because the mask preserves whitespace (newlines, spaces)
    in source positions, so cursor-on-whitespace-inside-a-fence would look
    indistinguishable from cursor-on-whitespace-in-prose.
    """
    _masked, spans = _mask_and_collect_spans(content)
    return _merge_overlapping(spans)


def _merge_overlapping(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort + merge overlapping or touching (start, end) ranges."""
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for s, e in spans[1:]:
        ms, me = merged[-1]
        if s <= me:
            merged[-1] = (ms, max(me, e))
        else:
            merged.append((s, e))
    return merged


def _mask_and_collect_spans(content: str) -> tuple[str, list[tuple[int, int]]]:
    """Run the masker passes; return both the masked text and the spans
    collected from each pass. Internal helper for both public APIs."""
    spans: list[tuple[int, int]] = []

    def make_collector():
        def _collect(m):
            spans.append((m.start(), m.end()))
            return _spaces_preserving_newlines(m.group(0))
        return _collect

    content = _FENCED_CODE_RE.sub(make_collector(), content)
    content = _HTML_COMMENT_RE.sub(make_collector(), content)
    content = _HTML_VERBATIM_TAG_RE.sub(make_collector(), content)
    content = _DISPLAY_MATH_RE.sub(make_collector(), content)
    content = _mask_indented_code_blocks_and_collect(content, spans)
    content = _INLINE_CODE_RE.sub(make_collector(), content)
    content = _INLINE_MATH_RE.sub(make_collector(), content)
    return content, spans


def _mask_indented_code_blocks_and_collect(
    content: str, spans: list[tuple[int, int]],
) -> str:
    """Like ``_mask_indented_code_blocks`` but also appends each masked
    line's (start, end) range to *spans* (in source coordinates)."""
    lines = content.split('\n')
    out = []
    prev_is_paragraph = False
    # Track cumulative offset so we can record absolute (start, end) ranges
    # in source coordinates.
    offset = 0
    for line in lines:
        is_blank = line.strip() == ''
        is_indented = line.startswith('    ') or line.startswith('\t')
        if is_indented and not prev_is_paragraph:
            out.append(' ' * len(line))
            spans.append((offset, offset + len(line)))
        else:
            out.append(line)
            prev_is_paragraph = not is_blank
        offset += len(line) + 1   # +1 for the '\n' that split removed
    return '\n'.join(out)

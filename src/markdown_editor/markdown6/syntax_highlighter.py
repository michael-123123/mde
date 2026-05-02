"""Markdown syntax highlighter for the editor."""

import re

from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextBlockUserData,
    QTextCharFormat,
    QTextDocument,
)

from markdown_editor.markdown6.fenced_code_highlighter import (
    DEFAULT_SCHEME_DARK,
    DEFAULT_SCHEME_LIGHT,
    highlight_line,
    initial_state,
    is_language_supported,
    scheme_defaults,
)


# Fence regexes — python-markdown-compatible.
_FENCE_OPEN_RE = re.compile(r'^(?P<fence>`{3,}|~{3,})\s*(?P<lang>[\w+#-]*)')

# Sentinel language for "fence was opened with a language Pygments doesn't
# know"; paint as plain code_block without per-token coloring.
_PLAIN = "_plain_code_"


class FenceState(QTextBlockUserData):
    """Per-block state for lines inside a fenced code block.

    Stored on each in-fence QTextBlock via `setCurrentBlockUserData`.
    `lang` is the Pygments alias (or `_PLAIN` for unknown languages);
    `state` is the opaque `fenced_code_highlighter.State` to resume
    from on the next line; `fence_kind`/`fence_len` pin the closer
    regex (same char, length >= opener).
    """

    __slots__ = ("lang", "state", "fence_kind", "fence_len")

    def __init__(self, lang, state, fence_kind, fence_len):
        super().__init__()
        self.lang = lang
        self.state = state
        self.fence_kind = fence_kind
        self.fence_len = fence_len


def _is_fence_close(text: str, fence_kind: str, fence_len: int) -> bool:
    """True iff `text` is a valid closing fence for an opener of
    `fence_kind` (backtick or tilde) and `fence_len` chars."""
    stripped = text.rstrip()
    if not stripped or stripped[0] != fence_kind:
        return False
    # count leading fence chars
    n = 0
    for ch in stripped:
        if ch == fence_kind:
            n += 1
        else:
            return False  # fence char then non-whitespace non-fence
    return n >= fence_len


class MarkdownHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Markdown text."""

    def __init__(self, document: QTextDocument, dark_mode: bool = False):
        super().__init__(document)
        self.dark_mode = dark_mode
        self._init_formats()
        self._init_rules()

    def set_dark_mode(self, dark: bool):
        """Update colors for dark/light mode."""
        self.dark_mode = dark
        self._init_formats()
        self._init_rules()
        self.rehighlight()

    def _init_formats(self):
        """Initialize text formats."""
        # Colors for light mode
        if self.dark_mode:
            colors = {
                "heading": "#569cd6",
                "bold": "#ce9178",
                "italic": "#dcdcaa",
                "code": "#9cdcfe",
                "code_block": "#9cdcfe",
                "link": "#4ec9b0",
                "url": "#808080",
                "image": "#c586c0",
                "blockquote": "#6a9955",
                "list": "#d4d4d4",
                "hr": "#808080",
                "comment": "#6a9955",
                "strikethrough": "#808080",
                "wiki_link": "#4ec9b0",
                "callout": "#d29922",
                "math": "#c586c0",
            }
        else:
            colors = {
                "heading": "#0000ff",
                "bold": "#871094",
                "italic": "#0451a5",
                "code": "#c7254e",
                "code_block": "#c7254e",
                "link": "#006400",
                "url": "#0366d6",
                "image": "#871094",
                "blockquote": "#6a737d",
                "list": "#24292e",
                "hr": "#6a737d",
                "comment": "#6a737d",
                "strikethrough": "#6a737d",
                "wiki_link": "#0366d6",
                "callout": "#9a6700",
                "math": "#871094",
            }

        self.formats = {}

        # Headings
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["heading"]))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.formats["heading"] = fmt

        # Bold
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["bold"]))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.formats["bold"] = fmt

        # Italic
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["italic"]))
        fmt.setFontItalic(True)
        self.formats["italic"] = fmt

        # Inline code
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["code"]))
        fmt.setFontFamilies(["Monospace"])
        self.formats["code"] = fmt

        # Code block
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["code_block"]))
        fmt.setFontFamilies(["Monospace"])
        self.formats["code_block"] = fmt

        # Link text
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["link"]))
        fmt.setFontUnderline(True)
        self.formats["link"] = fmt

        # URL
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["url"]))
        self.formats["url"] = fmt

        # Image
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["image"]))
        self.formats["image"] = fmt

        # Blockquote
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["blockquote"]))
        fmt.setFontItalic(True)
        self.formats["blockquote"] = fmt

        # List markers
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["list"]))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.formats["list"] = fmt

        # Horizontal rule
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["hr"]))
        self.formats["hr"] = fmt

        # HTML comment
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["comment"]))
        fmt.setFontItalic(True)
        self.formats["comment"] = fmt

        # Strikethrough
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["strikethrough"]))
        fmt.setFontStrikeOut(True)
        self.formats["strikethrough"] = fmt

        # Wiki links [[link]]
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["wiki_link"]))
        fmt.setFontUnderline(True)
        self.formats["wiki_link"] = fmt

        # Callouts [!NOTE] etc
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["callout"]))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.formats["callout"] = fmt

        # Math $...$ and $$...$$
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["math"]))
        self.formats["math"] = fmt

        # ── Code-fence styling ──────────────────────────────────────
        # The fenced-code highlighter resolves every Pygments token's
        # color/bold/italic against the chosen scheme and hands back
        # spans with those primitives baked in. We just build a fresh
        # QTextCharFormat per span at paint time. The scheme also
        # provides a default text color and background, which we paint
        # as the in-fence fill so untokenized tokens (whitespace,
        # punctuation Pygments doesn't style explicitly) match the
        # scheme rather than the editor's default colors.
        self._code_scheme = (
            DEFAULT_SCHEME_DARK if self.dark_mode else DEFAULT_SCHEME_LIGHT
        )
        defaults = scheme_defaults(self._code_scheme)
        fence_fill = QTextCharFormat()
        fence_fill.setForeground(QColor(defaults.default_color))
        fence_fill.setBackground(QColor(defaults.bgcolor))
        fence_fill.setFontFamilies(["Monospace"])
        self.formats["fence_fill"] = fence_fill

    def _make_span_format(self, span) -> QTextCharFormat:
        """Build a QTextCharFormat from a fenced_code_highlighter Span.

        Always carries the scheme bg (from `fence_fill`) unless the span
        specifies its own explicit bgcolor. Qt's `setFormat` REPLACES the
        previous range's format rather than merging — so without copying
        the bg here, in-fence spans would lose the scheme background and
        fall back to Qt's default (black), breaking visual fidelity.

        Also carries the scheme's default foreground when the span has
        `color=None` (token unstyled by this scheme), again because the
        replace-not-merge semantics would otherwise drop it.
        """
        fmt = QTextCharFormat()
        fence_fill = self.formats["fence_fill"]
        fmt.setForeground(
            QColor(span.color) if span.color else fence_fill.foreground().color()
        )
        fmt.setBackground(
            QColor(span.bgcolor) if span.bgcolor else fence_fill.background().color()
        )
        if span.bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if span.italic:
            fmt.setFontItalic(True)
        return fmt

    def _init_rules(self):
        """Initialize highlighting rules."""
        self.rules = []

        # Headings: # Heading
        self.rules.append((
            re.compile(r"^#{1,6}\s+.+$", re.MULTILINE),
            self.formats["heading"],
        ))

        # Bold: **text** or __text__
        self.rules.append((
            re.compile(r"\*\*[^*]+\*\*"),
            self.formats["bold"],
        ))
        self.rules.append((
            re.compile(r"__[^_]+__"),
            self.formats["bold"],
        ))

        # Italic: *text* or _text_
        self.rules.append((
            re.compile(r"(?<!\*)\*(?!\*)[^*]+(?<!\*)\*(?!\*)"),
            self.formats["italic"],
        ))
        self.rules.append((
            re.compile(r"(?<!_)_(?!_)[^_]+(?<!_)_(?!_)"),
            self.formats["italic"],
        ))

        # Strikethrough: ~~text~~
        self.rules.append((
            re.compile(r"~~[^~]+~~"),
            self.formats["strikethrough"],
        ))

        # Inline code: `code`
        self.rules.append((
            re.compile(r"`[^`]+`"),
            self.formats["code"],
        ))

        # Images: ![alt](url)
        self.rules.append((
            re.compile(r"!\[[^\]]*\]\([^)]+\)"),
            self.formats["image"],
        ))

        # Links: [text](url)
        self.rules.append((
            re.compile(r"\[[^\]]+\]\([^)]+\)"),
            self.formats["link"],
        ))

        # Reference links: [text][ref] or [text]
        self.rules.append((
            re.compile(r"\[[^\]]+\]\[[^\]]*\]"),
            self.formats["link"],
        ))

        # Link definitions: [ref]: url
        self.rules.append((
            re.compile(r"^\[[^\]]+\]:\s+.+$", re.MULTILINE),
            self.formats["url"],
        ))

        # Autolinks: <url>
        self.rules.append((
            re.compile(r"<https?://[^>]+>"),
            self.formats["url"],
        ))

        # Blockquotes: > text
        self.rules.append((
            re.compile(r"^>\s+.+$", re.MULTILINE),
            self.formats["blockquote"],
        ))

        # Unordered list markers: -, *, +
        self.rules.append((
            re.compile(r"^\s*[-*+]\s+", re.MULTILINE),
            self.formats["list"],
        ))

        # Ordered list markers: 1. 2. etc
        self.rules.append((
            re.compile(r"^\s*\d+\.\s+", re.MULTILINE),
            self.formats["list"],
        ))

        # Horizontal rules: ---, ***, ___
        self.rules.append((
            re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE),
            self.formats["hr"],
        ))

        # HTML comments: <!-- comment -->
        self.rules.append((
            re.compile(r"<!--.*?-->", re.DOTALL),
            self.formats["comment"],
        ))

        # Wiki links: [[link]] or [[link|text]]
        self.rules.append((
            re.compile(r"\[\[[^\]]+\]\]"),
            self.formats["wiki_link"],
        ))

        # Callouts: [!NOTE], [!WARNING], etc.
        self.rules.append((
            re.compile(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", re.IGNORECASE),
            self.formats["callout"],
        ))

        # Inline math: $...$
        self.rules.append((
            re.compile(r"(?<!\$)\$(?!\$)[^$]+\$(?!\$)"),
            self.formats["math"],
        ))

        # Block math: $$...$$
        self.rules.append((
            re.compile(r"\$\$[^$]+\$\$"),
            self.formats["math"],
        ))

    def highlightBlock(self, text: str):
        """Highlight a block of text."""
        prev_block = self.currentBlock().previous()
        prev_data = prev_block.userData() if prev_block.isValid() else None

        # ── Fence handling ─────────────────────────────────────────
        # Three cases:
        #  (a) Not in a fence and this line opens one.
        #  (b) In a fence and this line is a valid closer.
        #  (c) In a fence and this line is code to highlight.

        if not isinstance(prev_data, FenceState):
            # (a) Possibly opening a fence.
            m = _FENCE_OPEN_RE.match(text)
            if m:
                lang = m.group("lang").lower() or _PLAIN
                if lang is not _PLAIN and not is_language_supported(lang):
                    lang = _PLAIN
                self.setFormat(0, len(text), self.formats["fence_fill"])
                self.setCurrentBlockUserData(
                    FenceState(
                        lang=lang,
                        state=initial_state(),
                        fence_kind=m.group("fence")[0],
                        fence_len=len(m.group("fence")),
                    )
                )
                # block-state int: 1 means "in fence" (coarse flag so Qt's
                # downstream-rehighlight shortcut sees a state change).
                self.setCurrentBlockState(1)
                return
            # Plain markdown — fall through to rules-based highlighting below.
            self.setCurrentBlockState(0)
        else:
            # Inside a fence. Either this line closes it, or it's code.
            if _is_fence_close(text, prev_data.fence_kind, prev_data.fence_len):
                self.setFormat(0, len(text), self.formats["fence_fill"])
                # clear user-data by not setting new FenceState; block state back to 0
                self.setCurrentBlockState(0)
                return

            # Code line. Background fill paints scheme defaults
            # (default_color + bgcolor) under everything; per-token
            # spans then overpaint the styled tokens.
            self.setFormat(0, len(text), self.formats["fence_fill"])
            if prev_data.lang is _PLAIN:
                next_state = prev_data.state
            else:
                result = highlight_line(
                    prev_data.lang, text, prev_data.state, self._code_scheme,
                )
                for span in result.spans:
                    self.setFormat(
                        span.start, span.length, self._make_span_format(span),
                    )
                next_state = result.next_state

            self.setCurrentBlockUserData(
                FenceState(
                    lang=prev_data.lang,
                    state=next_state,
                    fence_kind=prev_data.fence_kind,
                    fence_len=prev_data.fence_len,
                )
            )
            self.setCurrentBlockState(1)
            return

        # Find inline code spans first — these are "protected" regions
        # where no other formatting should apply
        code_pattern = re.compile(r"`[^`]+`")
        code_spans = [(m.start(), m.end()) for m in code_pattern.finditer(text)]

        def overlaps_code(start, end):
            return any(cs <= start < ce or cs < end <= ce
                       for cs, ce in code_spans)

        # Apply regular rules, skipping matches inside inline code
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                if fmt is self.formats.get("code"):
                    # Always apply inline code formatting
                    self.setFormat(start, length, fmt)
                elif not overlaps_code(start, match.end()):
                    self.setFormat(start, length, fmt)

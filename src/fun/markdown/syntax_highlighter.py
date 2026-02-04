"""Markdown syntax highlighter for the editor."""

import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)


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
            }

        self.formats = {}

        # Headings
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["heading"]))
        fmt.setFontWeight(QFont.Bold)
        self.formats["heading"] = fmt

        # Bold
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["bold"]))
        fmt.setFontWeight(QFont.Bold)
        self.formats["bold"] = fmt

        # Italic
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["italic"]))
        fmt.setFontItalic(True)
        self.formats["italic"] = fmt

        # Inline code
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["code"]))
        fmt.setFontFamily("Monospace")
        self.formats["code"] = fmt

        # Code block
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors["code_block"]))
        fmt.setFontFamily("Monospace")
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
        fmt.setFontWeight(QFont.Bold)
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

    def highlightBlock(self, text: str):
        """Highlight a block of text."""
        # Check for fenced code blocks
        block_state = self.previousBlockState()

        # Fenced code block start/end
        fence_match = re.match(r"^(`{3,}|~{3,})", text)

        if fence_match:
            if block_state == 1:
                # End of code block
                self.setFormat(0, len(text), self.formats["code_block"])
                self.setCurrentBlockState(0)
            else:
                # Start of code block
                self.setFormat(0, len(text), self.formats["code_block"])
                self.setCurrentBlockState(1)
            return
        elif block_state == 1:
            # Inside code block
            self.setFormat(0, len(text), self.formats["code_block"])
            self.setCurrentBlockState(1)
            return

        # Apply regular rules
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)

"""Pandoc/Obsidian-style highlight: ``==text==`` -> ``<mark>text</mark>``.

Stock python-markdown doesn't support the ``mark`` extension; pymdownx
does but that's a heavy dep for a single inline pattern. Same shape as
``strikethrough.py`` - one ``SimpleTagInlineProcessor``, no nested ``==``.
"""

from markdown import Extension
from markdown.inlinepatterns import SimpleTagInlineProcessor

# Priority 70 matches the existing strikethrough registration - keeps
# inline emphasis-like markers above the link/ref patterns (which run
# in the 160-180 range) so nested styling stays sane.
_MARK_PATTERN = r'(==)(.+?)=='


class MarkExtension(Extension):
    """Register ``==text==`` -> ``<mark>text</mark>``."""

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            SimpleTagInlineProcessor(_MARK_PATTERN, 'mark'),
            'mark',
            70,
        )

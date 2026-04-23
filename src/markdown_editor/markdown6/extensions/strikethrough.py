"""GFM-style strikethrough: ``~~text~~`` → ``<del>text</del>``.

Stock python-markdown (and the bundled ``extra`` bundle) does not
support strikethrough. Third-party packs like ``pymdownx`` do, but
pulling in pymdownx as a dependency for a single inline pattern is
overkill. A one-line ``SimpleTagInlineProcessor`` covers the common
case: two tildes on each side, no nested tildes, greedy-by-pattern
but bounded by the closing ``~~``.
"""

from markdown import Extension
from markdown.inlinepatterns import SimpleTagInlineProcessor


# Priority 70 matches stock inline patterns like emphasis/strong (~60-110);
# keeps strikethrough higher than link/ref so nested styling stays sane.
_STRIKE_PATTERN = r'(~~)(.+?)~~'


class StrikethroughExtension(Extension):
    """Register ``~~text~~`` → ``<del>text</del>``."""

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            SimpleTagInlineProcessor(_STRIKE_PATTERN, 'del'),
            'strikethrough',
            70,
        )

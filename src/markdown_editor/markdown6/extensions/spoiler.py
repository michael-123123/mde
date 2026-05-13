"""Discord/Obsidian-style spoiler: ``||text||`` -> ``<span class="spoiler">text</span>``.

The pattern isn't in any standard markdown bundle; Pandoc has no
spoiler. Discord uses ``||``, Obsidian uses ``||`` too (Reading-view
extension). We render to a span with class ``spoiler`` so themes can
style the reveal effect however they want.

Conflict to be aware of: GFM tables use ``|`` as cell separator. The
processor's regex matches ``||...||`` only when both delimiters are
``||`` runs and the content has no ``|`` - that limits false positives
inside table cells (where a stray ``|`` would close the cell anyway).
"""

from markdown import Extension
from markdown.inlinepatterns import InlineProcessor
from xml.etree import ElementTree as etree


class _SpoilerProcessor(InlineProcessor):
    def handleMatch(self, m, _data):
        el = etree.Element('span')
        el.set('class', 'spoiler')
        el.text = m.group(1)
        return el, m.start(0), m.end(0)


# Priority 70 - matches the strikethrough/mark family.
_SPOILER_PATTERN = r'\|\|([^|]+?)\|\|'


class SpoilerExtension(Extension):
    """Register ``||text||`` -> ``<span class="spoiler">text</span>``."""

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            _SpoilerProcessor(_SPOILER_PATTERN, md),
            'spoiler',
            70,
        )

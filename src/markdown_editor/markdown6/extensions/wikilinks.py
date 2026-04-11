"""Wiki-style [[link]] inline processing."""

import xml.etree.ElementTree as etree
from markdown import Extension
from markdown.inlinepatterns import InlineProcessor


class WikiLinkPattern(InlineProcessor):
    """Inline processor for wiki-style [[links]]."""

    def __init__(self, pattern, md, base_path=None):
        super().__init__(pattern, md)
        self.base_path = base_path

    def handleMatch(self, m, data):
        link_text = m.group(1)

        # Check for display text: [[link|display]]
        if '|' in link_text:
            link_target, display_text = link_text.split('|', 1)
        else:
            link_target = link_text
            display_text = link_text

        # Create anchor element
        el = etree.Element('a')
        el.set('class', 'wiki-link')
        el.set('href', f'{link_target}.md')
        el.set('data-wiki-link', link_target)
        el.text = display_text

        return el, m.start(0), m.end(0)


class WikiLinkExtension(Extension):
    """Extension for wiki-style [[links]]."""

    def __init__(self, **kwargs):
        self.config = {
            'base_path': ['', 'Base path for resolving wiki links'],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        # Pattern: [[link text]] or [[link|display text]]
        pattern = r'\[\[([^\]]+)\]\]'
        wiki_link = WikiLinkPattern(pattern, md, self.getConfig('base_path'))
        md.inlinePatterns.register(wiki_link, 'wikilink', 175)

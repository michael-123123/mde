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

from xml.etree import ElementTree as etree

from markdown import Extension
from markdown.inlinepatterns import InlineProcessor


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


def get_spoiler_css(dark_mode: bool = False) -> str:
    """CSS for ``<span class="spoiler">`` rendering.

    Click-to-reveal with a blur effect: the text is visibly blurry by
    default (so the reader knows there's content there) and reveals on
    click. See ``get_spoiler_js`` for the click handler that toggles
    the ``.revealed`` class.

    Why blur instead of solid-colour blackout: the user sees that
    spoilered content exists - they can measure how much - they just
    can't read it without opting in. A solid-colour bar can look like
    a redaction or formatting glitch.

    The selector is ``span.spoiler`` so an author who used the same
    class on some other element doesn't accidentally inherit the
    behaviour. ``dark_mode`` is accepted for signature parity with the
    other ``get_*_css`` helpers - blur is theme-agnostic.
    """
    return """
        span.spoiler {
            filter: blur(4px);
            border-radius: 3px;
            padding: 0 0.25em;
            cursor: pointer;
            user-select: none;
            transition: filter 0.15s ease;
        }
        span.spoiler.revealed {
            filter: none;
            user-select: text;
        }
    """


def get_spoiler_js() -> str:
    """Inline ``<script>`` that wires click-to-reveal for spoilers.

    Click toggles a ``.revealed`` class on the span. Sticky - once
    revealed, it stays revealed until the user clicks it again. Matches
    Discord / Obsidian behaviour and is mobile-friendly (no hover
    needed). Run on DOMContentLoaded so it picks up the spans inserted
    by the markdown renderer.

    Returns a ``<script>`` tag so the preview template can drop it in
    next to the other JS helpers (math_js, mermaid_js).
    """
    return """
        <script>
            document.addEventListener('DOMContentLoaded', function () {
                document.querySelectorAll('span.spoiler').forEach(function (el) {
                    el.setAttribute('role', 'button');
                    el.setAttribute('tabindex', '0');
                    el.addEventListener('click', function () {
                        el.classList.toggle('revealed');
                    });
                    el.addEventListener('keydown', function (ev) {
                        if (ev.key === 'Enter' || ev.key === ' ') {
                            ev.preventDefault();
                            el.classList.toggle('revealed');
                        }
                    });
                });
            });
        </script>
    """

"""Regression tests for the preview/export markdown rendering stack.

Each test uses the minimum possible markdown input that reproduces
the bug — not EXAMPLE.md in full. Any noise from surrounding content
(headings, other paragraphs) is deliberately excluded so the failure
points squarely at the rendering rule under test.
"""

from markdown_editor.markdown6.html_renderer_core import build_markdown


def test_two_space_indented_sublist_nests_under_parent():
    """A 2-space indented list item must render as a child of the preceding
    bullet, not as a sibling at the top level.

    EXAMPLE.md uses 2-space indentation throughout. Without `sane_lists`,
    python-markdown demands 4 spaces, and everything collapses to flat.
    """
    src = "- parent\n  - child\n"
    html = build_markdown().convert(src)
    # The child <ul> must sit inside the parent <li>, before that <li> closes.
    assert "<li>parent<ul>" in html.replace("\n", ""), html


def test_three_space_indented_ordered_sublist_nests_under_parent():
    """Ordered-list equivalent: a 3-space indented item (matching `1. `
    content start) must render as a child of the preceding ordered item."""
    src = "1. parent\n   1. child\n"
    html = build_markdown().convert(src)
    assert "<li>parent<ol>" in html.replace("\n", ""), html


def test_tilde_strikethrough_renders_as_del():
    """`~~text~~` must produce a `<del>` element, not literal tildes."""
    html = build_markdown().convert("a ~~b~~ c")
    assert "<del>b</del>" in html, html

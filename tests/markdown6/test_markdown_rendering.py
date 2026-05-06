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


def test_unmarked_fence_does_not_emit_error_tokens():
    """An unmarked code fence (no language tag) must NOT trip Pygments'
    `guess_lexer` — that classifies content as some random language and
    flags non-language characters (e.g. unicode box-drawing) as
    `Token.Error`, which the formatter wraps as `class="err"` with
    visible red/magenta CSS.

    Bug: ASCII-art diagrams in unmarked fences in `MESSAGE_FLOW.md`
    rendered with hundreds of red-bordered character cells because
    `guess_lexer` picked Transact-SQL for one block and Carbon for
    another. We disable language guessing so unmarked fences fall back
    to Pygments' `TextLexer`, which emits no errors.
    """
    src = (
        "```\n"
        "┌─────────┐  ┌──────────┐\n"
        "│  hello  │  │  world   │\n"
        "└─────────┘  └──────────┘\n"
        "```\n"
    )
    html = build_markdown().convert(src)
    assert 'class="err"' not in html, (
        f"unmarked fence emitted error tokens: {html}"
    )


def test_explicitly_tagged_fences_still_highlight():
    """Disabling `guess_lang` must NOT affect fences with an explicit
    language — those still go through their language's lexer."""
    src = (
        "```python\n"
        "def f(): return 1\n"
        "```\n"
    )
    html = build_markdown().convert(src)
    # Pygments' Python lexer styles `def` as a keyword (`class="k"`)
    # and `f` as a function name (`class="nf"`). One of those should
    # appear; otherwise the python fence isn't being highlighted.
    assert 'class="k"' in html or 'class="nf"' in html, (
        f"python fence not highlighted: {html}"
    )

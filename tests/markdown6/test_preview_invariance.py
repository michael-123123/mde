"""Golden-master invariance tests for the live preview rendering path.

These tests LOCK the current output of:
  1. `MarkdownEditor._init_markdown()`-constructed `Markdown.convert()` - the
     "body" HTML that the live preview's incremental JS update writes into
     `#md-content`.
  2. `MarkdownEditor.get_html_template(body, ...)` - the full HTML string
     that QWebEngineView's initial `setHtml` and QTextBrowser's `setHtml`
     receive.

Context: these tests are the iron-rule enforcer for the HTML-export
unification refactor (see local/html-export-unify.md). The refactor must
keep `DocumentTab.render_markdown` output byte-for-byte identical. If
these tests fail after the refactor, the refactor broke the iron rule.

Fixtures are snippets lifted from `examples/EXAMPLE.md` - the canonical
preview feature showcase - plus one whole-file fixture that renders the
entire EXAMPLE.md document end-to-end.

How the goldens work:
  - Expected output is stored as files under `tests/markdown6/invariance/`.
  - Run tests normally to compare current output against goldens.
  - Run with `MDE_UPDATE_GOLDENS=1` to (re)generate goldens from current
    output. This should only happen when the goldens are first created
    OR when an iron-rule-exception change is explicitly sanctioned.
    During the export-unification refactor, do NOT regenerate - the
    tests must pass against the existing goldens.

Determinism:
  - Mermaid and Graphviz service binaries are forced "absent" via
    monkeypatch so both extensions emit their JS-fallback paths (pure
    HTML strings, no external-tool output, no caching, no async
    placeholders). This removes machine-dependent variation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from markdown_editor.markdown6.app_context import get_app_context
from markdown_editor.markdown6.markdown_editor import MarkdownEditor

GOLDENS_DIR = Path(__file__).parent / "invariance"
EXAMPLE_MD = (
    Path(__file__).parent.parent.parent / "examples" / "EXAMPLE.md"
)
UPDATE = os.environ.get("MDE_UPDATE_GOLDENS") == "1"


# ─── Harness ─────────────────────────────────────────────────────────

class _PreviewHarness:
    """Minimal stand-in for MarkdownEditor that exposes the two methods
    the live preview uses on `self.main_window`:
        - self.md (built by _init_markdown)
        - self.get_html_template(...)
    No Qt window is instantiated - we bind the methods to a plain object.
    """

    def __init__(self):
        self.ctx = get_app_context()
        # Bind and call _init_markdown to produce self.md with the full
        # extension stack - identical to what MarkdownEditor does on startup.
        MarkdownEditor._init_markdown.__get__(self)()
        # Bind get_html_template so calls read self.ctx.
        self.get_html_template = MarkdownEditor.get_html_template.__get__(self)

    def convert(
        self,
        text: str,
        *,
        dark_mode: bool = False,
        logseq_mode: bool = False,
        base_path: str | None = None,
    ) -> str:
        """Mirror DocumentTab.render_markdown's setup before calling convert."""
        self.md.reset()
        self.md._pending_diagrams = []
        self.md.graphviz_dark_mode = dark_mode
        self.md.graphviz_base_path = base_path
        self.md.mermaid_dark_mode = dark_mode
        self.md.logseq_mode = logseq_mode
        return self.md.convert(text)


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def no_diagram_tools(monkeypatch):
    """Force mermaid/graphviz binaries to be treated as absent.

    This makes the diagram extensions deterministic: Mermaid emits
    `<div class="mermaid">...</div>` (client-side JS fallback) and
    Graphviz emits `<div class="graphviz-pending">...</div>` (static
    source with a JS fallback). Both template helpers also inject JS.
    """
    monkeypatch.setattr(
        "markdown_editor.markdown6.mermaid_service.has_mermaid",
        lambda: False,
    )
    monkeypatch.setattr(
        "markdown_editor.markdown6.graphviz_service.has_graphviz",
        lambda: False,
    )


@pytest.fixture
def harness(no_diagram_tools):
    return _PreviewHarness()


# ─── Golden compare/update helper ────────────────────────────────────

def _compare_or_write(name: str, actual: str) -> None:
    """Compare `actual` against the golden file at `name`, or write it
    if MDE_UPDATE_GOLDENS=1.

    Fails with a clear message if the golden does not exist yet (forcing
    the developer to review the first-time write).
    """
    path = GOLDENS_DIR / name
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        if not UPDATE:
            pytest.fail(
                f"Golden file {path} did not exist; wrote current output. "
                f"Re-run tests to verify. If this was unexpected, delete "
                f"the file and investigate."
            )
        return

    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Output diverged from golden {name}. "
        f"If this change is intentional (iron rule exception), regenerate "
        f"with MDE_UPDATE_GOLDENS=1. Otherwise the refactor broke the "
        f"live-preview invariance."
    )


# ─── Input fixtures ─────────────────────────────────────────────────
# Snippets below are copied verbatim from examples/EXAMPLE.md - the
# canonical preview feature showcase - so they exercise exactly the
# constructs users see in the live preview. Each fixture is small
# enough that a golden-file diff will pinpoint what changed.

FIXTURES = {
    # Inline text: bold/italic/strike/code, hard breaks, kbd inline HTML
    "inline_text": """Plain paragraph text with **bold**, *italic*, ***bold italic***, ~~strikethrough~~, and `inline code`. Lines in the same paragraph wrap softly
to the next line.

A second paragraph with a hard break at the end of this line,\\
followed by a trailing line using the Markdown backslash break.

Keyboard hint via inline HTML: press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> for the command palette.
""",

    # Unordered with nesting + ordered with nesting
    "lists_nested": """Unordered with nesting:

- First item
- Second item
  - Nested
    - Double-nested
- Third item

Ordered:

1. One
2. Two
   1. Two-a
   2. Two-b
3. Three
""",

    # Task list (GitHub-style checkboxes)
    "tasks": """Task list:

- [x] Implement feature
- [x] Write regression test
- [ ] Update docs
- [ ] Ship it
""",

    # Breakless list (BreaklessListExtension)
    "breakless_list": """Breakless list (no blank line before) handled by `BreaklessListExtension`:
- alpha
- beta
- gamma
""",

    # Nested blockquote
    "blockquote_nested": """> Simple blockquote.
>
> > Nested blockquote.
""",

    # Horizontal rule
    "hr": """Above the rule.

---

Below the rule.
""",

    # Links: markdown, title, bare URL, reference, wiki (bare + display), image
    "links_and_images": """- Markdown link: [Anthropic](https://www.anthropic.com)
- Link with title: [Hover me](https://example.com "tooltip text")
- Bare URL: https://example.com
- Reference-style link: see [the spec][md-spec]
- Wiki link (bare): [[another-note]]
- Wiki link (with display text): [[another-note|a human-friendly label]]
- Image (remote URL): ![Placeholder](https://placehold.co/120x40.png "alt text")

[md-spec]: https://daringfireball.net/projects/markdown/
""",

    # Local image files (raster + vector)
    "local_images": """![A red square](./square.png "square.png - raster/PNG")
![A blue circle](./circle.svg "circle.svg - vector/SVG")
""",

    # Fenced code - python with docstring, f-strings, decorators
    "code_python": """```python
def greet(name: str, punctuation: str = "!") -> str:
    \"\"\"Return a friendly greeting.

    >>> greet("world")
    'Hello, world!'
    \"\"\"
    return f"Hello, {name}{punctuation}"


if __name__ == "__main__":
    print(greet("world"))
```
""",

    # Fenced code - shell
    "code_shell": """```bash
# Export the project to PDF via pandoc, with a TOC and page breaks
mde export -p ./docs -f pdf -o out.pdf --toc --page-breaks

# Validate every wiki link in the project and print JSON
mde validate -p ./docs --json | jq '.broken'
```
""",

    # Fenced code - no language (plain monospace, no highlighting)
    "code_plain": """```
no highlighting here
just monospace text
```
""",

    # Tables with alignment (left/center/right)
    "table": """| Header 1 | Header 2 | Header 3 |
|----------|:--------:|---------:|
| Left     | Center   |    Right |
| Data     | Data     |     Data |
| 42       | ✓        |    99.99 |
""",

    # GitHub-style callouts - all 5 types
    "callouts_github": """> [!NOTE]
> Useful information that readers should pay attention to.

> [!TIP]
> Helpful advice for doing things better.

> [!IMPORTANT]
> Key information users need to know.

> [!WARNING]
> Urgent info that needs immediate user attention to avoid problems.

> [!CAUTION]
> Negative potential consequences of an action.
""",

    # Admonition-style callouts - various types including custom title
    "callouts_admonition": """!!! note "A titled note"
    Admonition callouts accept an optional title.

!!! tip
    Pro tip: every shortcut in the editor is remappable.

!!! warning
    Something to watch out for.

!!! bug
    Admonition supports exotic types too.
""",

    # Math: inline + block + pmatrix
    "math": """Inline: $E = mc^2$, $\\forall x \\in \\mathbb{R}$, and $\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$.

Block:

$$
\\int_0^{\\infty} e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}
$$

$$
\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}
\\begin{pmatrix} x \\\\ y \\end{pmatrix}
=
\\begin{pmatrix} ax + by \\\\ cx + dy \\end{pmatrix}
$$
""",

    # Mermaid diagram
    "mermaid": """```mermaid
graph LR
    A[Editor] -->|source-line sync| B[Preview]
    B -->|click link| C{md file?}
    C -->|yes| D[Open in new tab]
    C -->|no| E[OS default handler]
```
""",

    # Graphviz (dot)
    "graphviz": """```dot
digraph G {
    rankdir=LR;
    node [shape=box, style=rounded];
    MarkdownEditor -> DocumentTab -> EnhancedEditor;
    DocumentTab -> Preview;
    EnhancedEditor -> Preview [label="source-line map", style=dashed];
}
```
""",

    # Definition list (part of python-markdown "extra")
    "definition_list": """markdown-editor
:   A Qt6 Markdown editor with live preview.

mde
:   Short CLI alias for `markdown-editor`.
""",

    # Abbreviation (part of python-markdown "extra")
    "abbreviation": """The HTML spec is defined by the W3C.

*[HTML]: HyperText Markup Language
*[W3C]: World Wide Web Consortium
""",

    # Footnote (part of python-markdown "extra")
    "footnote": """Here is a sentence with a footnote reference.[^1] And another using a named key.[^named]

[^1]: First footnote - appears at the bottom of the rendered document.
[^named]: Named footnotes keep the source readable.
""",

    # TOC placeholder (TocExtension)
    "toc": """[TOC]

# First section

Text.

## Subsection

More text.

# Second section

Even more text.
""",

    # Headings (for SourceLineExtension anchors)
    "headings": """# First heading

paragraph one

## Second heading

paragraph two

### Third-level heading

paragraph three
""",
}


# ─── Class I tests: body-HTML invariance (md.convert output) ────────

@pytest.mark.parametrize("name", list(FIXTURES.keys()))
def test_body_html_invariance(harness, name):
    """The HTML body produced by `self.md.convert()` must be stable.

    This is the string DocumentTab.render_markdown passes to the
    incremental `innerHTML` JS update for QWebEngineView, and the raw
    input to `convert_lists_for_qtextbrowser` for the QTextBrowser path.
    """
    body = harness.convert(FIXTURES[name])
    _compare_or_write(f"{name}_body.html", body)


@pytest.mark.parametrize("name", ["mermaid", "graphviz"])
def test_diagram_body_dark_mode(harness, name):
    """Dark-mode flag is read by Mermaid/Graphviz extensions and may
    affect their output. Locks the dark variant separately."""
    body = harness.convert(FIXTURES[name], dark_mode=True)
    _compare_or_write(f"{name}_body_dark.html", body)


def test_body_logseq_mode(harness):
    """Logseq-mode toggles LogseqExtension's cleanup behavior."""
    logseq_input = """- bullet one
  - nested bullet
- bullet two #tag

TODO Some todo item
DONE Some done item
"""
    body = harness.convert(logseq_input, logseq_mode=True)
    _compare_or_write("logseq_body_on.html", body)

    body_off = harness.convert(logseq_input, logseq_mode=False)
    _compare_or_write("logseq_body_off.html", body_off)


# ─── Class I tests: full-template invariance (get_html_template) ────

@pytest.mark.parametrize("name", list(FIXTURES.keys()))
def test_full_template_invariance(harness, name):
    """The full HTML document produced by `get_html_template(body)` must
    be stable. This is what QWebEngineView receives on first `setHtml`.
    """
    body = harness.convert(FIXTURES[name])
    full = harness.get_html_template(body)
    _compare_or_write(f"{name}_full.html", full)


@pytest.mark.parametrize("name", list(FIXTURES.keys()))
def test_simple_template_invariance(harness, name):
    """The QTextBrowser fallback template (for_qtextbrowser=True).

    Same body, but wrapped in PREVIEW_TEMPLATE_SIMPLE instead of
    PREVIEW_TEMPLATE_FULL.
    """
    body = harness.convert(FIXTURES[name])
    simple = harness.get_html_template(body, for_qtextbrowser=True)
    _compare_or_write(f"{name}_simple.html", simple)


def test_full_template_dark_theme(harness):
    """Switching theme to dark changes CSS colors in the template.

    Locks dark-mode template output for a representative body.
    """
    get_app_context().set("view.theme", "dark")
    body = harness.convert(FIXTURES["inline_text"], dark_mode=True)
    full = harness.get_html_template(body)
    _compare_or_write("inline_text_full_dark.html", full)


def test_full_template_total_lines(harness):
    """total_lines is passed through to the template (used by
    source-line scroll sync)."""
    body = harness.convert(FIXTURES["headings"])
    full = harness.get_html_template(body, total_lines=42)
    _compare_or_write("headings_full_total42.html", full)


# ─── Whole-document invariance ──────────────────────────────────────

def test_whole_example_md_body(harness):
    """Render the entire examples/EXAMPLE.md document and lock the
    body-HTML output. Catches interaction effects between extensions
    that the per-feature fixtures above would miss.
    """
    if not EXAMPLE_MD.exists():
        pytest.skip(f"Missing {EXAMPLE_MD}")
    content = EXAMPLE_MD.read_text(encoding="utf-8")
    body = harness.convert(content, base_path=str(EXAMPLE_MD.parent))
    _compare_or_write("example_md_body.html", body)


def test_whole_example_md_full(harness):
    """Render the entire examples/EXAMPLE.md and lock the full
    template-wrapped HTML output."""
    if not EXAMPLE_MD.exists():
        pytest.skip(f"Missing {EXAMPLE_MD}")
    content = EXAMPLE_MD.read_text(encoding="utf-8")
    body = harness.convert(content, base_path=str(EXAMPLE_MD.parent))
    total_lines = content.count("\n") + 1
    full = harness.get_html_template(body, total_lines=total_lines)
    _compare_or_write("example_md_full.html", full)


def test_whole_example_md_simple(harness):
    """Render the entire examples/EXAMPLE.md through the QTextBrowser
    simple template."""
    if not EXAMPLE_MD.exists():
        pytest.skip(f"Missing {EXAMPLE_MD}")
    content = EXAMPLE_MD.read_text(encoding="utf-8")
    body = harness.convert(content, base_path=str(EXAMPLE_MD.parent))
    simple = harness.get_html_template(body, for_qtextbrowser=True)
    _compare_or_write("example_md_simple.html", simple)

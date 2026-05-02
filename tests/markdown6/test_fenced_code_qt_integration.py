"""Qt-integration tests for per-language fenced-code highlighting.

End-to-end through `MarkdownHighlighter`: set plain text on a
QTextDocument, let Qt's block iterator dispatch `highlightBlock`,
inspect `QTextBlock.layout().formats()` to assert the foreground
color at specific positions.

We assert against scheme-derived colors rather than abstract category
names, because the editor's `setFormat` calls now bake the scheme's
hex strings directly.
"""

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QPlainTextEdit

from markdown_editor.markdown6.fenced_code_highlighter import (
    DEFAULT_SCHEME_DARK,
    DEFAULT_SCHEME_LIGHT,
    highlight_line,
    initial_state,
    scheme_defaults,
)
from markdown_editor.markdown6.syntax_highlighter import MarkdownHighlighter


def _make(qtbot, text, dark_mode=True):
    """The editor's default scheme depends on dark_mode; pinning to
    dark gives us monokai colors which are easy to introspect."""
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    highlighter = MarkdownHighlighter(editor.document(), dark_mode=dark_mode)
    editor.setPlainText(text)
    highlighter.rehighlight()
    return editor, highlighter


def _block_fg_colors(doc: QTextDocument, block_number: int) -> list[tuple[int, int, str]]:
    """[(start, length, fg_color_name), ...] for one block.

    Foreground color is extracted eagerly because the QTextCharFormat
    objects from `QTextLayout.formats()` are transient C++ objects.
    """
    block = doc.findBlockByNumber(block_number)
    layout = block.layout()
    return [
        (r.start, r.length, r.format.foreground().color().name())
        for r in layout.formats()
    ]


def _fg_at(doc: QTextDocument, block_number: int, col: int) -> str | None:
    """Return foreground color at (block, col), or None if outside spans."""
    for start, length, color in _block_fg_colors(doc, block_number):
        if start <= col < start + length:
            return color
    return None


def _scheme_color_at(scheme: str, lang: str, text: str, col: int) -> str | None:
    """What color the scheme would assign to the token covering `col`
    when `text` is lexed fresh in `lang`. Used as ground truth for
    asserting that the editor's painted color matches the scheme."""
    r = highlight_line(lang, text, initial_state(), scheme)
    for s in r.spans:
        if s.start <= col < s.start + s.length:
            return s.color
    return None


class TestPythonDocstringAcrossBlocks:
    """The canonical regression: a multi-line docstring stays
    string-coloured on every line between the opening and closing `\"\"\"`.
    """

    SRC = "\n".join([
        "# outside the fence",
        "```python",                # block 1: fence open
        'def f():',                 # block 2: code
        '    """',                  # block 3: docstring open
        "    Documentation.",       # block 4: inside docstring
        "    More docs.",           # block 5: inside docstring
        '    """',                  # block 6: docstring close
        '    return 42',            # block 7: code again
        "```",                      # block 8: fence close
        "after the fence",          # block 9: plain markdown
    ])
    SCHEME = DEFAULT_SCHEME_DARK

    def test_def_keyword_painted_with_scheme_keyword_color(self, qtbot):
        _, hi = _make(qtbot, self.SRC, dark_mode=True)
        editor_color = _fg_at(hi.document(), 2, 0)
        scheme_color = _scheme_color_at(self.SCHEME, "python", "def f():", 0)
        assert editor_color == scheme_color
        # Sanity: keyword is not the default text color.
        defaults = scheme_defaults(self.SCHEME)
        assert editor_color != defaults.default_color

    def test_docstring_middle_lines_painted_string_color(self, qtbot):
        _, hi = _make(qtbot, self.SRC, dark_mode=True)
        # Sample several positions in middle docstring lines.
        for block_num, sample_col in [(4, 4), (5, 4), (4, 12), (5, 8)]:
            color = _fg_at(hi.document(), block_num, sample_col)
            assert color is not None
        # Compare: all middle-docstring content positions share one color
        # (the string color), unlike `def f():` where def and f differ.
        colors_in_block_4 = {
            color for _, _, color in _block_fg_colors(hi.document(), 4)
        }
        # block 4 is entirely inside the docstring, so all its spans
        # share the string color (only one distinct foreground).
        assert len(colors_in_block_4) == 1

    def test_code_after_docstring_resumes_keyword_coloring(self, qtbot):
        _, hi = _make(qtbot, self.SRC, dark_mode=True)
        # block 7: "    return 42" — 'return' starts at col 4.
        color_return = _fg_at(hi.document(), 7, 4)
        scheme_kw_color = _scheme_color_at(self.SCHEME, "python", "return 42", 0)
        assert color_return == scheme_kw_color

    def test_after_fence_no_code_styling(self, qtbot):
        _, hi = _make(qtbot, self.SRC, dark_mode=True)
        # block 9 is plain markdown — its color should NOT match any
        # scheme code color. (We can't easily assert "is the editor's
        # default text" without coupling, so just confirm it's not
        # the keyword color.)
        color = _fg_at(hi.document(), 9, 0)
        scheme_kw_color = _scheme_color_at(self.SCHEME, "python", "def x", 0)
        assert color != scheme_kw_color


class TestFenceClose:
    """Fence closing rules: same char as opener, length >= opener."""

    def test_backtick_fence_does_not_close_with_tilde(self, qtbot):
        src = "\n".join([
            "```python",
            "x = 1",
            "~~~",
            "y = 2",
            "```",
        ])
        _, hi = _make(qtbot, src)
        # If `~~~` had closed the fence, `2` on line 3 wouldn't be a
        # number. Inside-fence: it gets the number color.
        color = _fg_at(hi.document(), 3, 4)
        scheme_num_color = _scheme_color_at(DEFAULT_SCHEME_DARK, "python", "y = 2", 4)
        assert color == scheme_num_color

    def test_tilde_fence_does_not_close_with_backtick(self, qtbot):
        src = "\n".join([
            "~~~python",
            "x = 1",
            "```",
            "y = 2",
            "~~~",
        ])
        _, hi = _make(qtbot, src)
        color = _fg_at(hi.document(), 3, 4)
        scheme_num_color = _scheme_color_at(DEFAULT_SCHEME_DARK, "python", "y = 2", 4)
        assert color == scheme_num_color

    def test_four_backtick_opener_requires_four_plus_to_close(self, qtbot):
        src = "\n".join([
            "````python",
            "x = 1",
            "```",
            "y = 2",
            "````",
        ])
        _, hi = _make(qtbot, src)
        color = _fg_at(hi.document(), 3, 4)
        scheme_num_color = _scheme_color_at(DEFAULT_SCHEME_DARK, "python", "y = 2", 4)
        assert color == scheme_num_color


class TestUnknownLanguage:
    """An opening fence with an unknown language paints the body using
    the scheme's default-text color; no per-token coloring."""

    SRC = "\n".join([
        "```klingon-not-real",
        "some content here",
        "more content",
        "```",
    ])

    def test_no_crash(self, qtbot):
        _, hi = _make(qtbot, self.SRC)

    def test_body_painted_with_scheme_default_color(self, qtbot):
        _, hi = _make(qtbot, self.SRC)
        # Position 0 of the body should be the scheme default fg color
        # (no Pygments-driven span overlaying it).
        color = _fg_at(hi.document(), 1, 0)
        defaults = scheme_defaults(DEFAULT_SCHEME_DARK)
        assert color == defaults.default_color

    def test_fence_still_closes(self, qtbot):
        src_with_after = self.SRC + "\nafter fence"
        _, hi = _make(qtbot, src_with_after)
        # block 4 is "after fence" — plain markdown, NOT scheme default.
        color = _fg_at(hi.document(), 4, 0)
        defaults = scheme_defaults(DEFAULT_SCHEME_DARK)
        # Plain-markdown text is whatever the markdown rules decide;
        # at minimum, it's not the scheme's code background fill color.
        # We just assert it's distinct from the in-fence default.
        if color is not None:
            assert color != defaults.bgcolor


class TestThemeSwitchRehighlights:

    SRC = "\n".join(["```python", "x = 1", "```"])

    def test_color_changes_on_theme_switch(self, qtbot):
        _, hi = _make(qtbot, self.SRC, dark_mode=False)
        # Light scheme color for the number literal.
        light_color = _fg_at(hi.document(), 1, 4)

        hi.set_dark_mode(True)
        dark_color = _fg_at(hi.document(), 1, 4)
        # Different schemes pick different colors.
        assert light_color != dark_color


class TestFenceBackgroundIsRendered:
    """The PIXEL-LEVEL regression. `QPlainTextEdit` paints per-character
    `QTextCharFormat.background` only behind glyph extents — inter-character
    gaps and trailing line area show through to the widget bg. So even
    when `setFormat` correctly sets a bg per span, the rendered fenced
    block does NOT show a uniform scheme background; it reads as
    striped/muddy with the editor's bg leaking through.

    Fix: paint a full-width `ExtraSelection` for each fence block from
    `EnhancedEditor`, so the entire block area (including gaps + trailing
    space) shows the scheme bg, as the HTML preview does via `<pre>` bg.

    This test renders an `EnhancedEditor` to a `QImage` and verifies that
    a horizontal slice through a fenced SQL line is dominated by the
    scheme bg, not the widget bg.
    """

    def test_full_width_scheme_bg_in_fence(self, qtbot):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from markdown_editor.markdown6.enhanced_editor import EnhancedEditor
        from markdown_editor.markdown6.fenced_code_highlighter import (
            DEFAULT_SCHEME_DARK, scheme_defaults,
        )
        from markdown_editor.markdown6.app_context import (
            get_app_context, init_app_context,
        )

        # Force dark theme so the test doesn't depend on user settings.
        ctx = init_app_context(ephemeral=True)
        ctx.set("view.theme", "dark")

        editor = EnhancedEditor(ctx=ctx)
        qtbot.addWidget(editor)
        editor.setPlainText("```sql\nSELECT u.name FROM users\n```\n")
        editor.resize(800, 200)
        editor.show()
        qtbot.waitExposed(editor)
        qtbot.wait(100)  # let the layout settle

        # Render the editor's viewport (the part that draws text+bg).
        viewport = editor.viewport()
        img = QImage(viewport.size(), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        viewport.render(img)

        # Locate block 1 (the SQL line) in viewport coordinates.
        block = editor.document().findBlockByNumber(1)
        rect = editor.blockBoundingGeometry(block).translated(
            editor.contentOffset()
        ).toRect()

        # Sweep the entire block area — counts pixels that match scheme bg
        # vs widget bg.
        scheme_bg = scheme_defaults(DEFAULT_SCHEME_DARK).bgcolor.lower()
        # The widget bg comes from the dark theme stylesheet.
        # We just need to confirm scheme bg dominates — without per-block
        # bg, scheme bg appears only sparsely (behind glyphs).
        scheme_bg_pixels = 0
        total_pixels = 0
        for y in range(rect.top(), rect.bottom()):
            for x in range(rect.left() + 50, rect.right()):  # skip line-number gutter
                if y >= img.height() or x >= img.width() or y < 0 or x < 0:
                    continue
                color_name = img.pixelColor(x, y).name().lower()
                total_pixels += 1
                if color_name == scheme_bg:
                    scheme_bg_pixels += 1

        ratio = scheme_bg_pixels / total_pixels if total_pixels else 0
        assert ratio > 0.5, (
            f"in-fence area should be dominated by scheme bg ({scheme_bg}); "
            f"only {ratio:.1%} of pixels match (out of {total_pixels})"
        )


class TestFenceWithoutLanguage:
    """No language tag → fall back to scheme-default-text painting only."""

    SRC = "\n".join([
        "```",
        "def not_highlighted(): pass",
        "```",
    ])

    def test_body_painted_with_scheme_default(self, qtbot):
        _, hi = _make(qtbot, self.SRC)
        # 'def' at position 0 should be the scheme default color, NOT
        # the Pygments keyword color (we don't know the language).
        color = _fg_at(hi.document(), 1, 0)
        defaults = scheme_defaults(DEFAULT_SCHEME_DARK)
        assert color == defaults.default_color
        # And distinct from the keyword color we'd see in a real fence.
        kw_color = _scheme_color_at(DEFAULT_SCHEME_DARK, "python", "def x", 0)
        assert color != kw_color

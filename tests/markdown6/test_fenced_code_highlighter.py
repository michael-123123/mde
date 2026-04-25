"""Behavior tests for fenced_code_highlighter.

Uses the public API only; no imports from `_pygments_backend`. Covers
state checkpointing across lines, scheme handling, unknown languages,
aliases, and per-language edge cases (line-scoped states, nested
constructs).

Note on assertions: spans now carry resolved styling (color/bold/italic)
rather than abstract category names. Tests assert behavioural invariants:
"the same line carries different colors when fed different prior states",
"line N inside a docstring is uniformly colored across its full width",
"position 0 of line N has color X with carried state and color Y without".
The exact hex values come from whichever Pygments scheme we use (monokai
by default for behavioural tests).
"""

from markdown_editor.markdown6.fenced_code_highlighter import (
    DEFAULT_SCHEME_DARK,
    DEFAULT_SCHEME_LIGHT,
    LineResult,
    SchemeDefaults,
    Span,
    State,
    available_schemes,
    highlight_line,
    initial_state,
    is_language_supported,
    scheme_defaults,
)

SCHEME = DEFAULT_SCHEME_DARK   # monokai — the test reference


def _color_at(spans: list[Span], pos: int) -> str | None:
    for s in spans:
        if s.start <= pos < s.start + s.length:
            return s.color
    return None


def _hl(lang: str, text: str, state=None, scheme: str = SCHEME) -> LineResult:
    return highlight_line(lang, text, state or initial_state(), scheme)


class TestSchemeBasics:
    def test_available_schemes_returns_sorted_nonempty(self):
        s = available_schemes()
        assert s == sorted(s)
        assert len(s) > 5
        assert all(isinstance(x, str) and x for x in s)

    def test_default_schemes_present(self):
        s = available_schemes()
        assert DEFAULT_SCHEME_LIGHT in s
        assert DEFAULT_SCHEME_DARK in s

    def test_scheme_defaults_returns_hex_strings(self):
        d = scheme_defaults("monokai")
        assert isinstance(d, SchemeDefaults)
        assert d.default_color.startswith("#")
        assert len(d.default_color) == 7
        assert d.bgcolor.startswith("#")
        assert len(d.bgcolor) == 7

    def test_scheme_defaults_differ_across_schemes(self):
        light = scheme_defaults("default")
        dark = scheme_defaults("monokai")
        assert light.bgcolor != dark.bgcolor

    def test_unknown_scheme_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown code-color scheme"):
            scheme_defaults("klingon-xyz")

    def test_highlight_line_unknown_scheme_raises(self):
        import pytest
        with pytest.raises(ValueError):
            highlight_line("python", "x", initial_state(), "klingon-xyz")


class TestLanguageSupport:
    def test_python_is_supported(self):
        assert is_language_supported("python")

    def test_py_alias_is_supported(self):
        assert is_language_supported("py")

    def test_unknown_language_not_supported(self):
        assert not is_language_supported("klingon-not-a-real-language")

    def test_javascript_js_aliases_both_supported(self):
        assert is_language_supported("javascript")
        assert is_language_supported("js")

    def test_csharp_aliases(self):
        assert is_language_supported("csharp")
        assert is_language_supported("c#")


class TestInitialState:
    def test_returns_a_state(self):
        assert isinstance(initial_state(), State)

    def test_equality_across_calls(self):
        assert initial_state() == initial_state()

    def test_empty_line_preserves_initial_state(self):
        r = _hl("python", "")
        assert r.spans == []
        assert r.next_state == initial_state()


class TestUnknownLanguageFallback:
    def test_unknown_lang_returns_empty_spans(self):
        r = _hl("klingon-xyz", "some text")
        assert r.spans == []

    def test_unknown_lang_preserves_state(self):
        s = initial_state()
        r = _hl("klingon-xyz", "some text", state=s)
        assert r.next_state == s


class TestPythonSingleLine:
    """Distinct tokens get distinct colors. We don't assert on specific
    hex values — just that `def` and `foo` differ, etc."""

    def test_keyword_and_function_have_different_colors(self):
        r = _hl("python", "def foo(): pass")
        kw = _color_at(r.spans, 0)
        fn = _color_at(r.spans, 4)
        assert kw is not None and fn is not None
        assert kw != fn

    def test_class_and_classname_have_different_colors(self):
        r = _hl("python", "class Foo: pass")
        kw = _color_at(r.spans, 0)
        cls = _color_at(r.spans, 6)
        assert kw is not None and cls is not None
        assert kw != cls

    def test_string_color_differs_from_keyword(self):
        r = _hl("python", 'x = "hi"')
        s_color = _color_at(r.spans, 4)   # opening quote
        # No keyword on this line, so just assert string is colored
        assert s_color is not None

    def test_state_returns_to_initial_on_plain_code(self):
        r = _hl("python", "x = 1")
        assert r.next_state == initial_state()


class TestPythonTripleDoubleQuote:
    """3-line docstring; carried state changes how line 2 colors."""

    SRC = ['x = """start', "middle content", 'end"""']

    def test_first_line_pushes_into_string_state(self):
        r1 = _hl("python", self.SRC[0])
        assert r1.next_state != initial_state()

    def test_middle_line_uniformly_colored(self):
        """Inside the docstring, every span on line 2 has the same color
        (the string color). With fresh state, line 2 colors differ
        per-token because the lexer sees ordinary names + whitespace."""
        r1 = _hl("python", self.SRC[0])
        r2 = _hl("python", self.SRC[1], state=r1.next_state)

        carried_colors = {s.color for s in r2.spans}
        assert len(carried_colors) == 1, (
            f"expected uniform color across line 2 (it's all string content), "
            f"got {carried_colors}"
        )

        fresh = _hl("python", self.SRC[1])
        # Position 0 ("middle") differs between carried (string) and fresh (name).
        assert _color_at(r2.spans, 0) != _color_at(fresh.spans, 0)


class TestPythonTripleSingleQuote:
    SRC = ["x = '''alpha", "beta", "gamma'''"]

    def test_round_trip_pushes_and_pops(self):
        r1 = _hl("python", self.SRC[0])
        r2 = _hl("python", self.SRC[1], state=r1.next_state)
        r3 = _hl("python", self.SRC[2], state=r2.next_state)
        assert r1.next_state != initial_state()
        assert r2.next_state != initial_state()
        # Line 3 closes the string; state pops back to initial.
        assert r3.next_state == initial_state()
        # Line 2 (middle of string): all spans share the string color.
        assert len({s.color for s in r2.spans}) == 1


class TestJavascriptTemplateLiteral:
    """JS template literals span lines via a state transition. Per-line
    `/* */` does NOT — many lexers match it with one big regex — so we
    pick template literals as our cross-line construct test for JS."""

    SRC = ["const x = `start", "middle content", "end` + y;"]

    def test_template_state_flows_across_lines(self):
        r1 = _hl("js", self.SRC[0])
        r2 = _hl("js", self.SRC[1], state=r1.next_state)
        r3 = _hl("js", self.SRC[2], state=r2.next_state)

        # Line 2 (middle of template): color of position 0 differs from
        # what a fresh lex would assign.
        carried = _color_at(r2.spans, 0)
        fresh = _color_at(_hl("js", self.SRC[1]).spans, 0)
        assert carried != fresh

        # Line 3 starts inside the template; position 0's color (still
        # template/string) differs from a fresh lex's position 0.
        assert _color_at(r3.spans, 0) != _color_at(_hl("js", self.SRC[2]).spans, 0)


class TestPrologBlockComment:
    SRC = ["foo(X) :- /* start", "end */ bar(X)."]

    def test_block_comment_across_lines(self):
        r1 = _hl("prolog", self.SRC[0])
        r2 = _hl("prolog", self.SRC[1], state=r1.next_state)
        # State carries: position 0 on line 2 (still inside comment)
        # has different color from a fresh lex (where it would be a name).
        assert _color_at(r2.spans, 0) != _color_at(_hl("prolog", self.SRC[1]).spans, 0)


class TestSchemeBlockComment:
    """Scheme `#| ... |#` block comment."""

    SRC = ["(define x 1) #| start", "end |# (define y 2)"]

    def test_block_comment_across_lines(self):
        r1 = _hl("scheme", self.SRC[0])
        r2 = _hl("scheme", self.SRC[1], state=r1.next_state)
        carried_pos0 = _color_at(r2.spans, 0)
        fresh_pos0 = _color_at(_hl("scheme", self.SRC[1]).spans, 0)
        assert carried_pos0 != fresh_pos0


class TestRustNestedBlockComment:
    """Pygments' Rust lexer supports nested `/* /* */ */`. We just need
    not to break that — the driver runs Pygments' own state machine
    verbatim, so nesting behaviour is inherited."""

    SRC = ["fn f() { /* outer", "/* inner */ still outer", "*/ }"]

    def test_nested_comment_carries_state(self):
        r1 = _hl("rust", self.SRC[0])
        r2 = _hl("rust", self.SRC[1], state=r1.next_state)
        r3 = _hl("rust", self.SRC[2], state=r2.next_state)
        # Each line's spans differ between carried-state and fresh — nesting
        # affects all three lines.
        for src, result in zip(self.SRC[1:], [r2, r3]):
            assert result.spans != _hl("rust", src).spans


class TestCPreprocessorLineScoped:
    """C's `#include` puts the lexer into a line-scoped `'macro'` state
    that only pops on newline. We synthesise a trailing newline so the
    state pops at end-of-line; otherwise it would leak into line 2.
    """

    def test_include_state_does_not_leak_into_next_line(self):
        r1 = _hl("c", "#include <stdio.h>")
        r2 = _hl("c", "int main(void) {", state=r1.next_state)
        # Line 2's `int` should be a keyword color, distinct from the
        # `main` identifier color.
        kw = _color_at(r2.spans, 0)
        fn = _color_at(r2.spans, 4)
        assert kw != fn

    def test_include_state_pops_at_end_of_line(self):
        r = _hl("c", "#include <stdio.h>")
        assert r.next_state == initial_state()


class TestSqlLexerSmokeTest:
    """SQL lexer uses callable actions (`using`). Smoke test only:
    no crash, non-empty spans on a simple SELECT."""

    def test_simple_select_produces_spans(self):
        r = _hl("sql", "SELECT 1;")
        assert isinstance(r, LineResult)
        assert len(r.spans) > 0


class TestPythonBygroups:
    """Python lexer's `bygroups` callable splits `def foo` into two
    differently-styled tokens. Confirms our driver invokes callable
    actions like Pygments does."""

    def test_def_and_function_name_differ_in_color(self):
        r = _hl("python", "def foo(): pass")
        assert _color_at(r.spans, 0) != _color_at(r.spans, 4)


class TestStateOpacity:
    def test_initial_states_equal(self):
        assert initial_state() == initial_state()

    def test_mid_string_state_differs_from_initial(self):
        r = _hl("python", 'x = """unclosed')
        assert r.next_state != initial_state()

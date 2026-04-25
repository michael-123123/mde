"""Public-API shape tests for the fenced_code_highlighter package.

Pin the public surface — types importable, behaviour at boundaries.
Backend/behaviour tests live in test_fenced_code_highlighter.py.
"""

import pytest

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


class TestPublicSurface:

    def test_span_is_frozen_dataclass(self):
        s = Span(start=0, length=3, color="#ff0000")
        assert s.start == 0 and s.length == 3 and s.color == "#ff0000"
        with pytest.raises(Exception):
            s.start = 5

    def test_span_defaults(self):
        s = Span(start=0, length=3)
        assert s.color is None
        assert s.bgcolor is None
        assert s.bold is False
        assert s.italic is False

    def test_state_is_opaque_and_hashable(self):
        a = State(opaque=("root",))
        b = State(opaque=("root",))
        c = State(opaque=("root", "tdqs"))
        assert a == b and hash(a) == hash(b)
        assert a != c
        assert {a, b, c} == {a, c}

    def test_state_opaque_is_underscore_prefixed(self):
        s = State(opaque=("root",))
        assert hasattr(s, "_opaque")
        assert not hasattr(s, "opaque")

    def test_line_result_holds_spans_and_next_state(self):
        spans = [Span(start=0, length=2, color="#ffffff")]
        next_state = State(opaque=("root",))
        lr = LineResult(spans=spans, next_state=next_state)
        assert lr.spans == spans
        assert lr.next_state is next_state

    def test_scheme_defaults_dataclass(self):
        d = SchemeDefaults(default_color="#abcdef", bgcolor="#012345")
        assert d.default_color == "#abcdef"
        assert d.bgcolor == "#012345"

    def test_default_scheme_constants_are_strings(self):
        assert isinstance(DEFAULT_SCHEME_LIGHT, str) and DEFAULT_SCHEME_LIGHT
        assert isinstance(DEFAULT_SCHEME_DARK, str) and DEFAULT_SCHEME_DARK


class TestEntryPointsCallable:
    """The wired-in implementations must respond. Behaviour is tested
    in test_fenced_code_highlighter.py — these are smoke tests."""

    def test_initial_state(self):
        assert isinstance(initial_state(), State)

    def test_is_language_supported(self):
        assert isinstance(is_language_supported("python"), bool)

    def test_highlight_line_smoke(self):
        result = highlight_line("python", "x = 1", initial_state(), DEFAULT_SCHEME_DARK)
        assert isinstance(result, LineResult)

    def test_scheme_defaults_smoke(self):
        d = scheme_defaults(DEFAULT_SCHEME_DARK)
        assert isinstance(d, SchemeDefaults)

    def test_available_schemes_smoke(self):
        s = available_schemes()
        assert isinstance(s, list)
        assert all(isinstance(x, str) for x in s)
